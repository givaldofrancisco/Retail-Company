"""Central data models for the observability system.

All dataclasses live here to avoid circular imports between modules.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------

@dataclass
class SpanEvent:
    """Timestamped annotation within a span."""
    timestamp: float
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Span:
    """A single unit of work inside a trace (e.g., one workflow node)."""
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = ""
    name: str = ""
    parent_span_id: Optional[str] = None
    start_time: float = 0.0
    end_time: Optional[float] = None
    status: Literal["ok", "error", "timeout"] = "ok"
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[SpanEvent] = field(default_factory=list)

    @property
    def duration_ms(self) -> Optional[float]:
        if self.end_time is not None:
            return (self.end_time - self.start_time) * 1000
        return None


@dataclass
class TraceMetadata:
    """Immutable metadata attached to every trace."""
    agent_version: str = ""
    prompt_version: str = ""
    model_name: str = ""
    workflow_version: str = ""
    question: str = ""
    final_status: Optional[str] = None


@dataclass
class Trace:
    """End-to-end record of a single user request execution."""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    conversation_id: str = ""
    user_id: str = ""
    start_time: float = 0.0
    end_time: Optional[float] = None
    spans: List[Span] = field(default_factory=list)
    metadata: TraceMetadata = field(default_factory=TraceMetadata)

    @property
    def duration_ms(self) -> Optional[float]:
        if self.end_time is not None:
            return (self.end_time - self.start_time) * 1000
        return None


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@dataclass
class MetricPoint:
    """A single numeric measurement."""
    name: str
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tool Observability
# ---------------------------------------------------------------------------

@dataclass
class ToolInvocation:
    """Record of a single tool call."""
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    response_summary: str = ""
    execution_time_ms: float = 0.0
    success: bool = True
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    node_name: str = ""
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Retrieval Observability (few-shot example selection & schema fetch)
# ---------------------------------------------------------------------------

@dataclass
class RetrievalObservation:
    """Record of a retrieval operation (few-shot example selection or schema fetch).

    Note: despite the class name, this project does NOT use a vector-store /
    embedding-based RAG system.  GoldenRetriever performs token-overlap
    matching against hardcoded examples in golden_trios.json.
    """
    query: str = ""
    docs_retrieved: int = 0
    top_scores: List[float] = field(default_factory=list)
    top_k_requested: int = 0
    retrieval_time_ms: float = 0.0
    data_origin: str = ""
    no_relevant_docs: bool = False


# ---------------------------------------------------------------------------
# Quality Evaluation
# ---------------------------------------------------------------------------

@dataclass
class QualitySignal:
    """Quality evaluation of a single execution."""
    trace_id: str = ""
    groundedness: Optional[float] = None
    relevance: Optional[float] = None
    completeness: Optional[float] = None
    tool_success_final_success: bool = False
    used_fallback: bool = False
    empty_response: bool = False
    user_feedback: Optional[str] = None


# ---------------------------------------------------------------------------
# Security & Audit
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    """Record of an auditable action."""
    timestamp: float = 0.0
    action: str = ""
    actor: str = ""
    trace_id: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

@dataclass
class VersionSnapshot:
    """Hash-based snapshot of all versioned components."""
    version_id: str = ""
    timestamp: float = 0.0
    components: Dict[str, str] = field(default_factory=dict)
