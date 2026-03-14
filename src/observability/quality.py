"""Quality evaluation signals – heuristic post-execution quality scoring.

Computes groundedness, relevance, completeness without calling an LLM.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from src.observability.models import QualitySignal


# Reuse the tokenizer from GoldenRetriever
_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


def _tokens(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


class QualityEvaluator:
    """Heuristic quality scoring for agent responses."""

    def __init__(self) -> None:
        self._signals: List[QualitySignal] = []

    def evaluate(
        self,
        trace_id: str,
        question: str,
        final_report: Optional[str],
        result_rows: Optional[List[Dict[str, Any]]],
        final_status: str,
        used_fallback: bool = False,
    ) -> QualitySignal:
        report = final_report or ""
        rows = result_rows or []

        signal = QualitySignal(
            trace_id=trace_id,
            groundedness=self._compute_groundedness(report, rows),
            relevance=self._compute_relevance(question, report),
            completeness=self._compute_completeness(question, report, len(rows)),
            tool_success_final_success=(final_status == "success"),
            used_fallback=used_fallback,
            empty_response=(not report.strip()),
        )
        self._signals.append(signal)
        return signal

    @property
    def signals(self) -> List[QualitySignal]:
        return list(self._signals)

    def get_summary(self) -> Dict[str, Any]:
        if not self._signals:
            return {}

        n = len(self._signals)
        groundedness = [s.groundedness for s in self._signals if s.groundedness is not None]
        relevance = [s.relevance for s in self._signals if s.relevance is not None]
        completeness = [s.completeness for s in self._signals if s.completeness is not None]

        return {
            "total_evaluations": n,
            "avg_groundedness": round(sum(groundedness) / len(groundedness), 3) if groundedness else None,
            "avg_relevance": round(sum(relevance) / len(relevance), 3) if relevance else None,
            "avg_completeness": round(sum(completeness) / len(completeness), 3) if completeness else None,
            "success_rate": sum(1 for s in self._signals if s.tool_success_final_success) / n,
            "fallback_rate": sum(1 for s in self._signals if s.used_fallback) / n,
            "empty_response_rate": sum(1 for s in self._signals if s.empty_response) / n,
        }

    def record_user_feedback(self, trace_id: str, feedback: str) -> None:
        for signal in reversed(self._signals):
            if signal.trace_id == trace_id:
                signal.user_feedback = feedback
                return

    def reset(self) -> None:
        self._signals.clear()

    # ----- Heuristic scorers -----

    @staticmethod
    def _compute_groundedness(report: str, rows: List[Dict[str, Any]]) -> float:
        """What fraction of numbers in the report appear in the data?"""
        if not report or not rows:
            return 0.0

        report_numbers = set(_NUMBER_RE.findall(report))
        if not report_numbers:
            return 1.0  # No numbers to verify → assume grounded

        # Collect all numbers from the data rows
        data_numbers: set[str] = set()
        for row in rows:
            for v in row.values():
                data_numbers.update(_NUMBER_RE.findall(str(v)))

        if not data_numbers:
            return 0.5  # No data numbers to compare against

        matched = report_numbers.intersection(data_numbers)
        return round(len(matched) / len(report_numbers), 3)

    @staticmethod
    def _compute_relevance(question: str, report: str) -> float:
        """Token overlap between question and report, normalized by question tokens."""
        q_tokens = set(_tokens(question))
        r_tokens = set(_tokens(report))
        if not q_tokens:
            return 0.0
        overlap = len(q_tokens.intersection(r_tokens))
        return round(min(overlap / len(q_tokens), 1.0), 3)

    @staticmethod
    def _compute_completeness(question: str, report: str, row_count: int) -> float:
        """Checklist heuristic for completeness."""
        score = 0.0

        # Does the report mention data volume?
        if any(w in report.lower() for w in ["row", "record", "result", "total", str(row_count)]):
            score += 0.25

        # Does it contain at least one data point?
        if _NUMBER_RE.search(report):
            score += 0.25

        # Is it longer than 50 characters?
        if len(report.strip()) > 50:
            score += 0.25

        # Does it NOT contain failure indicators?
        failure_phrases = ["could not", "unable", "no matching", "no data", "error"]
        if not any(phrase in report.lower() for phrase in failure_phrases):
            score += 0.25

        return round(score, 3)
