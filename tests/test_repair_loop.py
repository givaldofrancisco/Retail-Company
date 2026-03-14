from src.graph.state import AgentState
from src.graph.workflow import route_after_execute


def test_route_repair_when_error_and_retries_remaining():
    state = AgentState(error_message="syntax error", retry_count=0, max_retries=2)
    assert route_after_execute(state) == "repair_sql"


def test_route_finalize_when_error_and_retries_exhausted():
    state = AgentState(error_message="syntax error", retry_count=2, max_retries=2)
    assert route_after_execute(state) == "finalize_response"


def test_route_sanitize_when_no_error():
    state = AgentState(error_message="", retry_count=0, max_retries=2)
    assert route_after_execute(state) == "sanitize_results"
