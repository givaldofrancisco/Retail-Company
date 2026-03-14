from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


@dataclass
class LearningLoopStore:
    candidates_path: Path
    golden_path: Path

    def __post_init__(self) -> None:
        self.candidates_path.parent.mkdir(parents=True, exist_ok=True)
        self.golden_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.candidates_path.exists():
            self.candidates_path.write_text("[]", encoding="utf-8")
        if not self.golden_path.exists():
            self.golden_path.write_text("[]", encoding="utf-8")

    def capture_candidate(self, question: str, sql: str, report: str) -> Tuple[bool, str]:
        signature = self._signature(question=question, sql=sql)
        candidates = self._load(self.candidates_path)

        for item in candidates:
            if item.get("signature") == signature:
                return False, str(item.get("id", ""))

        candidate_id = f"cand-{int(time.time() * 1000)}"
        candidates.append(
            {
                "id": candidate_id,
                "signature": signature,
                "question": question,
                "sql": sql,
                "report": report[:2000],
                "tags": self._tags(question),
                "created_at": int(time.time()),
                "status": "pending",
            }
        )
        self._save(self.candidates_path, candidates)
        return True, candidate_id

    def list_pending(self, limit: int = 10) -> List[Dict[str, Any]]:
        candidates = self._load(self.candidates_path)
        pending = [item for item in candidates if item.get("status") == "pending"]
        return pending[:limit]

    def approve_candidate(self, candidate_id: str) -> Tuple[bool, str]:
        candidates = self._load(self.candidates_path)
        selected = None
        for item in candidates:
            if item.get("id") == candidate_id:
                selected = item
                break

        if selected is None:
            return False, "Candidate not found."
        if selected.get("status") == "approved":
            return False, "Candidate already approved."

        golden = self._load(self.golden_path)
        if not any(self._signature(entry.get("question", ""), entry.get("sql", "")) == selected.get("signature") for entry in golden):
            golden.append(
                {
                    "question": selected.get("question", ""),
                    "sql": selected.get("sql", ""),
                    "report": selected.get("report", ""),
                    "tags": selected.get("tags", []),
                }
            )
            self._save(self.golden_path, golden)

        for item in candidates:
            if item.get("id") == candidate_id:
                item["status"] = "approved"
                item["approved_at"] = int(time.time())
                break
        self._save(self.candidates_path, candidates)
        return True, "Candidate approved and promoted to golden bucket."

    @staticmethod
    def _signature(question: str, sql: str) -> str:
        raw = f"{question.strip().lower()}::{sql.strip().lower()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _tags(question: str) -> List[str]:
        tokens = [token.lower() for token in question.replace("?", " ").split()]
        keep = []
        for token in tokens:
            cleaned = "".join(ch for ch in token if ch.isalnum() or ch == "_")
            if len(cleaned) >= 4 and cleaned not in keep:
                keep.append(cleaned)
        return keep[:6]

    @staticmethod
    def _load(path: Path) -> List[Dict[str, Any]]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _save(path: Path, payload: List[Dict[str, Any]]) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
