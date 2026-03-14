import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.llm.client import LLMClient
import src.llm.client as llm_module


class _RaisingClient:
    def invoke(self, _prompt: str):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")


def test_llm_generate_sql_falls_back_when_provider_fails():
    client = LLMClient()
    client.enabled = True
    client._client = _RaisingClient()

    sql = client.generate_sql(
        question="Compare a receita deste mês com a do mês anterior",
        schemas={},
        golden_examples=[],
    )
    assert "SELECT" in sql.upper()


def test_llm_generate_report_falls_back_when_provider_fails():
    client = LLMClient()
    client.enabled = True
    client._client = _RaisingClient()

    report = client.generate_report(
        question="Top products by revenue",
        row_count=1,
        data_preview=[{"product": "A", "revenue": 100}],
        persona_text="{}",
        preference_format="bullets",
        golden_examples=[],
    )
    assert "Rows analyzed" in report


def test_ollama_provider_initializes_when_client_available(monkeypatch):
    class _FakeOllama:
        def __init__(self, model, temperature, base_url):
            self.model = model
            self.temperature = temperature
            self.base_url = base_url

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(llm_module, "ChatOllama", _FakeOllama)

    client = LLMClient()
    assert client.enabled is True
    assert client.provider == "ollama"
    assert client._client.model == "qwen2.5"
