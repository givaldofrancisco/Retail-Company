from __future__ import annotations

import re
from typing import Dict


ANALYTICS_HINTS = {
    "revenue",
    "sales",
    "trend",
    "products",
    "customers",
    "orders",
    "inventory",
    "spend",
    "compare",
    "monthly",
    "quarter",
    "top",
    "total",
    "performance",
    "branch",
    "store",
}

SCHEMA_HINTS = {"column", "columns", "schema", "structure", "fields"}
PII_HINTS = {"email", "e-mail", "mail", "phone", "phone number", "contact"}
INSTRUCTION_UPDATE_HINTS = {
    "change tone",
    "update persona",
    "system instructions",
    "from now on",
    "change style",
    "update instructions",
}

DESTRUCTIVE_PATTERNS = [
    r"\bdelete\b.*\breport",
    r"\bremove\b.*\breport",
    r"\bpurge\b.*\breport",
    r"\bdelete\s+all\b",
]


class Guardrails:
    def classify_intent(self, question: str) -> Dict[str, str]:
        q = question.strip().lower()

        if any(token in q for token in INSTRUCTION_UPDATE_HINTS):
            return {
                "intent": "instruction_update",
                "reason": "Detected request to update system instructions/tone.",
            }

        if any(re.search(pattern, q) for pattern in DESTRUCTIVE_PATTERNS):
            return {
                "intent": "destructive_report_op",
                "reason": "Detected destructive report management command; requires strict confirmation flow.",
            }

        if any(token in q for token in SCHEMA_HINTS):
            return {
                "intent": "schema_lookup",
                "reason": "Schema introspection request detected.",
            }

        if any(token in q for token in ANALYTICS_HINTS):
            return {"intent": "analysis", "reason": "Detected analysis intent."}

        return {
            "intent": "unsupported",
            "reason": "Only analysis questions about sales, inventory, customers, and schema are supported.",
        }

    @staticmethod
    def detect_pii_request(question: str) -> bool:
        q = question.lower()
        return any(token in q for token in PII_HINTS)
