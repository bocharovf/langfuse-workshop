import uuid
import streamlit as st

from agent import run_agent, workshop_flags

# отладочная информация в правом верхнем углу: с какими флагами реально работают агент и MCP-сервер.
# Показываем только включённые флаги; "?" - если MCP-сервер не ответил
flags = workshop_flags()
debug_lines = [f"{name} = {'?' if value is None else value}" for name, value in flags.items() if value is not False]
st.markdown(
    '<div style="position: fixed; top: 4.25rem; right: 1rem; z-index: 1000; white-space: nowrap; '
    'font-size: 0.75rem; line-height: 1.4; color: gray; text-align: right;">'
    + "<br>".join(debug_lines or ["Все флаги False"])
    + "</div>",
    unsafe_allow_html=True,
)

st.title("Cookbook MCP Agent")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

question = st.text_input(
    "Задайте вопрос",
    "Как сделать котлеты? Сколько будет стоить приготовление?"
)

if st.button("Спросить агента"):
    result = run_agent(question, session_id=st.session_state.session_id)
    st.write(result)
