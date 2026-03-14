from __future__ import annotations

import json
from typing import Any, Dict, List


def build_sql_prompt(question: str, schemas: Dict[str, Any], golden_examples: List[Dict[str, Any]]) -> str:
    return f"""
You are an analytics SQL assistant for BigQuery.
Task: Generate one BigQuery SELECT query for the user question.

Rules:
- Only use dataset bigquery-public-data.thelook_ecommerce
- Allowed tables: orders, order_items, products, users
- Never generate DML/DDL.
- Prefer safe aggregate outputs when user requests PII.
- Return SQL only.

Question:
{question}

Schemas:
{json.dumps(schemas, indent=2)}

Golden examples:
{json.dumps(golden_examples, indent=2)}
""".strip()


def build_repair_prompt(
    question: str,
    failed_sql: str,
    error_message: str,
    schemas: Dict[str, Any],
    golden_examples: List[Dict[str, Any]],
) -> str:
    return f"""
The following SQL failed in BigQuery. Repair it.
Return SQL only.

Question:
{question}

Failed SQL:
{failed_sql}

Error:
{error_message}

Schemas:
{json.dumps(schemas, indent=2)}

Golden examples:
{json.dumps(golden_examples, indent=2)}
""".strip()


def build_report_prompt(
    question: str,
    row_count: int,
    data_preview: List[Dict[str, Any]],
    persona_text: str,
    preference_format: str,
    golden_examples: List[Dict[str, Any]],
) -> str:
    return f"""
You are preparing an executive report for retail managers.

Persona:
{persona_text}

User format preference: {preference_format}

Question:
{question}

Rows returned: {row_count}
Sample rows:
{json.dumps(data_preview[:20], indent=2)}

Relevant historical analyst examples:
{json.dumps(golden_examples, indent=2)}

Output rules:
- Be concise and data-grounded.
- Do not expose raw PII.
- If data is limited, state uncertainty.
""".strip()
