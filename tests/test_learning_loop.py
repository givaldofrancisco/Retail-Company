from __future__ import annotations

import json
from pathlib import Path

from src.memory.learning_loop import LearningLoopStore


def _new_store(tmp_path: Path) -> LearningLoopStore:
    golden_path = tmp_path / "golden_trios.json"
    golden_path.write_text("[]", encoding="utf-8")
    return LearningLoopStore(
        candidates_path=tmp_path / "learning_candidates.json",
        golden_path=golden_path,
    )


def test_capture_candidate_adds_pending_item(tmp_path):
    store = _new_store(tmp_path)
    created, candidate_id = store.capture_candidate(
        question="What are the top products by revenue?",
        sql="SELECT 1",
        report="Summary",
    )
    assert created is True
    assert candidate_id.startswith("cand-")

    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0]["id"] == candidate_id


def test_capture_candidate_deduplicates_same_signature(tmp_path):
    store = _new_store(tmp_path)
    created_1, _ = store.capture_candidate("Q1", "SELECT 1", "R1")
    created_2, _ = store.capture_candidate("Q1", "SELECT 1", "R2")
    assert created_1 is True
    assert created_2 is False
    assert len(store.list_pending()) == 1


def test_approve_candidate_promotes_to_golden(tmp_path):
    store = _new_store(tmp_path)
    created, candidate_id = store.capture_candidate("Q2", "SELECT 2", "R2")
    assert created is True

    ok, message = store.approve_candidate(candidate_id)
    assert ok is True
    assert "promoted" in message.lower()

    golden = json.loads((tmp_path / "golden_trios.json").read_text(encoding="utf-8"))
    assert len(golden) == 1
    assert golden[0]["question"] == "Q2"
