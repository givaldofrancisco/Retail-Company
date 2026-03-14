"""Session export – serializes all observability data to a single JSON file."""
from __future__ import annotations

import dataclasses
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.observability.metrics import MetricsCollector
from src.observability.models import (
    AuditEntry,
    QualitySignal,
    RetrievalObservation,
    Trace,
    ToolInvocation,
    VersionSnapshot,
)


def _to_dict(obj: Any) -> Any:
    """Recursively convert dataclasses and known types to JSON-serializable dicts."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


class ObservabilityExporter:
    """Exports a complete observability session to a JSON file."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def export_session(
        self,
        session_id: str,
        traces: List[Trace],
        metrics_collector: MetricsCollector,
        tool_invocations: List[ToolInvocation],
        tool_summary: Dict[str, Any],
        retrieval_observations: List[RetrievalObservation],
        retrieval_summary: Dict[str, Any],
        quality_signals: List[QualitySignal],
        quality_summary: Dict[str, Any],
        audit_log: List[AuditEntry],
        version_snapshot: Optional[VersionSnapshot],
    ) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"observability_{ts}.json"

        data = {
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "version_snapshot": _to_dict(version_snapshot) if version_snapshot else None,
            "traces": _to_dict(traces),
            "metrics_summary": metrics_collector.get_summary(),
            "tool_invocations_summary": tool_summary,
            "tool_invocations": _to_dict(tool_invocations),
            "retrieval_observations_summary": retrieval_summary,
            "retrieval_observations": _to_dict(retrieval_observations),
            "quality_summary": quality_summary,
            "quality_signals": _to_dict(quality_signals),
            "audit_log": _to_dict(audit_log),
        }

        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    @staticmethod
    def format_cli_summary(
        traces: List[Trace],
        metrics_summary: Dict[str, Any],
        tool_summary: Dict[str, Any],
        quality_summary: Dict[str, Any],
    ) -> str:
        """Format a concise summary for CLI output."""
        lines = ["", "=" * 60, " OBSERVABILITY SUMMARY", "=" * 60]

        # Traces
        lines.append(f"\n  Traces completed: {len(traces)}")
        for trace in traces[-5:]:  # last 5
            dur = f"{trace.duration_ms:.0f}ms" if trace.duration_ms else "?"
            status = trace.metadata.final_status or "unknown"
            lines.append(f"    [{status}] {dur} - {len(trace.spans)} spans")

        # Key metrics
        if metrics_summary:
            lines.append("\n  Key Metrics:")
            for name in ["node_latency_ms", "llm_latency_ms", "bq_query_time_ms",
                         "llm_input_tokens", "llm_output_tokens", "llm_cost_usd"]:
                if name in metrics_summary:
                    m = metrics_summary[name]
                    lines.append(f"    {name}: avg={m['mean']:.2f} p95={m['p95']:.2f} count={m['count']}")

        # Tool summary
        if tool_summary:
            lines.append("\n  Tool Invocations:")
            for tool, stats in tool_summary.items():
                lines.append(
                    f"    {tool}: calls={stats['call_count']} "
                    f"success_rate={stats['success_rate']:.0%} "
                    f"avg_time={stats['avg_time_ms']:.0f}ms"
                )

        # Quality
        if quality_summary:
            lines.append("\n  Quality:")
            for key in ["avg_groundedness", "avg_relevance", "avg_completeness",
                        "success_rate", "fallback_rate"]:
                val = quality_summary.get(key)
                if val is not None:
                    lines.append(f"    {key}: {val:.3f}")

        lines.append("=" * 60)
        return "\n".join(lines)
