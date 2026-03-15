from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from src.graph.nodes import WorkflowNodes
from src.graph.state import new_state
from src.graph.workflow import build_workflow
from src.memory.learning_loop import LearningLoopStore
from src.memory.report_actions import ReportActionStore
from src.memory.user_preferences import UserPreferenceStore
from src.reporting.report_generator import ReportGenerator
from src.safety.guardrails import Guardrails
from src.safety.pii_masker import PIIMasker
from src.tools.sql_validator import SQLValidator


@dataclass
class QACaseResult:
    case_id: str
    question: str
    expected_intent: str
    actual_intent: str
    final_status: str
    intent_match: bool
    status_ok: bool
    safety_ok: bool
    details: str


class _FakeSchemaTool:
    def fetch(self):
        return {
            "orders": [{"name": "order_id", "type": "INTEGER"}],
            "order_items": [{"name": "sale_price", "type": "FLOAT"}],
            "products": [{"name": "name", "type": "STRING"}],
            "users": [{"name": "id", "type": "INTEGER"}, {"name": "email", "type": "STRING"}],
        }


class _FakeGoldenRetriever:
    def retrieve(self, question: str, top_k: int = 3):
        return [{"question": question, "sql": "SELECT 1", "report": "sample", "tags": ["sample"], "score": 1}]


class _FakeLLM:
    def generate_sql(self, question, schemas, golden_examples):
        q = question.lower()
        if "monthly" in q or "mês" in q or "month" in q:
            return (
                "SELECT FORMAT_DATE('%Y-%m', DATE(o.created_at)) AS month, ROUND(SUM(oi.sale_price), 2) AS revenue "
                "FROM bigquery-public-data.thelook_ecommerce.order_items oi "
                "JOIN bigquery-public-data.thelook_ecommerce.orders o ON oi.order_id = o.order_id "
                "WHERE DATE(o.created_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH) "
                "GROUP BY month ORDER BY month"
            )
        if "customer" in q or "cliente" in q:
            return (
                "SELECT u.id AS customer_id, ROUND(SUM(oi.sale_price), 2) AS total_spend "
                "FROM bigquery-public-data.thelook_ecommerce.users u "
                "JOIN bigquery-public-data.thelook_ecommerce.orders o ON u.id = o.user_id "
                "JOIN bigquery-public-data.thelook_ecommerce.order_items oi ON o.order_id = oi.order_id "
                "GROUP BY customer_id ORDER BY total_spend DESC LIMIT 10"
            )
        return (
            "SELECT p.id, p.name, ROUND(SUM(oi.sale_price), 2) AS revenue "
            "FROM bigquery-public-data.thelook_ecommerce.order_items oi "
            "JOIN bigquery-public-data.thelook_ecommerce.orders o ON oi.order_id = o.order_id "
            "JOIN bigquery-public-data.thelook_ecommerce.products p ON oi.product_id = p.id "
            "GROUP BY p.id, p.name ORDER BY revenue DESC LIMIT 10"
        )

    def repair_sql(self, question, failed_sql, error_message, schemas, golden_examples):
        return self.generate_sql(question, schemas, golden_examples)

    def generate_report(self, question, row_count, data_preview, persona_text, preference_format, golden_examples):
        return f"Question: {question}\nRows analyzed: {row_count}\nSummary: Safe analytical output."


class _FakeBigQueryRunner:
    def execute_query(self, sql_query: str) -> pd.DataFrame:
        sql = sql_query.lower()
        if " as month" in sql and "revenue" in sql:
            return pd.DataFrame([{"month": "2026-02", "revenue": 100.0}, {"month": "2026-03", "revenue": 110.0}])
        if "customer_id" in sql:
            return pd.DataFrame([{"customer_id": 1, "total_spend": 999.0}, {"customer_id": 2, "total_spend": 777.0}])
        return pd.DataFrame([{"product_id": 101, "product_name": "Widget A", "revenue": 15000.5}])

    def get_table_schema(self, table_name: str):
        return [{"name": "id", "type": "INTEGER"}]


def _build_eval_app(base: Path):
    nodes = WorkflowNodes(
        guardrails=Guardrails(),
        schema_tool=_FakeSchemaTool(),
        golden_retriever=_FakeGoldenRetriever(),
        llm=_FakeLLM(),
        sql_validator=SQLValidator(
            allowed_dataset="bigquery-public-data.thelook_ecommerce",
            allowed_tables={"orders", "order_items", "products", "users"},
        ),
        bq_runner=_FakeBigQueryRunner(),
        pii_masker=PIIMasker(),
        report_generator=ReportGenerator(llm=_FakeLLM(), personas_dir=base / "config" / "personas"),
        preference_store=UserPreferenceStore(base / "data" / "user_preferences.json"),
        report_store=ReportActionStore(
            reports_path=base / "data" / "saved_reports.json",
            pending_path=base / "data" / "pending_report_actions.json",
        ),
    )
    return build_workflow(nodes), nodes


def run_qa_gate(base_dir: Path) -> Dict[str, Any]:
    eval_cases_path = base_dir / "src" / "evaluation" / "eval_cases.json"
    output_json = base_dir / "outputs" / "qa_gate_summary.json"
    output_md = base_dir / "outputs" / "qa_gate_summary.md"
    output_json.parent.mkdir(parents=True, exist_ok=True)

    app, nodes = _build_eval_app(base_dir)
    cases = json.loads(eval_cases_path.read_text(encoding="utf-8"))
    results: List[QACaseResult] = []

    for case in cases:
        question = case["question"]
        expected_intent = case.get("expected_intent", "")
        actual_intent = nodes.guardrails.classify_intent(question)["intent"]

        result = app.invoke(
            new_state(question=question, user_id="qa_gate"),
            config={"configurable": {"thread_id": f"qa:{case['id']}"}},
        )

        final_report = result.get("final_report", "")
        final_status = result.get("final_status", "")
        must_not = [token.lower() for token in case.get("must_not_contain", [])]
        safety_ok = all(not _contains_blocked(final_report, token) for token in must_not)

        expected_behavior = case.get("expected_behavior", "")
        if expected_behavior == "requires_confirmation_no_execution":
            status_ok = final_status == "requires_confirmation"
        elif expected_behavior == "aggregate_or_masked_output":
            status_ok = final_status == "success" and "Safety Note:" in final_report
        elif expected_intent == "analysis":
            status_ok = final_status == "success"
        else:
            status_ok = final_status in {"success", "requires_confirmation", "rejected"}

        details = f"status={final_status}; report_len={len(final_report)}"
        results.append(
            QACaseResult(
                case_id=case["id"],
                question=question,
                expected_intent=expected_intent,
                actual_intent=actual_intent,
                final_status=final_status,
                intent_match=(expected_intent == actual_intent),
                status_ok=status_ok,
                safety_ok=safety_ok,
                details=details,
            )
        )

    total = len(results)
    intent_accuracy = sum(1 for item in results if item.intent_match) / total if total else 0.0
    success_rate = sum(1 for item in results if item.status_ok) / total if total else 0.0
    safety_rate = sum(1 for item in results if item.safety_ok) / total if total else 0.0

    thresholds = {
        "intent_accuracy_min": 0.95,
        "status_success_min": 0.90,
        "safety_rate_min": 1.00,
    }
    gate_passed = (
        intent_accuracy >= thresholds["intent_accuracy_min"]
        and success_rate >= thresholds["status_success_min"]
        and safety_rate >= thresholds["safety_rate_min"]
    )

    summary = {
        "gate_passed": gate_passed,
        "metrics": {
            "total_cases": total,
            "intent_accuracy": round(intent_accuracy, 4),
            "status_success_rate": round(success_rate, 4),
            "safety_rate": round(safety_rate, 4),
        },
        "thresholds": thresholds,
        "results": [asdict(item) for item in results],
    }

    output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    output_md.write_text(_to_markdown(summary), encoding="utf-8")
    return summary


def _to_markdown(summary: Dict[str, Any]) -> str:
    lines = []
    lines.append("# QA Gate Summary")
    lines.append("")
    lines.append(f"- Gate passed: **{summary['gate_passed']}**")
    lines.append(f"- Total cases: {summary['metrics']['total_cases']}")
    lines.append(f"- Intent accuracy: {summary['metrics']['intent_accuracy']}")
    lines.append(f"- Status success rate: {summary['metrics']['status_success_rate']}")
    lines.append(f"- Safety rate: {summary['metrics']['safety_rate']}")
    lines.append("")
    lines.append("## Case Results")
    for item in summary["results"]:
        lines.append(
            f"- {item['case_id']}: intent_match={item['intent_match']}, "
            f"status_ok={item['status_ok']}, safety_ok={item['safety_ok']}, final_status={item['final_status']}"
        )
    return "\n".join(lines) + "\n"


def _contains_blocked(text: str, token: str) -> bool:
    lower_text = text.lower()
    if token in {"email", "e-mail", "mail"}:
        return bool(re.search(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", text))
    if token in {"phone", "telefone", "celular"}:
        return bool(re.search(r"\b(?:\+?\d{1,3}[\s\-.]?)?(?:\(?\d{2,4}\)?[\s\-.]?)\d{3,4}[\s\-.]?\d{3,4}\b", text))
    return token in lower_text


def main() -> int:
    base = Path(__file__).resolve().parents[2]
    summary = run_qa_gate(base)
    print(json.dumps(summary["metrics"], indent=2))
    print(f"gate_passed={summary['gate_passed']}")
    return 0 if summary["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
