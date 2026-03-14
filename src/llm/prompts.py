from __future__ import annotations

import json
from typing import Any, Dict, List


def _format_golden_examples(examples: List[Dict[str, Any]]) -> str:
    if not examples:
        return "None available."
    lines = []
    for i, ex in enumerate(examples, 1):
        if not isinstance(ex, dict):
            continue
        lines.append(f"Example {i}:")
        lines.append(f"Input: {ex.get('question', '')}")
        lines.append(f"Output:\n{ex.get('sql', '')}\n")
    return "\n".join(lines)


def build_sql_prompt(question: str, schemas: Dict[str, Any], golden_examples: List[Dict[str, Any]]) -> str:
    formatted_examples = _format_golden_examples(golden_examples)
    return f"""
System: You are an expert data analytics SQL assistant for BigQuery.

Rules:
- Only query the dataset `bigquery-public-data.thelook_ecommerce`.
- Allowed tables: `orders`, `order_items`, `products`, `users`.
- Never generate DML/DDL.
- Protect PII: If requested, prefer safe aggregate metrics.
- Output ONLY valid SQL. 
- You MUST write your reasoning steps inside a multiline SQL comment block (/* ... */) before the SELECT statement.

Historical Examples:
{formatted_examples}

Input Question:
"{question}"

Database Schema:
{json.dumps(schemas, indent=2)}
""".strip()


def build_repair_prompt(
    question: str,
    failed_sql: str,
    error_message: str,
    schemas: Dict[str, Any],
    golden_examples: List[Dict[str, Any]],
) -> str:
    formatted_examples = _format_golden_examples(golden_examples)
    return f"""
System: You are an expert BigQuery SQL debugger. The previous query failed.

Rules:
- Output ONLY valid SQL.
- You MUST write your diagnosis and reasoning inside a SQL comment block (/* ... */) before the repaired SELECT statement.

Input Question:
"{question}"

Failed SQL:
{failed_sql}

Error Received:
{error_message}

Database Schema:
{json.dumps(schemas, indent=2)}

Historical Examples:
{formatted_examples}
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
System: You are a senior business analyst preparing an executive report.

Role & Style:
{persona_text}

Rules:
- Format preference: {preference_format}
- Be concise and grounded exclusively on the provided data.
- Do not expose raw PII.
- If data returned is 0 rows or insufficient, explicitly state the limitation.

Context:
User Question: "{question}"
Rows returned: {row_count}

Sample Results:
{json.dumps(data_preview[:20], indent=2)}

Historical Analyst Context (for tone reference):
{json.dumps(golden_examples, indent=2)}
""".strip()
