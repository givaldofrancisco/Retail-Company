from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

import pandas as pd


EMAIL_REGEX = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
PHONE_REGEX = re.compile(r"\b(?:\+?\d{1,3}[\s\-.]?)?(?:\(?\d{2,4}\)?[\s\-.]?)\d{3,4}[\s\-.]?\d{3,4}\b")

SENSITIVE_COLUMN_TOKENS = (
    "email",
    "phone",
    "telephone",
    "mobile",
    "contact",
)


@dataclass
class SanitizationResult:
    dataframe: pd.DataFrame
    removed_columns: List[str]


class PIIMasker:
    def sanitize_dataframe(self, dataframe: pd.DataFrame) -> SanitizationResult:
        removed_columns: List[str] = []
        safe_df = dataframe.copy()

        for column in list(safe_df.columns):
            col_lower = str(column).lower()
            if any(token in col_lower for token in SENSITIVE_COLUMN_TOKENS):
                removed_columns.append(column)
                safe_df = safe_df.drop(columns=[column])

        for column in safe_df.select_dtypes(include=["object", "string"]).columns:
            safe_df[column] = safe_df[column].astype(str).apply(self.mask_text)

        return SanitizationResult(dataframe=safe_df, removed_columns=removed_columns)

    def mask_text(self, text: str) -> str:
        masked = EMAIL_REGEX.sub("[REDACTED_EMAIL]", text)
        masked = PHONE_REGEX.sub("[REDACTED_PHONE]", masked)
        return masked
