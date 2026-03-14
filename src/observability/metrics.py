"""Operational metrics collection and aggregation."""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.observability.models import MetricPoint


class MetricsCollector:
    """Collects numeric metrics and provides aggregation."""

    MAX_POINTS = 10_000

    def __init__(self) -> None:
        self._points: List[MetricPoint] = []

    def record(self, name: str, value: float, **labels: str) -> None:
        if len(self._points) >= self.MAX_POINTS:
            self._points = self._points[-(self.MAX_POINTS // 2):]
        self._points.append(MetricPoint(
            name=name,
            value=value,
            timestamp=time.perf_counter(),
            labels=labels,
        ))

    def get_summary(self, name: Optional[str] = None) -> Dict[str, Any]:
        grouped: Dict[str, List[float]] = defaultdict(list)
        for pt in self._points:
            if name and pt.name != name:
                continue
            grouped[pt.name].append(pt.value)

        summary: Dict[str, Any] = {}
        for metric_name, values in grouped.items():
            values_sorted = sorted(values)
            n = len(values_sorted)
            summary[metric_name] = {
                "count": n,
                "sum": sum(values_sorted),
                "mean": sum(values_sorted) / n,
                "min": values_sorted[0],
                "max": values_sorted[-1],
                "p50": values_sorted[n // 2],
                "p95": values_sorted[int(n * 0.95)] if n >= 2 else values_sorted[-1],
            }
        return summary

    def get_points(self, name: Optional[str] = None) -> List[MetricPoint]:
        if name:
            return [p for p in self._points if p.name == name]
        return list(self._points)

    def export_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "summary": self.get_summary(),
            "points": [
                {"name": p.name, "value": p.value, "timestamp": p.timestamp, "labels": p.labels}
                for p in self._points
            ],
        }
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def reset(self) -> None:
        self._points.clear()


# Module-level singleton
_collector = MetricsCollector()


def record_metric(name: str, value: float, **labels: str) -> None:
    _collector.record(name, value, **labels)


def get_metrics_summary(name: Optional[str] = None) -> Dict[str, Any]:
    return _collector.get_summary(name)


def get_collector() -> MetricsCollector:
    return _collector


def reset_metrics() -> None:
    _collector.reset()
