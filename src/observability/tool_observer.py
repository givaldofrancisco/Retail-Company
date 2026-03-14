"""Tool / action observability – observable wrappers for LLM, BigQuery, SQL validator.

Each wrapper subclass adds timing, token counting, cost estimation and records
ToolInvocation entries via the ToolObserver singleton.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

import pandas as pd

from src.observability.decorators import span_context
from src.observability.metrics import record_metric
from src.observability.models import ToolInvocation

# ---------------------------------------------------------------------------
# ToolObserver – central registry of tool invocations
# ---------------------------------------------------------------------------


class ToolObserver:
    """Collects ToolInvocation records and provides summaries."""

    def __init__(self) -> None:
        self._invocations: List[ToolInvocation] = []

    def record(self, inv: ToolInvocation) -> None:
        self._invocations.append(inv)

    @property
    def invocations(self) -> List[ToolInvocation]:
        return list(self._invocations)

    def get_summary(self) -> Dict[str, Any]:
        by_tool: Dict[str, List[ToolInvocation]] = defaultdict(list)
        for inv in self._invocations:
            by_tool[inv.tool_name].append(inv)

        summary: Dict[str, Any] = {}
        for tool_name, items in by_tool.items():
            times = [i.execution_time_ms for i in items]
            successes = sum(1 for i in items if i.success)
            summary[tool_name] = {
                "call_count": len(items),
                "success_count": successes,
                "failure_count": len(items) - successes,
                "success_rate": successes / len(items) if items else 0,
                "avg_time_ms": sum(times) / len(times) if times else 0,
                "total_time_ms": sum(times),
                "error_types": list({i.error_type for i in items if i.error_type}),
            }
        return summary

    def detect_redundant_calls(self) -> List[str]:
        """Flag tool calls with identical arguments made more than once."""
        seen: Dict[str, int] = defaultdict(int)
        for inv in self._invocations:
            key = f"{inv.tool_name}:{inv.arguments}"
            seen[key] += 1
        return [k for k, v in seen.items() if v > 1]

    def reset(self) -> None:
        self._invocations.clear()


# Module singleton
_tool_observer = ToolObserver()


def get_tool_observer() -> ToolObserver:
    return _tool_observer


def reset_tool_observer() -> None:
    _tool_observer.reset()


# ---------------------------------------------------------------------------
# Gemini pricing (USD per 1M tokens) – Gemini 2.0 Flash approximate pricing
# ---------------------------------------------------------------------------

_PRICING: Dict[str, Dict[str, float]] = {
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    # Ollama models run local; cost is recorded as 0 for now.
    "qwen2.5": {"input": 0.0, "output": 0.0},
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    prices = _PRICING.get(model, _PRICING.get("gemini-2.0-flash", {"input": 0.10, "output": 0.40}))
    return (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000


# ---------------------------------------------------------------------------
# ObservableLLMClient – wraps LLMClient
# ---------------------------------------------------------------------------

from src.llm.client import LLMClient  # noqa: E402


class ObservableLLMClient(LLMClient):
    """LLMClient subclass that instruments every LLM invocation."""

    def _safe_invoke(self, prompt: str) -> Optional[str]:
        with span_context("llm_invoke", model=self.model_name) as span:
            start = time.perf_counter()
            success = True
            error_type = None
            error_msg = None
            input_tokens = output_tokens = 0
            result: Optional[str] = None

            try:
                response = self._client.invoke(prompt)
                result = str(response.content).strip()

                # Extract token usage from response metadata (Gemini)
                meta = getattr(response, "usage_metadata", None) or {}
                if isinstance(meta, dict):
                    input_tokens = meta.get("prompt_token_count", 0) or meta.get("input_tokens", 0)
                    output_tokens = meta.get("candidates_token_count", 0) or meta.get("output_tokens", 0)
                elif hasattr(meta, "prompt_token_count"):
                    input_tokens = getattr(meta, "prompt_token_count", 0)
                    output_tokens = getattr(meta, "candidates_token_count", 0)

                # Also check response_metadata
                resp_meta = getattr(response, "response_metadata", {}) or {}
                usage = resp_meta.get("usage_metadata", {})
                if usage and not input_tokens:
                    input_tokens = usage.get("prompt_token_count", 0)
                    output_tokens = usage.get("candidates_token_count", 0)
                # Generic token usage shape fallback
                token_usage = resp_meta.get("token_usage", {}) or {}
                if token_usage and not input_tokens:
                    input_tokens = token_usage.get("prompt_tokens", 0) or token_usage.get("input_tokens", 0)
                    output_tokens = token_usage.get("completion_tokens", 0) or token_usage.get("output_tokens", 0)

            except Exception as exc:
                success = False
                error_type = type(exc).__name__
                error_msg = str(exc)[:500]
                logging.getLogger(__name__).warning("LLM invoke failed; using fallback: %s", exc)
                result = None

            elapsed = (time.perf_counter() - start) * 1000
            cost = _estimate_cost(self.model_name, input_tokens, output_tokens)

            # Record metrics
            record_metric("llm_latency_ms", elapsed, model=self.model_name)
            record_metric("llm_input_tokens", input_tokens, model=self.model_name)
            record_metric("llm_output_tokens", output_tokens, model=self.model_name)
            record_metric("llm_cost_usd", cost, model=self.model_name)
            if not success:
                record_metric("llm_error_count", 1, model=self.model_name)

            # Span attributes
            if span is not None:
                span.attributes.update({
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": round(cost, 6),
                    "model": self.model_name,
                })

            # Record tool invocation
            _tool_observer.record(ToolInvocation(
                tool_name="llm_invoke",
                arguments={"prompt_len": len(prompt), "model": self.model_name},
                response_summary=f"tokens_in={input_tokens}, tokens_out={output_tokens}",
                execution_time_ms=elapsed,
                success=success,
                error_type=error_type,
                error_message=error_msg,
                node_name="",  # filled by caller context
            ))

            return result

    def generate_sql(self, question: str, schemas: Dict[str, Any], golden_examples: List[Dict[str, Any]]) -> str:
        result = super().generate_sql(question, schemas, golden_examples)
        # Track if fallback was used
        if not self.enabled:
            record_metric("llm_fallback_used", 1, reason="llm_disabled")
            _tool_observer.record(ToolInvocation(
                tool_name="llm_heuristic_fallback",
                arguments={"question_len": len(question)},
                response_summary="heuristic_sql_used",
                execution_time_ms=0,
                success=True,
                node_name="generate_sql",
                reason="llm_disabled",
            ))
        return result

    def repair_sql(self, question: str, failed_sql: str, error_message: str,
                   schemas: Dict[str, Any], golden_examples: List[Dict[str, Any]]) -> str:
        result = super().repair_sql(question, failed_sql, error_message, schemas, golden_examples)
        if not self.enabled:
            record_metric("llm_fallback_used", 1, reason="llm_disabled_repair")
        return result

    def generate_report(self, question: str, row_count: int, data_preview: List[Dict[str, Any]],
                        persona_text: str, preference_format: str,
                        golden_examples: List[Dict[str, Any]]) -> str:
        result = super().generate_report(question, row_count, data_preview,
                                         persona_text, preference_format, golden_examples)
        if not self.enabled:
            record_metric("llm_fallback_used", 1, reason="llm_disabled_report")
        return result


# ---------------------------------------------------------------------------
# ObservableBigQueryRunner – wraps BigQueryRunner
# ---------------------------------------------------------------------------

from src.tools.bigquery_runner import BigQueryExecutionError, BigQueryRunner  # noqa: E402


class ObservableBigQueryRunner(BigQueryRunner):
    """BigQueryRunner subclass that instruments query execution."""

    def execute_query(self, sql_query: str) -> pd.DataFrame:
        with span_context("bq_execute", sql_len=len(sql_query)) as span:
            start = time.perf_counter()
            success = True
            error_type = None
            error_msg = None
            row_count = 0

            try:
                df = super().execute_query(sql_query)
                row_count = len(df)
                return df
            except BigQueryExecutionError as exc:
                success = False
                error_type = "BigQueryExecutionError"
                error_msg = str(exc)[:500]
                raise
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                record_metric("bq_query_time_ms", elapsed)
                record_metric("bq_rows_returned", row_count)
                if not success:
                    record_metric("bq_error_count", 1)

                if span is not None:
                    span.attributes.update({
                        "rows_returned": row_count,
                        "sql_length": len(sql_query),
                    })

                _tool_observer.record(ToolInvocation(
                    tool_name="bigquery_execute",
                    arguments={"sql_len": len(sql_query)},
                    response_summary=f"rows={row_count}",
                    execution_time_ms=elapsed,
                    success=success,
                    error_type=error_type,
                    error_message=error_msg,
                    node_name="execute_sql",
                ))

    def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        with span_context("bq_get_schema", table=table_name) as span:
            start = time.perf_counter()
            success = True
            error_type = None

            try:
                result = super().get_table_schema(table_name)
                if span is not None:
                    span.attributes["column_count"] = len(result)
                return result
            except Exception as exc:
                success = False
                error_type = type(exc).__name__
                raise
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                record_metric("bq_schema_time_ms", elapsed, table=table_name)

                _tool_observer.record(ToolInvocation(
                    tool_name="bigquery_get_schema",
                    arguments={"table": table_name},
                    response_summary="ok" if success else error_type or "error",
                    execution_time_ms=elapsed,
                    success=success,
                    error_type=error_type,
                    node_name="load_schema",
                ))


# ---------------------------------------------------------------------------
# ObservableSQLValidator – wraps SQLValidator
# ---------------------------------------------------------------------------

from src.tools.sql_validator import SQLValidationError, SQLValidator  # noqa: E402


class ObservableSQLValidator(SQLValidator):
    """SQLValidator subclass that instruments validation."""

    def validate_and_rewrite(self, sql: str) -> str:
        with span_context("sql_validate", sql_len=len(sql)) as span:
            start = time.perf_counter()
            success = True
            error_type = None
            error_msg = None

            try:
                result = super().validate_and_rewrite(sql)
                return result
            except SQLValidationError as exc:
                success = False
                error_type = "SQLValidationError"
                error_msg = str(exc)[:500]
                raise
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                record_metric("validation_time_ms", elapsed)
                if not success:
                    record_metric("validation_error_count", 1)

                if span is not None:
                    span.attributes["validation_success"] = success

                _tool_observer.record(ToolInvocation(
                    tool_name="sql_validator",
                    arguments={"sql_len": len(sql)},
                    response_summary="valid" if success else (error_msg or "invalid"),
                    execution_time_ms=elapsed,
                    success=success,
                    error_type=error_type,
                    error_message=error_msg,
                    node_name="validate_sql",
                ))
