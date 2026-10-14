import os

from fastmcp import FastMCP
from starlette.middleware import Middleware as ASGIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette_context.middleware import ContextMiddleware

from schemas.recipe_rag import RecipeRagRequest, RecipeRagResponse
from schemas.recipe_cost import RecipeCostRequest, RecipeCostResponse
from tools.recipe_cost import calculate_total_cost
from tools.recipe_rag import search_recipes
from failure_sim import is_faulty_mode_on, init_request_failure_chance, should_request_fail
from tool_gen import generate_cost_tools

mcp = FastMCP()

WORKSHOP_FLAGS_PATH = "/workshop/flags"


class SimulateFailureHTTPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # служебный адрес с флагами не участвует в имитации сбоев
        if request.url.path == WORKSHOP_FLAGS_PATH:
            return await call_next(request)

        if is_faulty_mode_on():
            init_request_failure_chance()

        if should_request_fail():
            raise Exception("Simulated MCP server failure")

        return await call_next(request)


@mcp.tool
def recipe_rag(request: RecipeRagRequest) -> RecipeRagResponse:
    """
    Поиск по рецептам

    Параметры запроса:
    - search_query: текст, который должен присутствовать в рецепте или ингридентах

    Ответ содержит список рецептов, для которых указаны:
    - name: название рецепта
    - url: ссылка на веб-страницу рецепта
    - ingredients: список ингридиентов рецепта
    """
    recipes = search_recipes(request)
    return RecipeRagResponse(recipes=recipes)


def recipe_cost(request: RecipeCostRequest) -> RecipeCostResponse:
    """
    Расчёт стоимости приготовления рецепта на основе списка ингридиентов

    Параметры запроса:
    - ingredients: массив ингридиентов с опциональным указанием необходимого количества

    Ответ содержит список расчёт стоимости:
    - total_cost: общая стоимость приготовления рецепта
    """
    total_cost = calculate_total_cost(request)
    return RecipeCostResponse(total_cost=total_cost)


STEP_4 = os.getenv("STEP_4", "False") == "True"
if STEP_4:
    generate_cost_tools(mcp, recipe_cost.__doc__)
else:
    mcp.tool(recipe_cost)


@mcp.custom_route(WORKSHOP_FLAGS_PATH, methods=["GET"])
async def workshop_flags(request):
    # флаги, с которыми реально запущен MCP-сервер: агент по ним определяет сессию Langfuse
    return JSONResponse({"STEP_3": is_faulty_mode_on(), "STEP_4": STEP_4})


app = mcp.http_app(
    stateless_http=True,
    json_response=True,
    middleware=[
        ASGIMiddleware(ContextMiddleware),
        ASGIMiddleware(SimulateFailureHTTPMiddleware),
    ],
)
