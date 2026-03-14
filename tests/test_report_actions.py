from __future__ import annotations

import json
from pathlib import Path

from src.memory.report_actions import ReportActionStore


def _new_store(tmp_path: Path) -> ReportActionStore:
    return ReportActionStore(
        reports_path=tmp_path / "saved_reports.json",
        pending_path=tmp_path / "pending_actions.json",
        token_ttl_seconds=600,
    )


def test_start_delete_flow_creates_token_and_preview(tmp_path):
    store = _new_store(tmp_path)
    flow = store.start_delete_flow(
        user_id="manager_a",
        raw_question="Delete all reports mentioning Client X",
        scope="Client X",
    )

    assert flow["token"].startswith("DEL-")
    assert flow["preview_count"] == 2

    pending = json.loads((tmp_path / "pending_actions.json").read_text(encoding="utf-8"))
    assert len(pending) == 1
    assert pending[0]["user_id"] == "manager_a"


def test_confirm_delete_deletes_only_matching_reports(tmp_path):
    store = _new_store(tmp_path)
    flow = store.start_delete_flow(
        user_id="manager_a",
        raw_question="Delete all reports mentioning Client X",
        scope="Client X",
    )

    ok, message = store.confirm_delete(token=flow["token"], user_id="manager_a")
    assert ok is True
    assert "Deleted 2 saved report(s)" in message

    reports = json.loads((tmp_path / "saved_reports.json").read_text(encoding="utf-8"))
    assert len(reports) == 1
    assert reports[0]["id"] == "rpt-002"


def test_confirm_delete_rejects_invalid_token(tmp_path):
    store = _new_store(tmp_path)
    ok, message = store.confirm_delete(token="DEL-XXXXXX", user_id="manager_a")
    assert ok is False
    assert "Invalid confirmation token" in message
