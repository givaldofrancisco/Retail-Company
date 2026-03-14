"""Security, privacy & compliance observability.

Provides PII scrubbing of log payloads, prompt injection detection,
audit logging, and retention enforcement.
"""
from __future__ import annotations

import re
import time
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from src.observability.models import AuditEntry


# Common prompt injection patterns
_INJECTION_PATTERNS = [
    (re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.I), "ignore_instructions"),
    (re.compile(r"you\s+are\s+now\b", re.I), "role_override"),
    (re.compile(r"system\s*prompt", re.I), "system_prompt_leak"),
    (re.compile(r"pretend\s+you\s+are", re.I), "role_play"),
    (re.compile(r"\bDAN\b"), "DAN_jailbreak"),
    (re.compile(r"do\s+anything\s+now", re.I), "DAN_jailbreak"),
    (re.compile(r"disregard\s+(all\s+)?(your|the)\s+(rules|instructions)", re.I), "disregard_rules"),
]

# Patterns for secrets that must never appear in logs
_SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),          # Google API key
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*"),  # Bearer token
    re.compile(r"sk-[A-Za-z0-9]{20,}"),              # OpenAI-style key
    re.compile(r"ghp_[A-Za-z0-9]{36}"),              # GitHub PAT
    re.compile(r"AKIA[0-9A-Z]{16}"),                 # AWS access key
]

# PII patterns (email, phone) - reused from pii_masker logic
_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[\s\-.]?)?(?:\(?\d{2,4}\)?[\s\-.]?)\d{3,4}[\s\-.]?\d{3,4}\b")


class SecurityObserver:
    """Centralized security and audit observer."""

    def __init__(self, max_audit_entries: int = 5000) -> None:
        self._audit_log: deque[AuditEntry] = deque(maxlen=max_audit_entries)

    # ----- PII / Secret sanitization for log payloads -----

    def sanitize_log_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Deep-sanitize a log payload dict, masking PII and secrets in all string values."""
        return self._sanitize_dict(payload)

    def _sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {k: self._sanitize_value(v) for k, v in data.items()}

    def _sanitize_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._mask_string(value)
        if isinstance(value, dict):
            return self._sanitize_dict(value)
        if isinstance(value, list):
            return [self._sanitize_value(item) for item in value]
        return value

    @staticmethod
    def _mask_string(text: str) -> str:
        result = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
        result = _PHONE_RE.sub("[REDACTED_PHONE]", result)
        for pattern in _SECRET_PATTERNS:
            result = pattern.sub("[REDACTED_SECRET]", result)
        return result

    # ----- Prompt injection detection -----

    def detect_prompt_injection(self, text: str) -> Tuple[bool, str]:
        """Check text for known injection patterns. Returns (is_suspicious, reason)."""
        for pattern, reason in _INJECTION_PATTERNS:
            if pattern.search(text):
                return True, reason
        return False, ""

    # ----- Audit logging -----

    def record_audit(
        self,
        action: str,
        actor: str = "",
        trace_id: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = AuditEntry(
            timestamp=time.time(),
            action=action,
            actor=actor,
            trace_id=trace_id,
            details=self.sanitize_log_payload(details or {}),
        )
        self._audit_log.append(entry)

    @property
    def audit_log(self) -> List[AuditEntry]:
        return list(self._audit_log)

    # ----- Retention -----

    def enforce_retention(self, max_age_seconds: float = 86400) -> int:
        """Remove audit entries older than max_age_seconds. Returns count removed."""
        cutoff = time.time() - max_age_seconds
        removed = 0
        while self._audit_log and self._audit_log[0].timestamp < cutoff:
            self._audit_log.popleft()
            removed += 1
        return removed


# Module-level singleton (registered by app.py at startup)
_security_observer: Optional[SecurityObserver] = None


def get_security_observer() -> Optional[SecurityObserver]:
    return _security_observer


def set_security_observer(observer: SecurityObserver) -> None:
    global _security_observer
    _security_observer = observer
