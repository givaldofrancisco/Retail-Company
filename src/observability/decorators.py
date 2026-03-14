"""Instrumentation primitives: @traced decorator and span_context manager."""
from __future__ import annotations

import functools
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

from src.observability.metrics import record_metric
from src.observability.models import Span
from src.observability.tracer import Tracer


def traced(node_name: str | None = None):
    """Decorator for WorkflowNodes methods.

    Creates a span at entry, records latency, captures errors.
    Expects the first positional arg after ``self`` to be ``state: AgentState``.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, state, *args, **kwargs):
            ctx = Tracer.get_current()
            name = node_name or func.__name__

            if ctx is None:
                return func(self, state, *args, **kwargs)

            attrs: Dict[str, Any] = {}
            if isinstance(state, dict):
                attrs["request_id"] = state.get("request_id", "")
                attrs["user_id"] = state.get("user_id", "")

            span = ctx.start_span(name, attributes=attrs)
            start = time.perf_counter()
            try:
                result = func(self, state, *args, **kwargs)
                ctx.end_span(span, status="ok")
                return result
            except Exception as exc:
                span.attributes["error_type"] = type(exc).__name__
                span.attributes["error_message"] = str(exc)[:500]
                ctx.end_span(span, status="error")
                record_metric("error_count", 1, node=name)
                raise
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                span.attributes["latency_ms"] = round(elapsed, 2)
                record_metric("node_latency_ms", elapsed, node=name)

        return wrapper
    return decorator


@contextmanager
def span_context(name: str, **attributes: Any):
    """Context manager for sub-spans within a node (e.g., an LLM call)."""
    ctx = Tracer.get_current()
    if ctx is None:
        yield None
        return

    span = ctx.start_span(name, attributes=attributes)
    start = time.perf_counter()
    try:
        yield span
        ctx.end_span(span, status="ok")
    except Exception as exc:
        span.attributes["error_type"] = type(exc).__name__
        span.attributes["error_message"] = str(exc)[:500]
        ctx.end_span(span, status="error")
        raise
    finally:
        elapsed = (time.perf_counter() - start) * 1000
        span.attributes["latency_ms"] = round(elapsed, 2)
        record_metric(f"{name}_latency_ms", elapsed)
