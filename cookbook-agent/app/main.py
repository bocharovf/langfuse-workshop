import uuid
import streamlit as st

from agent import run_agent

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
