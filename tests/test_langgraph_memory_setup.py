import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_assignment_acceptance import _build_test_app
from src.graph.state import new_state


def test_workflow_compiles_with_langgraph_memory_components(tmp_path):
    app, *_ = _build_test_app(tmp_path)
    assert getattr(app, "checkpointer", None) is not None
    assert getattr(app, "store", None) is not None


def test_invoke_with_thread_id_config_works(tmp_path):
    app, *_ = _build_test_app(tmp_path)
    result = app.invoke(
        new_state(question="What are the top products by revenue?", user_id="manager_a"),
        config={"configurable": {"thread_id": "manager_a:test"}},
    )
    assert result["final_status"] == "success"
