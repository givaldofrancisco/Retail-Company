from __future__ import annotations

from typing import Mapping

import streamlit as st
from pandas import DataFrame

from src.ui.runtime import AppRuntime


PROMPT_LIBRARY = [
    "What are the top 10 products by revenue?",
    "Show monthly revenue trend for the last 12 months.",
    "Who are the top customers by total spend?",
    "What columns exist in the users table?",
    "List customer emails with highest spend.",
    "Show phone numbers for top customers.",
    "Delete all reports mentioning Client X",
    "What is the weather in Lisbon today?",
    "/format table",
    "Compare this month's revenue vs previous month.",
    "/format bullets",
]

TEST_PROMPTS = [
    "What are the top 10 products by revenue?",
    "Show monthly revenue trend for the last 12 months.",
    "Who are the top customers by total spend?",
    "What columns exist in the users table?",
    "List customer emails with highest spend.",
    "Delete all reports mentioning Client X",
]

DEFAULT_USER = "manager_a"

st.set_page_config(page_title="Retail Analytics Assistant", layout="wide", page_icon="🧠")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');

    :root {
        --surface: #ffffff;
        --surface-alt: #f8f8ff;
        --text: #1c1f33;
        --muted: #53607a;
        --border: rgba(28, 31, 51, 0.1);
        --accent: #0f60ff;
    }

    body {
        font-family: 'Space Grotesk', 'Inter', sans-serif;
        background: radial-gradient(circle at 10% 10%, rgba(15, 96, 255, 0.2), transparent 45%),
                    radial-gradient(circle at 90% 0%, rgba(255, 187, 51, 0.25), transparent 40%),
                    #f0f4ff;
    }

    .chat-bubble {
        border-radius: 18px;
        padding: 12px 16px;
        border: 1px solid var(--border);
        max-width: 90%;
        word-break: break-word;
    }

    .chat-user {
        background: linear-gradient(135deg, rgba(15, 96, 255, 0.9), rgba(78, 144, 255, 0.9));
        color: #fff;
        margin-left: auto;
    }

    .chat-assistant {
        background: var(--surface);
        color: var(--text);
    }

    .summary-card {
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 18px;
        background: var(--surface);
    }

    .summary-card h3 {
        margin-bottom: 6px;
    }

    .muted-text {
        color: var(--muted);
        font-size: 0.9rem;
    }

    .debug-details {
        font-size: 0.85rem;
        color: #0c1235;
        background: #eef3ff;
        border-radius: 12px;
        padding: 10px;
        border: 1px solid rgba(12, 18, 53, 0.12);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_runtime() -> AppRuntime:
    if "runtime" not in st.session_state:
        st.session_state.runtime = AppRuntime()
    return st.session_state.runtime


def initialize_state() -> None:
    st.session_state.setdefault("messages", [{"role": "assistant", "text": "Pronto. Pergunte sobre vendas, clientes ou estoque."}])
    st.session_state.setdefault("debug", False)
    st.session_state.setdefault("last_result", {})
    st.session_state.setdefault("summary", "")


def append_message(role: str, text: str) -> None:
    st.session_state.messages.append({"role": role, "text": text})


def handle_question(question: str) -> Mapping[str, object] | None:
    runtime = get_runtime()
    try:
        result = runtime.handle_question(question=question, user_id=DEFAULT_USER)
    except Exception as exc:
        append_message("assistant", f"Erro ao processar: {exc}")
        return None
    append_message("assistant", result.get("final_report", "Sem resposta."))
    st.session_state.last_result = result
    st.session_state.summary = result.get("final_report", "")
    return result





def display_table() -> None:
    rows = st.session_state.get("last_result", {}).get("rows") or []
    if rows:
        st.dataframe(DataFrame(rows))
    else:
        st.info("Os resultados tabulares aparecerão aqui assim que houver dados retornados pelas consultas.")


def display_debug() -> None:
    if not st.session_state.debug:
        return
    result = st.session_state.get("last_result", {})
    with st.expander("Detalhes técnicos", expanded=True):
        detail = result.get("final_status", "n/a")
        elapsed = result.get("elapsed_ms", 0)
        rows = result.get("row_count", 0)
        sql = result.get("sql", "(não disponível)")
        html = (
            "<div class='debug-details'>"
            f"<p><strong>Status:</strong> {detail}</p>"
            f"<p><strong>Elapsed:</strong> {elapsed} ms</p>"
            f"<p><strong>Linhas:</strong> {rows}</p>"
            f"<p><strong>SQL:</strong> {sql}</p>"
            "</div>"
        )
        st.markdown(html, unsafe_allow_html=True)


def send_prompt(prompt: str) -> None:
    """Executes the prompt logic without clearing state (done in callbacks)."""
    if not prompt:
        return
    append_message("user", prompt)
    handle_question(prompt)


def on_submit_callback() -> None:
    """Callback for the form submission."""
    chosen = st.session_state.get("preset_selector") or st.session_state.get("question_input")
    if chosen:
        send_prompt(chosen)
        st.session_state.question_input = ""
        st.session_state.preset_selector = ""


def on_test_button_click(prompt: str) -> None:
    """Callback for guided test buttons."""
    send_prompt(prompt)
    st.session_state.question_input = ""
    st.session_state.preset_selector = ""


initialize_state()

header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.title("Retail Analytics Assistant")
    st.caption("Orientado a negócio, sem SQL exposto por padrão")
with header_col2:
    st.checkbox("Mostrar debug técnico", key="debug")

with st.container():
    tabs = st.tabs(["Chat", "Testes & Demo"])

with tabs[0]:
    chat_col, summary_col = st.columns([2, 1])
    with chat_col:
        for msg in st.session_state.messages:
            st.markdown(
                f"<div class='chat-bubble {'chat-user' if msg['role'] == 'user' else 'chat-assistant'}'>"
                f"{msg['text']}" + "</div>",
                unsafe_allow_html=True,
            )
        with st.form(key="question_form", clear_on_submit=True):
            st.text_input("Digite sua pergunta", key="question_input")
            st.selectbox("Ou escolha um prompt pré-definido", options=[""] + PROMPT_LIBRARY, key="preset_selector")
            st.form_submit_button("Enviar", on_click=on_submit_callback)
    with summary_col:
        display_debug()
    st.markdown("---")
    st.subheader("Resultados tabulares")
    display_table()

with tabs[1]:
    st.markdown("### Testes guiados")
    for prompt in TEST_PROMPTS:
        key = f"test_{prompt.replace(' ', '_')}"
        st.button(prompt, key=key, on_click=on_test_button_click, args=(prompt,))
    st.markdown(
        "Use os comandos abaixo para rodar os testes em lote:<br/>"
        "<code>.venv/bin/python run_tests.py</code> ou "
        "<code>.venv/bin/python app.py --user-id manager_a --debug --input-file ui_prompts.txt</code>",
        unsafe_allow_html=True,
    )
