import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.safety.guardrails import Guardrails


def test_detects_destructive_report_operation():
    guardrails = Guardrails()
    result = guardrails.classify_intent("Delete all reports mentioning Client X")
    assert result["intent"] == "destructive_report_op"


def test_detects_schema_lookup():
    guardrails = Guardrails()
    result = guardrails.classify_intent("What columns exist in the users table?")
    assert result["intent"] == "schema_lookup"


def test_detects_unsupported_intent():
    guardrails = Guardrails()
    result = guardrails.classify_intent("qual o clima hoje em lisboa?")
    assert result["intent"] == "unsupported"


def test_detects_portuguese_analysis_question():
    guardrails = Guardrails()
    result = guardrails.classify_intent("Qual foi a receita total por mês nos últimos 12 meses?")
    assert result["intent"] == "analysis"


if __name__ == "__main__":
    checks = [
        ("detects_destructive_report_operation", test_detects_destructive_report_operation),
        ("detects_schema_lookup", test_detects_schema_lookup),
        ("detects_unsupported_intent", test_detects_unsupported_intent),
        ("detects_portuguese_analysis_question", test_detects_portuguese_analysis_question),
    ]
    passed = 0
    for name, fn in checks:
        fn()
        passed += 1
        print(f"[PASSOU] {name}")
    print(f"Resumo: {passed}/{len(checks)} checks aprovados")
