from __future__ import annotations

from pathlib import Path

from src.evaluation.qa_gate import run_qa_gate


def test_qa_gate_passes_with_thresholds():
    base = Path(__file__).resolve().parents[1]
    summary = run_qa_gate(base)
    assert summary["gate_passed"] is True
    assert summary["metrics"]["intent_accuracy"] >= 0.95
    assert summary["metrics"]["status_success_rate"] >= 0.90
    assert summary["metrics"]["safety_rate"] >= 1.00
