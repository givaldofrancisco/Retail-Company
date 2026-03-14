from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Set


class SQLValidationError(ValueError):
    pass


BLOCKED_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "merge",
    "truncate",
    "create",
    "execute",
    "call",
    "grant",
    "revoke",
}

TABLE_REF_REGEX = re.compile(r"(?i)\b(FROM|JOIN)\s+((?:`?[a-zA-Z0-9_.-]+`?\.)*`?[a-zA-Z0-9_.-]+`?)")
CTE_NAME_REGEX = re.compile(r"(?i)\bwith\s+(.*?)\s+select", re.DOTALL)
CTE_EXTRACT_REGEX = re.compile(r"(?i)\b([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s*\(")


@dataclass
class SQLValidator:
    allowed_dataset: str
    allowed_tables: Set[str]
    default_limit: int = 200

    _allowed_project: str | None = None
    _allowed_dataset_id: str = ""

    def __post_init__(self) -> None:
        parts = self.allowed_dataset.split(".")
        if len(parts) == 2:
            self._allowed_project = parts[0]
            self._allowed_dataset_id = parts[1]
        else:
            self._allowed_project = None
            self._allowed_dataset_id = parts[-1]

    def validate_and_rewrite(self, sql: str) -> str:
        self._ensure_no_blocked_keywords(sql)
        candidate = self._extract_sql(sql)
        self._ensure_single_statement(candidate)
        self._ensure_select_only(candidate)
        cte_names = self._extract_cte_names(candidate)
        candidate = self._qualify_and_validate_tables(candidate, cte_names)
        candidate = self._append_limit_if_missing(candidate)
        return candidate.strip()

    def _extract_sql(self, raw: str) -> str:
        text = raw.strip()
        fenced = re.search(r"```(?:sql)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()

        select_pos = re.search(r"(?i)\b(select|with)\b", text)
        if not select_pos:
            raise SQLValidationError("No SELECT/WITH statement detected.")
        start: int = select_pos.start()
        text = text[start:].strip()
        return text

    def _ensure_single_statement(self, sql: str) -> None:
        cleaned = sql.strip()
        if ";" in cleaned[:-1]:
            raise SQLValidationError("Multiple SQL statements are not allowed.")

    def _ensure_select_only(self, sql: str) -> None:
        if not re.match(r"(?is)^\s*(select|with)\b", sql):
            raise SQLValidationError("Only SELECT queries are allowed.")

    def _ensure_no_blocked_keywords(self, sql: str) -> None:
        lowered = sql.lower()
        for keyword in BLOCKED_KEYWORDS:
            if re.search(rf"\b{keyword}\b", lowered):
                raise SQLValidationError(f"Blocked SQL operation detected: {keyword.upper()}")

    def _qualify_and_validate_tables(self, sql: str, cte_names: Set[str]) -> str:
        def replace_table(match: re.Match[str]) -> str:
            clause = match.group(1)
            raw_ref = match.group(2)
            
            if self._is_extract_clause(sql, match.start()):
                return f"{clause} {raw_ref}"

            if raw_ref.lower() in cte_names:
                return f"{clause} {raw_ref}"
            normalized, table = self._normalize_ref(raw_ref)
            if table not in self.allowed_tables:
                raise SQLValidationError(f"Table '{table}' is not in the approved allowlist.")
            if normalized is None:
                normalized = f"{self.allowed_dataset}.{table}"
            return f"{clause} `{normalized}`"

        rewritten = TABLE_REF_REGEX.sub(replace_table, sql)

        if not TABLE_REF_REGEX.search(rewritten):
            # Check if there are any non-EXTRACT table references
            has_table = False
            for match in TABLE_REF_REGEX.finditer(sql):
                if not self._is_extract_clause(sql, match.start()):
                    has_table = True
                    break
            if not has_table:
                raise SQLValidationError("No FROM/JOIN table reference found.")

        return rewritten

    def _is_extract_clause(self, sql: str, start_pos: int) -> bool:
        """Check if the FROM/JOIN keyword at start_pos is part of an EXTRACT() call."""
        prefix = sql[:start_pos].upper()
        extract_pos = prefix.rfind("EXTRACT(")
        if extract_pos == -1:
            return False
        # If there's a ")" between the last "EXTRACT(" and the current position, 
        # then the current position is outside that EXTRACT call.
        if ")" in prefix[extract_pos:]:
            return False
        return True

    @staticmethod
    def _extract_cte_names(sql: str) -> Set[str]:
        match = CTE_NAME_REGEX.search(sql)
        if not match:
            return set()
        cte_segment = match.group(1)
        return {name.lower() for name in CTE_EXTRACT_REGEX.findall(cte_segment)}

    def _normalize_ref(self, raw_ref: str) -> tuple[str | None, str]:
        # Strip backticks from each segment before validation
        parts = [p.strip("`") for p in raw_ref.split(".")]
        if len(parts) == 1:
            table = parts[0]
            return None, table
        if len(parts) == 2:
            dataset, table = parts
            if dataset not in {self.allowed_dataset, self._allowed_dataset_id}:
                # Try relative dataset check
                if dataset != self._allowed_dataset_id:
                    raise SQLValidationError(f"Dataset '{dataset}' is not allowed.")
            return f"{self.allowed_dataset}.{table}", table
        if len(parts) == 3:
            project, dataset, table = parts
            if dataset != self._allowed_dataset_id:
                raise SQLValidationError(f"Dataset '{dataset}' is not allowed.")
            if self._allowed_project and project != self._allowed_project:
                raise SQLValidationError(f"Project '{project}' is not allowed.")
            return f"{project}.{dataset}.{table}", table
        raise SQLValidationError(f"Invalid table reference: {raw_ref}")
        raise SQLValidationError(f"Invalid table reference: {raw_ref}")

    def _append_limit_if_missing(self, sql: str) -> str:
        if re.search(r"(?i)\blimit\s+\d+\b", sql):
            return sql
        return f"{sql.rstrip(';')} LIMIT {self.default_limit}"
