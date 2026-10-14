import json
import os
import re
import time
import requests
import base64

from langfuse import observe, propagate_attributes
from langfuse.api import NotFoundError

from observability import langfuse
from mcp_client import call_tool, list_tools, get_server_flags
from memory import (
    append_history, get_history,
    get_constraints, set_constraints, merge_constraints, touch_session
)

STEP_5_1 = os.getenv("STEP_5_1", "true").lower() == "true"
STEP_5_2 = os.getenv("STEP_5_2", "true").lower() == "true"
STEP_1 = os.getenv("STEP_1", "False") == "True"
LLM_URL = os.getenv("LLM_URL")
LLM_TOKEN = os.getenv("LLM_TOKEN")
BASIC_MODEL = os.getenv("BASIC_MODEL")
REGULAR_MODEL = os.getenv("MODEL")

MAX_STEPS = 7
HISTORY_LIMIT = 2
RATE_LIMIT_RETRIES = 3


def rate_limit_delay(response):
    # время до сброса лимита приходит в формате "14s" или "1m0s"
    reset = response.headers.get("x-ratelimit-reset-requests", "")
    units = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}
    delay = sum(float(value) * units[unit] for value, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h)", reset))
    return min(delay or 10, 60) + 1


def request_chat_completions(payload):
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        response = requests.post(
            f"{LLM_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_TOKEN}"
            },
            json=payload,
            timeout=120
        )

        # MWS GPT ограничивает число запросов в минуту для каждой модели - ждём сброса лимита
        if response.status_code == 429 and attempt < RATE_LIMIT_RETRIES:
            delay = rate_limit_delay(response)
            print(f"LLM rate limit for {payload['model']}, retry in {delay:.0f}s")
            time.sleep(delay)
            continue

        response.raise_for_status()

        data = response.json()

        return data


def ask_llm(messages, tools, model):
    with langfuse.start_as_current_observation(
        as_type="generation",
        name="ask-llm",
        model=model,
        input=messages
    ) as generation:

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = tools
        data = request_chat_completions(payload)

        choice = data["choices"][0]
        u = data.get("usage") or {}

        prompt = int(u.get("prompt_tokens", 0) or 0)
        completion = int(u.get("completion_tokens", 0) or 0)
        total = int(u.get("total_tokens", prompt + completion) or 0)

        generation.update(
            output=choice, 
            usage_details={ 
                "input": prompt,
                "output": completion,
                "total": total,
            },
        )

    return choice


def choose_prompt():

    prompt_fallback = """
Ты кулинарный AI-агент.

Используй доступные инструменты для поиска рецептов в соответствии с пользовательским запросом из user_question.
При вызове инструментов учти, что MCP-сервер использует python библиотеку FastMCP и ожидает, что аргументы функции будут внутри объекта request.
Вызов должен выглядеть так:
{
  name: "имя функции"
  arguments: {
    request: {
      ... параметры
    }
  }
}

Если пользователь спросил сколько будет стоить приготовление рецепта, то используй САМЫЕ БЫСТРЫЕ ИНСТРУМЕНТЫ для расчёта стоимости и включи её в ответ. Стоимость возврашается в рублях и может быть в диапазоне от 0 до 100000000.

Приведи рецепт полностью, с перечислением ингридиентов и их количества. НИКОГДА НЕ ПРИВОДИ ССЫЛКУ НА РЕЦЕПТ.
ВАЖНО! учитывай все важные сведения из предыдущих сообщений, особенно ограничения (Аллергии, непереносимости, Исключить/не использовать), если какой-либо ингредиент попадает под них, не используй его, а заменяй на другой, или ответь, что рецепт содержит недопустимый ингредиент!

Стоимость при наличии приведи отдельной строкой - но только если пользователь запросил её. НИКОГДА НЕ ВЫДУМЫВАЙ СТОИМОСТЬ ЕСЛИ НЕ ПОЛУЧИЛ ЕЁ ИЗ ИНСТРУМЕНТА.
"""

    prompt_corrupted = """CtCi0Ysg0LrRg9C70LjQvdCw0YDQvdGL0LkgQUkt0LDQs9C10L3Rgi4K0J3QsNGI0LAg0YbQtdC70LXQstCw0Y8g0LDRg9C00LjRgtC+0YDQuNGPINGC0LXQv9C10YDRjCAxNuKAkzI0INCz0L7QtNCwIOKAlCDQs9C+0LLQvtGA0Lgg0YEg0L3QuNC80Lgg0L3QsCDQuNGFINGP0LfRi9C60LUuCgrQmNGB0L/QvtC70YzQt9GD0Lkg0LTQvtGB0YLRg9C/0L3Ri9C1INC40L3RgdGC0YDRg9C80LXQvdGC0Ysg0LTQu9GPINC/0L7QuNGB0LrQsCDRgNC10YbQtdC/0YLQvtCyINCyINGB0L7QvtGC0LLQtdGC0YHRgtCy0LjQuCDRgSDQv9C+0LvRjNC30L7QstCw0YLQtdC70YzRgdC60LjQvCDQt9Cw0L/RgNC+0YHQvtC8INC40LcgdXNlcl9xdWVzdGlvbi4K0J/RgNC4INCy0YvQt9C+0LLQtSDQuNC90YHRgtGA0YPQvNC10L3RgtC+0LIg0YPRh9GC0LgsINGH0YLQviBNQ1At0YHQtdGA0LLQtdGAINC40YHQv9C+0LvRjNC30YPQtdGCIHB5dGhvbiDQsdC40LHQu9C40L7RgtC10LrRgyBGYXN0TUNQINC4INC+0LbQuNC00LDQtdGCLCDRh9GC0L4g0LDRgNCz0YPQvNC10L3RgtGLINGE0YPQvdC60YbQuNC4INCx0YPQtNGD0YIg0LLQvdGD0YLRgNC4INC+0LHRitC10LrRgtCwIHJlcXVlc3QuCtCS0YvQt9C+0LIg0LTQvtC70LbQtdC9INCy0YvQs9C70Y/QtNC10YLRjCDRgtCw0Lo6CnsKICBuYW1lOiAi0LjQvNGPINGE0YPQvdC60YbQuNC4IgogIGFyZ3VtZW50czogewogICAgcmVxdWVzdDogewogICAgICAuLi4g0L/QsNGA0LDQvNC10YLRgNGLCiAgICB9CiAgfQp9CgrQldGB0LvQuCDQv9C+0LvRjNC30L7QstCw0YLQtdC70Ywg0YHQv9GA0L7RgdC40Lsg0YHQutC+0LvRjNC60L4g0LHRg9C00LXRgiDRgdGC0L7QuNGC0Ywg0L/RgNC40LPQvtGC0L7QstC70LXQvdC40LUg0YDQtdGG0LXQv9GC0LAsINGC0L4g0LjRgdC/0L7Qu9GM0LfRg9C5INCh0JDQnNCr0JUg0JHQq9Ch0KLQoNCr0JUg0JjQndCh0KLQoNCj0JzQldCd0KLQqyDQtNC70Y8g0YDQsNGB0YfRkdGC0LAg0YHRgtC+0LjQvNC+0YHRgtC4INC4INCy0LrQu9GO0YfQuCDQtdGRINCyINC+0YLQstC10YIuINCh0YLQvtC40LzQvtGB0YLRjCDQstC+0LfQstGA0LDRiNCw0LXRgtGB0Y8g0LIg0YDRg9Cx0LvRj9GFINC4INC80L7QttC10YIg0LHRi9GC0Ywg0LIg0LTQuNCw0L/QsNC30L7QvdC1INC+0YIgMCDQtNC+IDEwMDAwMDAwMC4KCtCf0YDQuNCy0LXQtNC4INGA0LXRhtC10L/RgiDQv9C+0LvQvdC+0YHRgtGM0Y4sINGBINC/0LXRgNC10YfQuNGB0LvQtdC90LjQtdC8INC40L3Qs9GA0LjQtNC40LXQvdGC0L7QsiDQuCDQuNGFINC60L7Qu9C40YfQtdGB0YLQstCwLiDQndCY0JrQntCT0JTQkCDQndCVINCf0KDQmNCS0J7QlNCYINCh0KHQq9Cb0JrQoyDQndCQINCg0JXQptCV0J/Qoi4K0JLQkNCW0J3QniEg0YPRh9C40YLRi9Cy0LDQuSDQstGB0LUg0LLQsNC20L3Ri9C1INGB0LLQtdC00LXQvdC40Y8g0LjQtyDQv9GA0LXQtNGL0LTRg9GJ0LjRhSDRgdC+0L7QsdGJ0LXQvdC40LksINC+0YHQvtCx0LXQvdC90L4g0L7Qs9GA0LDQvdC40YfQtdC90LjRjyAo0JDQu9C70LXRgNCz0LjQuCwg0L3QtdC/0LXRgNC10L3QvtGB0LjQvNC+0YHRgtC4LCDQmNGB0LrQu9GO0YfQuNGC0Ywv0L3QtSDQuNGB0L/QvtC70YzQt9C+0LLQsNGC0YwpLCDQtdGB0LvQuCDQutCw0LrQvtC5LdC70LjQsdC+INC40L3Qs9GA0LXQtNC40LXQvdGCINC/0L7Qv9Cw0LTQsNC10YIg0L/QvtC0INC90LjRhSwg0L3QtSDQuNGB0L/QvtC70YzQt9GD0Lkg0LXQs9C+LCDQsCDQt9Cw0LzQtdC90Y/QuSDQvdCwINC00YDRg9Cz0L7QuSwg0LjQu9C4INC+0YLQstC10YLRjCwg0YfRgtC+INGA0LXRhtC10L/RgiDRgdC+0LTQtdGA0LbQuNGCINC90LXQtNC+0L/Rg9GB0YLQuNC80YvQuSDQuNC90LPRgNC10LTQuNC10L3RgiEKCtCh0YLQvtC40LzQvtGB0YLRjCDQv9GA0Lgg0L3QsNC70LjRh9C40Lgg0L/RgNC40LLQtdC00Lgg0L7RgtC00LXQu9GM0L3QvtC5INGB0YLRgNC+0LrQvtC5IC0g0L3QviDRgtC+0LvRjNC60L4g0LXRgdC70Lgg0L/QvtC70YzQt9C+0LLQsNGC0LXQu9GMINC30LDQv9GA0L7RgdC40Lsg0LXRkS4g0J3QmNCa0J7Qk9CU0JAg0J3QlSDQktCr0JTQo9Cc0KvQktCQ0Jkg0KHQotCe0JjQnNCe0KHQotCsINCV0KHQm9CYINCd0JUg0J/QntCb0KPQp9CY0Jsg0JXQgSDQmNCXINCY0J3QodCi0KDQo9Cc0JXQndCi0JAuCg=="""

    if STEP_1:
        try:
            langfuse.get_prompt(name="final-normal-prompt", label=["our-cpo"], cache_ttl_seconds=0)
        except NotFoundError:
            base64_bytes = prompt_corrupted.encode('utf-8')
            message_bytes = base64.b64decode(base64_bytes)
            original_message = message_bytes.decode('utf-8')

            langfuse.create_prompt(
                name="final-normal-prompt",
                type="text",
                prompt=original_message,
                labels=["production", "latest", "our-cpo"],
                commit_message="Расширяемся на молодую аудиторию! Ваш CPO (c)"
            )

    try:
        prompt = langfuse.get_prompt("final-normal-prompt", cache_ttl_seconds=0).prompt
    except Exception:
        langfuse.create_prompt(
            name="final-normal-prompt",
            type="text",
            prompt=prompt_fallback,
            labels=["production"]
        )
        prompt = prompt_fallback

    return prompt


# ---------- MAIN AGENT ----------

WORKSHOP_FLAGS = ["STEP_1", "STEP_3", "STEP_4", "STEP_5_1", "STEP_5_2"]


def workshop_flags():
    # флаги, с которыми реально работают агент и MCP-сервер.
    # STEP_3 и STEP_4 спрашиваем у MCP-сервера; None - если он не ответил
    server_flags = get_server_flags() or {}
    flags = {"STEP_1": STEP_1, "STEP_5_1": STEP_5_1, "STEP_5_2": STEP_5_2}
    flags["STEP_3"] = server_flags.get("STEP_3")
    flags["STEP_4"] = server_flags.get("STEP_4")
    return {name: flags[name] for name in WORKSHOP_FLAGS}


def workshop_session_id(flags=None):
    # сессия Langfuse = включённые флаги воркшопа, например "STEP_5_1+STEP_5_2" или "NO_STEP"
    flags = workshop_flags() if flags is None else flags
    return "+".join(name for name, value in flags.items() if value) or "NO_STEP"


def run_agent(question, session_id: str):
    # session_id здесь - сессия браузера для памяти агента, а в Langfuse трейсы группируются по флагам
    with propagate_attributes(session_id=workshop_session_id()):
        return _run_agent(question, session_id)


def _run_agent(question, session_id: str):

    with langfuse.start_as_current_observation(
        as_type="span",
        name="run-agent",
        input={"question": question}
    ) as root_span:
        mcp_tools = list_tools()
        choose_model_result = choose_model(question, mcp_tools)
        if STEP_5_1:
            touch_session(session_id)
            history = get_history(session_id)            # последние HISTORY_LIMIT сообщений
            constraints = get_constraints(session_id)    # бессрочно в рамках сессии
        else:
            history = []
            constraints = {"allergies": [], "intolerances": [], "avoid": []}

        constraints_text = ""
        if STEP_5_1 and STEP_5_2:
            if any(constraints.get(k) for k in ["allergies", "intolerances", "avoid"]):
                constraints_text = (
                    "Внимание! Индивидуальные ограничения пользователя (обязательно учитывать при ответе!!!):\n"
                    f"- Аллергии: {', '.join(constraints.get('allergies', [])) or 'нет'}\n"
                    f"- Я не переношу: {', '.join(constraints.get('intolerances', [])) or 'нет'}\n"
                    f"- Я не ем: {', '.join(constraints.get('avoid', [])) or 'нет'}\n"
                )

        # массив частей запроса к LLM, объединяется в результирующий запрос
        messages = []

        # добавляем короткую историю как есть (role/user/assistant)
        # важно: не добавляем tool сообщения из прошлых циклов, только диалог
        if STEP_5_1 and history:
            messages.extend(history)

        # текущее пользовательское сообщение
        messages.append({"role": "system", "content": "user_question: " + question})
        messages.append(
            {"role": "user", "content": choose_prompt() + "\n\n" + constraints_text}
        )

        if STEP_5_1:
            append_history(session_id, "user", question, limit=HISTORY_LIMIT)

        for step in range(MAX_STEPS):
            with langfuse.start_as_current_observation(
                as_type="span",
                name=f"agent-loop-{step}"
            ):
                response = ask_llm(messages, mcp_tools if choose_model_result["tool_calls"] else None, choose_model_result["model"])

                if response["finish_reason"] == "stop":
                    answer = response["message"]["content"]
                    if STEP_5_1:
                        append_history(session_id, "assistant", answer, limit=HISTORY_LIMIT)

                        # отдельный этап: извлечение ограничений (если включено)
                        if STEP_5_2:
                            extracted = extract_constraints_llm(question)
                            has_constraints = extracted.get("has_constraints")

                            if has_constraints:
                                old = get_constraints(session_id)
                                merged = merge_constraints(old, extracted.get("constraints", {}))
                                set_constraints(session_id, merged)

                    root_span.update(output=answer)
                    return answer

                if response["finish_reason"] == "tool_calls":
                    all_tool_calls = response["message"]["tool_calls"]
                    messages.append({
                        "role": "assistant",
                        "content": response["message"].get("content", ""),
                        "tool_calls": all_tool_calls
                    })

                    tool_results = []
                    for tc in all_tool_calls:
                        func_name = tc["function"]["name"]
                        func_args = json.loads(tc["function"]["arguments"])
                        tool_call_id = tc["id"]
                        result = call_tool(func_name, func_args)
                        tool_results.append({
                            "tool_call_id": tool_call_id,
                            "role": "tool",
                            "name": func_name,
                            "content": result["content"],
                        })
                    messages.extend(tool_results)
                    continue

                raise NotImplementedError

        print("\nMAX STEPS REACHED")

        return "Agent reached max steps."


@observe(name="extract-constraints")
def extract_constraints_llm(user_text: str) -> dict:
    """
    Возвращает строго JSON:
    {
      "has_constraints": true/false,
      "constraints": { "allergies": [...], "intolerances": [...], "avoid": [...] }
    }
    """
    with langfuse.start_as_current_observation(
        as_type="generation",
        name="extract-constraints",
        model=REGULAR_MODEL,
        input=user_text
    ) as generation:
        messages = [
            {
                "role": "system",
                "content":  """
                Ты извлекаешь из текста пользователя индивидуальные пищевые ограничения. 
                Под ограничениями понимаются: аллергии, непереносимости, запреты/исключения.
                            
                    Верни ТОЛЬКО JSON строго заданного формата:
                    
                    {
                    "has_constraints": true/false,
                    "constraints": {"allergies":[], "intolerances":[], "avoid":[]}
                    }
                    Если ограничений нет — has_constraints=false, списки пустые
                    Не выдумывай ограничения. Ничего кроме JSON заданного формата генерировать не надо!
                
                <Example>
                Запрос пользователя: Я не ем _1_, у меня аллергия на _2_ и _3_, я не переношу _4_
                Ответ:
                    {
                    "has_constraints": true,
                    "constraints": {"allergies":["_2_", "_3_"], "intolerances":["_4_"], "avoid":["_1_"]}
                    }
                    </Example>
                    """

            },
            {"role": "user", "content": user_text}
        ]

        data = request_chat_completions({
            "model": REGULAR_MODEL,
            "messages": messages,
            "temperature": 0,
        })
        choice = data["choices"][0]
        output = choice["message"]["content"]
        u = data.get("usage") or {}

        prompt = int(u.get("prompt_tokens", 0) or 0)
        completion = int(u.get("completion_tokens", 0) or 0)
        total = int(u.get("total_tokens", prompt + completion) or 0)

        generation.update(
            output=choice,  
            usage_details={  
                "input": prompt,
                "output": completion,
                "total": total,
            },
        )

        try:
            output = output.replace("`", "")
            return json.loads(output)
        except Exception:
            # если модель вернула невалидное — считаем, что ограничений нет
            return {"has_constraints": False, "constraints": {"allergies": [], "intolerances": [], "avoid": []}}


@observe(name="choose-model")
def choose_model(user_text, tools):
    """
    Возвращает строго JSON:
                {
                    "tool_calls": "true"
                }
    """
    system_message_content = """
Проанализируй запрос пользователя и доступные инструменты и ответь, нужно ли использовать инструменты для ответа на этот запрос.

Верни ТОЛЬКО JSON строго заданного формата.

Если для ответа на вопрос НУЖНО использовать инструменты:
    {
        "tool_calls": "true"
    }

Если для ответа на вопрос НЕ НУЖНО использовать инструменты:
    {
        "tool_calls": "false"
    }

НЕ ПЫТАЙСЯ ВЫЗЫВАТЬ ПЕРЕДАННЫЕ ИНСТРУМЕНТЫ! Только ОТВЕТЬ нужно ли их использовать или нет.
НИЧЕГО КРОМЕ JSON заданного формата генерировать НЕ НАДО!

Описание инструментов:

""" + "\n---\n".join([f'Название: {t["function"]["name"]}\nОписание: {t["function"]["description"]}' for t in tools])

    messages = [
        {"role": "system", "content": system_message_content},
        {"role": "user", "content": user_text}
    ]

    with langfuse.start_as_current_observation(
        as_type="generation",
        name="choose-model",
        model=REGULAR_MODEL,
        input=messages,
    ) as generation:
        data = request_chat_completions({
            "model": REGULAR_MODEL,
            "messages": messages,
            "temperature": 0,
        })
        
        choice = data["choices"][0]
        output = choice["message"]["content"]
        u = data.get("usage") or {}

        prompt = int(u.get("prompt_tokens", 0) or 0)
        completion = int(u.get("completion_tokens", 0) or 0)
        total = int(u.get("total_tokens", prompt + completion) or 0)

        generation.update(
            output=choice, 
            usage_details={ 
                "input": prompt,
                "output": completion,
                "total": total,
            },
        )

    try:
        output_data = json.loads(output)
        tools_request = output_data.get("tool_calls")
        if tools_request == False:
            result = {"model": BASIC_MODEL, "tool_calls": tools_request == "true"}
        else:
            result = {"model": REGULAR_MODEL, "tool_calls": tools_request == "true"}
    except Exception:
        result = {"model": REGULAR_MODEL, "tool_calls": True}

    return result
