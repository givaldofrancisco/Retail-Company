from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict


FinalStatus = Literal[
    "success",
    "rejected",
    "requires_confirmation",
    "failed_validation",
    "failed_execution",
    "empty_result",
]


class AgentState(TypedDict, total=False):
    request_id: str
    user_id: str
    question: str
    intent: str
    intent_reason: str
    retry_count: int
    max_retries: int

    schema_context: Dict[str, Any]
    golden_examples: List[Dict[str, Any]]

    sql_candidate: str
    validated_sql: str
    sql_error: str

    result_rows: List[Dict[str, Any]]
    result_columns: List[str]
    row_count: int
    removed_pii_columns: List[str]
    pii_request: bool

    final_report: str
    final_status: FinalStatus
    error_message: str


DEFAULT_MAX_RETRIES = 2


def new_state(question: str, user_id: str, max_retries: Optional[int] = None) -> AgentState:
    return AgentState(
        request_id="",
        user_id=user_id,
        question=question,
        intent="",
        intent_reason="",
        retry_count=0,
        max_retries=DEFAULT_MAX_RETRIES if max_retries is None else max_retries,
        schema_context={},
        golden_examples=[],
        # Reset per-request fields so LangGraph checkpointed state does not leak debug info.
        sql_candidate="",
        validated_sql="",
        sql_error="",
        result_rows=[],
        result_columns=[],
        row_count=0,
        removed_pii_columns=[],
        pii_request=False,
        final_report="",
        final_status="",
        error_message="",
    )
