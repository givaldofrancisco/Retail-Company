"""End-to-end tracing with spans via contextvars.

Usage:
    tracer = Tracer()
    ctx = tracer.begin_trace(session_id="s1", user_id="u1", metadata=TraceMetadata(...))
    # ... spans are created by @traced decorator or span_context ...
    trace = tracer.end_trace()
"""
from __future__ import annotations

import time
import uuid
from collections import deque
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from src.observability.models import Span, SpanEvent, Trace, TraceMetadata


_current_context: ContextVar[Optional["TraceContext"]] = ContextVar(
    "_current_context", default=None,
)


class TraceContext:
    """Manages the active trace and its span stack for a single execution."""

    def __init__(self, trace: Trace) -> None:
        self.trace = trace
        self._span_stack: List[Span] = []

    def start_span(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> Span:
        parent_id = self._span_stack[-1].span_id if self._span_stack else None
        span = Span(
            span_id=str(uuid.uuid4()),
            trace_id=self.trace.trace_id,
            name=name,
            parent_span_id=parent_id,
            start_time=time.perf_counter(),
            attributes=attributes or {},
        )
        self._span_stack.append(span)
        self.trace.spans.append(span)
        return span

    def end_span(self, span: Span, status: str = "ok") -> None:
        span.end_time = time.perf_counter()
        span.status = status  # type: ignore[assignment]
        if self._span_stack and self._span_stack[-1].span_id == span.span_id:
            self._span_stack.pop()

    def add_event(self, span: Span, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        span.events.append(SpanEvent(
            timestamp=time.perf_counter(),
            name=name,
            attributes=attributes or {},
        ))

    @property
    def current_span(self) -> Optional[Span]:
        return self._span_stack[-1] if self._span_stack else None


class TraceStore:
    """In-memory store for completed traces with cap."""

    def __init__(self, max_traces: int = 100) -> None:
        self._traces: deque[Trace] = deque(maxlen=max_traces)

    def add(self, trace: Trace) -> None:
        self._traces.append(trace)

    @property
    def traces(self) -> List[Trace]:
        return list(self._traces)

    def clear(self) -> None:
        self._traces.clear()


class Tracer:
    """Factory that creates and manages trace contexts."""

    def __init__(self, store: Optional[TraceStore] = None) -> None:
        self.store = store or TraceStore()

    def begin_trace(
        self,
        session_id: str = "",
        conversation_id: str = "",
        user_id: str = "",
        metadata: Optional[TraceMetadata] = None,
    ) -> TraceContext:
        trace = Trace(
            trace_id=str(uuid.uuid4()),
            session_id=session_id,
            conversation_id=conversation_id,
            user_id=user_id,
            start_time=time.perf_counter(),
            metadata=metadata or TraceMetadata(),
        )
        ctx = TraceContext(trace)
        _current_context.set(ctx)
        return ctx

    def end_trace(self) -> Trace:
        ctx = _current_context.get()
        if ctx is None:
            raise RuntimeError("No active trace context")
        ctx.trace.end_time = time.perf_counter()
        self.store.add(ctx.trace)
        _current_context.set(None)
        return ctx.trace

    @staticmethod
    def get_current() -> Optional[TraceContext]:
        return _current_context.get()
