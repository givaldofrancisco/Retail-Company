import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.graph.state import new_state
from tests.test_assignment_acceptance import _build_test_app


def test_manual_cli_inputs_replay_top_level_statuses(tmp_path):
    app, _nodes, pref_store, _fake_llm, _fake_bq, _fake_report = _build_test_app(tmp_path)
    inputs_file = ROOT / "tests" / "manual_cli_inputs_en.txt"
    prompts = [line.strip() for line in inputs_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    statuses = []
    for prompt in prompts:
        lower = prompt.lower()
        if lower in {"exit", "quit"}:
            continue
        if lower.startswith("/format "):
            pref_store.set_format("manager_a", lower.split(" ", 1)[1])
            continue

        result = app.invoke(
            new_state(question=prompt, user_id="manager_a"),
            config={"configurable": {"thread_id": "manual-cli-replay"}},
        )
        statuses.append(result.get("final_status"))

    assert statuses == [
        "success",  # top products
        "success",  # monthly trend
        "success",  # top customers
        "success",  # schema
        "success",  # pii email request -> safe aggregate
        "success",  # pii phone request -> safe aggregate
        "requires_confirmation",  # destructive op
        "rejected",  # unsupported weather
        "success",  # compare after /format table
        "success",  # compare after /format bullets
    ]
