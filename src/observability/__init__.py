"""Observability package – comprehensive instrumentation for the retail analytics agent.

8 blocks:
1. End-to-end tracing (tracer)
2. Structured logging (logger)
3. Operational metrics (metrics)
4. Retrieval observability – few-shot example selection (retrieval_observer)
5. Tool/action observability (tool_observer)
6. Quality evaluation (quality)
7. Security, privacy & compliance (security)
8. Versioning & comparison (versioning)
"""

from src.observability.decorators import span_context, traced
from src.observability.exporter import ObservabilityExporter
from src.observability.logger import get_logger, log_event, setup_logging
from src.observability.metrics import get_collector, get_metrics_summary, record_metric, reset_metrics
from src.observability.quality import QualityEvaluator
from src.observability.retrieval_observer import (
    ObservableGoldenRetriever,
    ObservableSchemaTool,
    get_retrieval_store,
    reset_retrieval_store,
)
from src.observability.security import SecurityObserver, get_security_observer, set_security_observer
from src.observability.tool_observer import (
    ObservableBigQueryRunner,
    ObservableLLMClient,
    ObservableSQLValidator,
    get_tool_observer,
    reset_tool_observer,
)
from src.observability.tracer import Tracer, TraceStore
from src.observability.versioning import VersionRegistry

__all__ = [
    # Tracing
    "Tracer",
    "TraceStore",
    "traced",
    "span_context",
    # Logging
    "setup_logging",
    "get_logger",
    "log_event",
    # Metrics
    "record_metric",
    "get_metrics_summary",
    "get_collector",
    "reset_metrics",
    # Tool observers
    "ObservableLLMClient",
    "ObservableBigQueryRunner",
    "ObservableSQLValidator",
    "get_tool_observer",
    "reset_tool_observer",
    # Retrieval observers (few-shot example selection & schema fetch)
    "ObservableGoldenRetriever",
    "ObservableSchemaTool",
    "get_retrieval_store",
    "reset_retrieval_store",
    # Quality
    "QualityEvaluator",
    # Security
    "SecurityObserver",
    "get_security_observer",
    "set_security_observer",
    # Versioning
    "VersionRegistry",
    # Export
    "ObservabilityExporter",
]
