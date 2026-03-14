import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.graph.nodes import WorkflowNodes
from src.graph.state import new_state
from src.graph.workflow import build_workflow
from src.memory.report_actions import ReportActionStore
from src.memory.user_preferences import UserPreferenceStore
from src.observability.logger import JsonFormatter
from src.safety.guardrails import Guardrails
from src.safety.pii_masker import PIIMasker
from src.tools.bigquery_runner import BigQueryExecutionError
from src.tools.sql_validator import SQLValidator


class FakeSchemaTool:
    def fetch(self):
        return {
            "orders": [{"name": "order_id", "type": "INTEGER"}],
            "order_items": [{"name": "sale_price", "type": "FLOAT"}],
            "products": [{"name": "name", "type": "STRING"}],
            "users": [
                {"name": "id", "type": "INTEGER"},
                {"name": "email", "type": "STRING"},
                {"name": "phone_number", "type": "STRING"},
            ],
        }


class FakeGoldenRetriever:
    def __init__(self):
        self.last_question = None

    def retrieve(self, question: str, top_k: int = 3):
        self.last_question = question
        return [
            {
                "question": "Who are the top customers by spend?",
                "sql": "SELECT user_id, SUM(sale_price) AS spend FROM order_items GROUP BY user_id",
                "report": "Top customers contribute the majority of revenue.",
                "tags": ["customers", "spend"],
                "score": 2,
            }
        ]


class FakeLLM:
    def __init__(self):
        self.generate_sql_calls = []
        self.repair_calls = []

    def generate_sql(self, question, schemas, golden_examples):
        self.generate_sql_calls.append(
            {
                "question": question,
                "schema_tables": sorted(schemas.keys()),
                "golden_examples_count": len(golden_examples),
            }
        )
        return "SELECT id AS customer_id, email, phone_number, 'Reach ceo@retail.com' AS note FROM users"

    def repair_sql(self, question, failed_sql, error_message, schemas, golden_examples):
        self.repair_calls.append(
            {
                "question": question,
                "failed_sql": failed_sql,
                "error_message": error_message,
                "golden_examples_count": len(golden_examples),
            }
        )
        return "SELECT id AS customer_id, email, phone_number, 'Reach ceo@retail.com' AS note FROM users"


class FakeBigQueryRunner:
    def __init__(self, fail_first=False):
        self.fail_first = fail_first
        self.execute_calls = 0
        self.executed_sql = []

    def execute_query(self, sql_query: str) -> pd.DataFrame:
        self.execute_calls += 1
        self.executed_sql.append(sql_query)
        if self.fail_first and self.execute_calls == 1:
            raise BigQueryExecutionError("simulated syntax error near SELECT")
        return pd.DataFrame(
            [
                {
                    "customer_id": 101,
                    "email": "alice@example.com",
                    "phone_number": "+1 (202) 555-0199",
                    "note": "Escalate to bob@example.org",
                }
            ]
        )


class FakeReportGenerator:
    def __init__(self):
        self.last_preference = None

    def generate(self, question, rows, preference_format, golden_examples, removed_pii_columns):
        self.last_preference = preference_format
        return (
            f"Format={preference_format}; rows={len(rows)}; "
            f"golden={len(golden_examples)}; contact ceo@retail.com"
        )


def _build_test_app(tmp_path: Path, fail_first=False):
    pref_store = UserPreferenceStore(tmp_path / "prefs.json")
    fake_llm = FakeLLM()
    fake_bq = FakeBigQueryRunner(fail_first=fail_first)
    fake_report = FakeReportGenerator()

    nodes = WorkflowNodes(
        guardrails=Guardrails(),
        schema_tool=FakeSchemaTool(),
        golden_retriever=FakeGoldenRetriever(),
        llm=fake_llm,
        sql_validator=SQLValidator(
            allowed_dataset="bigquery-public-data.thelook_ecommerce",
            allowed_tables={"orders", "order_items", "products", "users"},
        ),
        bq_runner=fake_bq,
        pii_masker=PIIMasker(),
        report_generator=fake_report,
        preference_store=pref_store,
        report_store=ReportActionStore(
            reports_path=tmp_path / "saved_reports.json",
            pending_path=tmp_path / "pending_report_actions.json",
        ),
    )
    app = build_workflow(nodes)
    return app, nodes, pref_store, fake_llm, fake_bq, fake_report


def _invoke(app, state):
    return app.invoke(state, config={"configurable": {"thread_id": "test-thread"}})


def test_assignment_end_to_end_hybrid_pii_and_resilience(tmp_path):
    app, _nodes, pref_store, fake_llm, fake_bq, _fake_report = _build_test_app(
        tmp_path, fail_first=True
    )
    pref_store.set_format("manager_a", "table")

    result = _invoke(
        app,
        new_state(
            question="Who are the top customers by spend?",
            user_id="manager_a",
            max_retries=2,
        )
    )

    assert result["final_status"] == "success"
    assert result["retry_count"] == 1
    assert fake_bq.execute_calls == 2

    assert fake_llm.generate_sql_calls[0]["golden_examples_count"] > 0
    assert len(fake_llm.repair_calls) == 1

    assert "email" in result["removed_pii_columns"]
    assert "phone_number" in result["removed_pii_columns"]

    assert "alice@example.com" not in result["final_report"]
    assert "ceo@retail.com" not in result["final_report"]
    assert "[REDACTED_EMAIL]" in result["final_report"]


def test_assignment_destructive_op_requires_confirmation_and_no_execution(tmp_path):
    app, _nodes, _pref_store, _fake_llm, fake_bq, _fake_report = _build_test_app(tmp_path)

    result = _invoke(
        app,
        new_state(
            question="Delete all reports mentioning Client X",
            user_id="manager_a",
        )
    )

    assert result["final_status"] == "requires_confirmation"
    assert "/confirm DEL-" in result["final_report"]
    assert "No action was executed" in result["final_report"]
    assert fake_bq.execute_calls == 0
    assert result.get("validated_sql", "") == ""


def test_assignment_analysis_only_rejects_non_analytical_questions(tmp_path):
    app, _nodes, _pref_store, _fake_llm, fake_bq, _fake_report = _build_test_app(tmp_path)

    result = _invoke(
        app,
        new_state(
            question="What is the weather in Lisbon today?",
            user_id="manager_a",
        )
    )

    assert result["final_status"] == "rejected"
    assert "only answer analytical" in result["final_report"].lower()
    assert fake_bq.execute_calls == 0
    assert result.get("validated_sql", "") == ""


def test_assignment_schema_lookup_supported(tmp_path):
    app, _nodes, _pref_store, _fake_llm, fake_bq, _fake_report = _build_test_app(tmp_path)

    result = _invoke(
        app,
        new_state(
            question="What columns exist in the users table?",
            user_id="manager_a",
        )
    )

    assert result["final_status"] == "success"
    assert "Schema for `users`" in result["final_report"]
    assert "email (STRING)" in result["final_report"]
    assert fake_bq.execute_calls == 0
    assert result.get("validated_sql", "") == ""


def test_assignment_user_preference_is_applied_in_reporting(tmp_path):
    app, _nodes, pref_store, _fake_llm, _fake_bq, fake_report = _build_test_app(tmp_path)
    pref_store.set_format("manager_b", "table")

    result = _invoke(
        app,
        new_state(
            question="What are the top products by revenue?",
            user_id="manager_b",
        )
    )

    assert result["final_status"] == "success"
    assert fake_report.last_preference == "table"


def test_assignment_compare_months_adds_comparison_note(tmp_path):
    class MonthlyBigQueryRunner:
        def execute_query(self, sql_query: str) -> pd.DataFrame:
            return pd.DataFrame(
                [
                    {"month": "2026-01", "revenue": 100.0},
                    {"month": "2026-02", "revenue": 150.0},
                ]
            )

    app, nodes, _pref_store, _fake_llm, _fake_bq, _fake_report = _build_test_app(tmp_path)
    nodes.bq_runner = MonthlyBigQueryRunner()
    # use the real report generator to test comparison logic
    from src.reporting.report_generator import ReportGenerator
    from src.llm.client import LLMClient
    nodes.report_generator = ReportGenerator(
        llm=LLMClient(), persona_file=Path(__file__).resolve().parents[1] / "config" / "personas" / "default.yaml"
    )

    result = _invoke(
        app,
        new_state(
            question="Compare this month's revenue vs previous month.",
            user_id="manager_a",
        )
    )

    assert result["final_status"] == "success"
    assert "Month-over-month comparison" in result["final_report"]


def test_assignment_observability_json_formatter_contains_context_fields():
    formatter = JsonFormatter()

    record = __import__("logging").LogRecord(
        name="test.logger",
        level=20,
        pathname=__file__,
        lineno=1,
        msg="sql_executed",
        args=(),
        exc_info=None,
    )
    record.event = "sql_executed"
    record.context = {
        "request_id": "req-123",
        "user_id": "manager_a",
        "retry_count": 1,
        "row_count": 10,
    }

    payload = json.loads(formatter.format(record))
    assert payload["event"] == "sql_executed"
    assert payload["request_id"] == "req-123"
    assert payload["user_id"] == "manager_a"
    assert payload["retry_count"] == 1
    assert payload["row_count"] == 10


def test_assignment_quality_artifacts_exist_and_are_structured():
    eval_file = ROOT / "src" / "evaluation" / "eval_cases.json"
    readme_file = ROOT / "README.md"
    architecture_file = ROOT / "architecture.md"

    assert eval_file.exists()
    assert readme_file.exists()
    assert architecture_file.exists()

    eval_cases = json.loads(eval_file.read_text(encoding="utf-8"))
    assert len(eval_cases) >= 4
    for case in eval_cases:
        assert "question" in case
        assert "dimensions" in case
        assert len(case["dimensions"]) >= 2

    readme = readme_file.read_text(encoding="utf-8")
    architecture = architecture_file.read_text(encoding="utf-8")

    assert "```mermaid" in readme
    assert "How Each Assignment Requirement Is Addressed" in readme

    assert "Destructive Operations Confirmation Design" in architecture
    assert "Observability Model" in architecture
    assert "Production evolution".lower() in architecture.lower()


def test_assignment_pii_request_returns_safe_aggregation_and_note(tmp_path):
    class SafeOnlyBigQueryRunner:
        def execute_query(self, sql_query: str) -> pd.DataFrame:
            return pd.DataFrame([{"customer_id": 1, "total_spend": 999.0}])

    app, nodes, pref_store, _fake_llm, _fake_bq, _fake_report = _build_test_app(tmp_path)
    nodes.bq_runner = SafeOnlyBigQueryRunner()

    result = _invoke(
        app,
        new_state(
            question="List customer emails with highest spend.",
            user_id="manager_a",
        )
    )

    assert result["final_status"] == "success"
    assert "Safety Note:" in result["final_report"]
    assert "@" not in result["final_report"]
