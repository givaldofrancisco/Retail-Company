"""Retrieval observability – observable wrappers for GoldenRetriever and SchemaTool.

The GoldenRetriever is a lightweight few-shot example selector that uses
token overlap (not embeddings or vector search). It matches the user question
against 5 hardcoded question/SQL/report examples in golden_trios.json.

This module captures retrieval timing, overlap scores, top-k, "no relevant
examples" rate, and data origin.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from src.observability.decorators import span_context
from src.observability.metrics import record_metric
from src.observability.models import RetrievalObservation
from src.tools.golden_retriever import GoldenRetriever
from src.tools.schema_tool import SchemaTool


# ---------------------------------------------------------------------------
# Retrieval observation store
# ---------------------------------------------------------------------------


class RetrievalObservationStore:
    """Collects retrieval observation records (few-shot example selection & schema fetch) per session."""

    def __init__(self) -> None:
        self._observations: List[RetrievalObservation] = []

    def add(self, obs: RetrievalObservation) -> None:
        self._observations.append(obs)

    @property
    def observations(self) -> List[RetrievalObservation]:
        return list(self._observations)

    def get_summary(self) -> Dict[str, Any]:
        if not self._observations:
            return {}
        total = len(self._observations)
        no_relevant = sum(1 for o in self._observations if o.no_relevant_docs)
        avg_top_score = 0.0
        scores = [o.top_scores[0] for o in self._observations if o.top_scores]
        if scores:
            avg_top_score = sum(scores) / len(scores)
        avg_time = sum(o.retrieval_time_ms for o in self._observations) / total
        return {
            "total_retrievals": total,
            "no_relevant_docs_count": no_relevant,
            "no_relevant_docs_rate": no_relevant / total,
            "avg_top_score": round(avg_top_score, 3),
            "avg_retrieval_time_ms": round(avg_time, 2),
        }

    def reset(self) -> None:
        self._observations.clear()


# Module singleton
_retrieval_store = RetrievalObservationStore()


def get_retrieval_store() -> RetrievalObservationStore:
    return _retrieval_store


def reset_retrieval_store() -> None:
    _retrieval_store.reset()


# ---------------------------------------------------------------------------
# ObservableGoldenRetriever
# ---------------------------------------------------------------------------


class ObservableGoldenRetriever(GoldenRetriever):
    """GoldenRetriever subclass that captures few-shot retrieval metrics.

    Note: GoldenRetriever uses token-overlap scoring on 5 hardcoded examples
    in golden_trios.json. This is NOT a vector-store / embedding-based RAG
    system – it is a simple few-shot example selector.
    """

    def retrieve(self, question: str, top_k: int = 3) -> List[Dict[str, Any]]:
        with span_context("fewshot_retrieve", query=question[:200], top_k=top_k) as span:
            start = time.perf_counter()
            results = super().retrieve(question, top_k=top_k)
            elapsed = (time.perf_counter() - start) * 1000

            scores = [r.get("score", 0) for r in results]
            no_relevant = all(s == 0 for s in scores) if scores else True

            obs = RetrievalObservation(
                query=question[:500],
                docs_retrieved=len(results),
                top_scores=scores,
                top_k_requested=top_k,
                retrieval_time_ms=round(elapsed, 2),
                data_origin="golden_trios.json",
                no_relevant_docs=no_relevant,
            )
            _retrieval_store.add(obs)

            # Metrics
            record_metric("retrieval_time_ms", elapsed)
            record_metric("retrieval_docs_count", len(results))
            if scores:
                record_metric("retrieval_top_score", max(scores))
            if no_relevant:
                record_metric("retrieval_no_relevant", 1)

            # Span attributes
            if span is not None:
                span.attributes.update({
                    "docs_retrieved": len(results),
                    "top_scores": scores,
                    "no_relevant_docs": no_relevant,
                })

            return results


# ---------------------------------------------------------------------------
# ObservableSchemaTool
# ---------------------------------------------------------------------------


class ObservableSchemaTool(SchemaTool):
    """SchemaTool subclass that captures schema fetch metrics."""

    def fetch(self) -> Dict[str, List[dict]]:
        with span_context("schema_fetch", tables=self.tables) as span:
            start = time.perf_counter()
            result = super().fetch()
            elapsed = (time.perf_counter() - start) * 1000

            # Count fallback usage
            fallback_count = 0
            total_columns = 0
            for table_name, columns in result.items():
                total_columns += len(columns)
                # If schema matches fallback exactly, it was a fallback
                from src.tools.schema_tool import FALLBACK_SCHEMAS
                if columns == FALLBACK_SCHEMAS.get(table_name, []):
                    fallback_count += 1

            obs = RetrievalObservation(
                query="schema_fetch",
                docs_retrieved=len(result),
                top_scores=[],
                top_k_requested=len(self.tables),
                retrieval_time_ms=round(elapsed, 2),
                data_origin="bigquery_schema",
                no_relevant_docs=len(result) == 0,
            )
            _retrieval_store.add(obs)

            record_metric("schema_fetch_time_ms", elapsed)
            record_metric("schema_tables_fetched", len(result))
            record_metric("schema_fallback_count", fallback_count)

            if span is not None:
                span.attributes.update({
                    "tables_fetched": len(result),
                    "total_columns": total_columns,
                    "fallback_count": fallback_count,
                })

            return result
