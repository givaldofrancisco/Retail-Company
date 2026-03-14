from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


@dataclass
class ReportActionStore:
    reports_path: Path
    pending_path: Path
    token_ttl_seconds: int = 600

    def __post_init__(self) -> None:
        self.reports_path.parent.mkdir(parents=True, exist_ok=True)
        self.pending_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.reports_path.exists():
            self._save_json(self.reports_path, self._seed_reports())
        if not self.pending_path.exists():
            self.pending_path.write_text("[]", encoding="utf-8")

    def start_delete_flow(self, user_id: str, raw_question: str, scope: str) -> Dict[str, Any]:
        reports = self._load_json(self.reports_path)
        matching = self._matching_reports(reports, scope)
        token = self._generate_token()

        pending = self._load_json(self.pending_path)
        pending.append(
            {
                "token": token,
                "user_id": user_id,
                "scope": scope,
                "scope_hash": self._scope_hash(scope),
                "created_at": int(time.time()),
                "expires_at": int(time.time()) + self.token_ttl_seconds,
                "raw_question": raw_question,
            }
        )
        self._save_json(self.pending_path, pending)

        return {
            "token": token,
            "scope": scope,
            "preview_count": len(matching),
        }

    def confirm_delete(self, token: str, user_id: str) -> Tuple[bool, str]:
        pending = self._load_json(self.pending_path)
        now = int(time.time())

        match = None
        for item in pending:
            if item.get("token") == token:
                match = item
                break

        if match is None:
            return False, "Invalid confirmation token."
        if match.get("user_id") != user_id:
            return False, "This token belongs to a different user."
        if now > int(match.get("expires_at", 0)):
            pending = [item for item in pending if item.get("token") != token]
            self._save_json(self.pending_path, pending)
            return False, "Confirmation token expired. Please issue the delete command again."

        scope = str(match.get("scope", "")).strip()
        reports = self._load_json(self.reports_path)
        kept: List[Dict[str, Any]] = []
        deleted_count = 0
        for report in reports:
            if self._matches_scope(report, scope):
                deleted_count += 1
            else:
                kept.append(report)
        self._save_json(self.reports_path, kept)

        pending = [item for item in pending if item.get("token") != token]
        self._save_json(self.pending_path, pending)

        return True, f"Deleted {deleted_count} saved report(s) matching '{scope}'."

    @staticmethod
    def extract_scope(question: str) -> str:
        cleaned = " ".join(question.strip().split())
        lowered = cleaned.lower()
        for marker in ("mentioning ", "containing ", "about "):
            idx = lowered.find(marker)
            if idx != -1:
                return cleaned[idx + len(marker) :].strip(" .\"'")
        return cleaned

    @staticmethod
    def _generate_token() -> str:
        return f"DEL-{secrets.token_hex(3).upper()}"

    @staticmethod
    def _scope_hash(scope: str) -> str:
        return hashlib.sha256(scope.lower().encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _matches_scope(report: Dict[str, Any], scope: str) -> bool:
        haystack = f"{report.get('title', '')} {report.get('content', '')}".lower()
        return scope.lower() in haystack

    def _matching_reports(self, reports: List[Dict[str, Any]], scope: str) -> List[Dict[str, Any]]:
        return [report for report in reports if self._matches_scope(report, scope)]

    @staticmethod
    def _load_json(path: Path) -> List[Dict[str, Any]]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _save_json(path: Path, payload: List[Dict[str, Any]]) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _seed_reports() -> List[Dict[str, Any]]:
        return [
            {
                "id": "rpt-001",
                "title": "Client X weekly revenue snapshot",
                "content": "Revenue summary and anomalies for Client X across stores.",
            },
            {
                "id": "rpt-002",
                "title": "Top products by region",
                "content": "Regional product ranking and trend notes.",
            },
            {
                "id": "rpt-003",
                "title": "Client X churn watchlist",
                "content": "Retention risk report for Client X segment.",
            },
        ]
