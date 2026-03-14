from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd
import re

from src.graph.state import AgentState
from src.memory.report_actions import ReportActionStore
from src.memory.user_preferences import UserPreferenceStore
from src.observability.decorators import traced
from src.observability.logger import get_logger, log_event
from src.reporting.report_generator import ReportGenerator
from src.safety.guardrails import Guardrails
from src.safety.pii_masker import PIIMasker
from src.tools.bigquery_runner import BigQueryExecutionError, BigQueryRunner
from src.tools.golden_retriever import GoldenRetriever
from src.tools.schema_tool import SchemaTool
from src.tools.sql_validator import SQLValidationError, SQLValidator
from src.llm.client import LLMClient


logger = get_logger(__name__)


@dataclass
class WorkflowNodes:
    guardrails: Guardrails
    schema_tool: SchemaTool
    golden_retriever: GoldenRetriever
    llm: LLMClient
    sql_validator: SQLValidator
    bq_runner: BigQueryRunner
    pii_masker: PIIMasker
    report_generator: ReportGenerator
    preference_store: UserPreferenceStore
    report_store: ReportActionStore | None = None

    @traced()
    def classify_intent(self, state: AgentState) -> Dict:
        request_id = state.get("request_id") or str(uuid.uuid4())
        question = state["question"]
        decision = self.guardrails.classify_intent(question)
        pii_request = self.guardrails.detect_pii_request(question)
        log_event(
            logger,
            "classify_intent",
            request_id=request_id,
            user_id=state["user_id"],
            question=question,
            intent=decision["intent"],
        )
        return {
            "request_id": request_id,
            "intent": decision["intent"],
            "intent_reason": decision["reason"],
            "pii_request": pii_request,
        }

    @traced()
    def reject_or_route(self, state: AgentState) -> Dict:
        intent = state["intent"]
        if intent == "destructive_report_op":
            log_event(logger, "completed", request_id=state.get("request_id", ""), status="requires_confirmation")
            if self.report_store is None:
                return {
                    "final_status": "requires_confirmation",
                    "final_report": (
                        "This command targets Saved Reports deletion, but confirmation storage is unavailable. "
                        "No action was executed."
                    ),
                    "sql_candidate": "",
                    "validated_sql": "",
                    "sql_error": "",
                }
            scope = self.report_store.extract_scope(state.get("question", ""))
            flow = self.report_store.start_delete_flow(
                user_id=state["user_id"],
                raw_question=state.get("question", ""),
                scope=scope,
            )
            return {
                "final_status": "requires_confirmation",
                "final_report": (
                    "Destructive action detected for Saved Reports.\n"
                    f"Scope: '{flow['scope']}'\n"
                    f"Matching reports: {flow['preview_count']}\n"
                    f"To execute, type: /confirm {flow['token']}\n"
                    "No action was executed yet."
                ),
                "sql_candidate": "",
                "validated_sql": "",
                "sql_error": "",
            }
        if intent == "instruction_update":
            if state["user_id"] != "ceo":
                return {
                    "final_status": "rejected",
                    "final_report": "Only the CEO has permission to change global system instructions.",
                }
            # Proceed to update node
            return state

        if intent == "unsupported":
            log_event(logger, "completed", request_id=state.get("request_id", ""), status="rejected")
            return {
                "final_status": "rejected",
                "final_report": "Sorry, I can only help with retail analytics (sales, inventory, customers).",
                "sql_candidate": "",
                "validated_sql": "",
                "sql_error": "",
            }
        return state

    @traced()
    def apply_instruction_update(self, state: AgentState) -> Dict:
        """Process the CEO's request to update persona instructions."""
        question = state["question"]
        request_id = state.get("request_id", "")
        
        # In a real implementation, we would use an LLM here to generate the new YAML content.
        # For this prototype, we'll extract the core request.
        log_event(logger, "apply_instruction_update", request_id=request_id, user_id=state["user_id"])
        
        # Simulate LLM extracting a more concise "voice" from the instruction
        # or just use the instruction itself as the new voice for all personas.
        new_voice = question.replace("daqui para frente use o tom ", "").replace("From now on, use a ", "").strip()
        
        self.report_generator.batch_update_personas(new_voice)
        
        return {
            "final_status": "success",
            "final_report": (
                "System instructions successfully updated for all personas.\n"
                f"New Tone: '{new_voice}'\n"
                "Changes will take effect immediately in future reports."
            ),
        }

    @traced()
    def load_schema(self, state: AgentState) -> Dict:
        schemas = self.schema_tool.fetch()
        log_event(logger, "schema_loaded", request_id=state["request_id"], tables=list(schemas.keys()))
        return {"schema_context": schemas}

    @traced()
    def generate_schema_response(self, state: AgentState) -> Dict:
        schemas = state.get("schema_context", {})
        question = state["question"].lower()
        requested_table = None
        for table in ["orders", "order_items", "products", "users"]:
            if table in question:
                requested_table = table
                break

        if requested_table:
            columns = schemas.get(requested_table, [])
            lines = [f"Schema for `{requested_table}` ({len(columns)} columns):"]
            for col in columns:
                lines.append(f"- {col.get('name')} ({col.get('type')})")
            report = "\n".join(lines)
        else:
            report = "Available tables: orders, order_items, products, users. Ask for one table to list its columns."

        report = self.pii_masker.mask_text(report)
        log_event(logger, "completed", request_id=state.get("request_id", ""), status="success")
        return {
            "final_status": "success",
            "final_report": report,
            "sql_candidate": "",
            "validated_sql": "",
            "sql_error": "",
        }

    @traced()
    def retrieve_golden_examples(self, state: AgentState) -> Dict:
        examples = self.golden_retriever.retrieve(state["question"], top_k=3)
        log_event(
            logger,
            "golden_retrieved",
            request_id=state["request_id"],
            examples=[e.get("question", "") for e in examples],
        )
        return {"golden_examples": examples}

    @traced()
    def generate_sql(self, state: AgentState) -> Dict:
        if state.get("pii_request"):
            sql = (
                "SELECT u.id AS customer_id, ROUND(SUM(oi.sale_price), 2) AS total_spend "
                "FROM bigquery-public-data.thelook_ecommerce.users u "
                "JOIN bigquery-public-data.thelook_ecommerce.orders o ON u.id = o.user_id "
                "JOIN bigquery-public-data.thelook_ecommerce.order_items oi ON o.order_id = oi.order_id "
                "GROUP BY customer_id ORDER BY total_spend DESC LIMIT 10"
            )
            log_event(
                logger,
                "sql_generated",
                request_id=state["request_id"],
                sql=sql,
                reason="pii_request_safe_fallback",
            )
            return {"sql_candidate": sql}

        raw_sql = self.llm.generate_sql(
            question=state["question"],
            schemas=state.get("schema_context", {}),
            golden_examples=state.get("golden_examples", []),
        )
        log_event(logger, "sql_generated", request_id=state["request_id"], sql=raw_sql)
        cleaned = self._sanitize_sql(raw_sql)
        if not cleaned:
            raise ValueError("LLM did not return a parsable SQL statement.")
        return {"sql_candidate": cleaned}

    @traced()
    def validate_sql(self, state: AgentState) -> Dict:
        try:
            validated = self.sql_validator.validate_and_rewrite(state["sql_candidate"])
            log_event(logger, "sql_validated", request_id=state["request_id"], sql=validated)
            return {"validated_sql": validated, "sql_error": "", "error_message": ""}
        except SQLValidationError as exc:
            log_event(logger, "completed", request_id=state.get("request_id", ""), status="failed_validation")
            return {
                "final_status": "failed_validation",
                "error_message": str(exc),
                "final_report": "I could not produce a safe SQL query for this request.",
                "sql_error": str(exc),
            }

    @traced()
    def execute_sql(self, state: AgentState) -> Dict:
        sql = state.get("validated_sql", "")
        try:
            dataframe = self.bq_runner.execute_query(sql)
            log_event(
                logger,
                "sql_executed",
                request_id=state["request_id"],
                row_count=len(dataframe),
                retry_count=state.get("retry_count", 0),
            )
            return self._df_to_state_payload(dataframe)
        except BigQueryExecutionError as exc:
            log_event(
                logger,
                "sql_execution_failed",
                request_id=state["request_id"],
                error=str(exc),
                retry_count=state.get("retry_count", 0),
            )
            return {
                "sql_error": str(exc),
                "error_message": str(exc),
            }

    @traced()
    def repair_sql(self, state: AgentState) -> Dict:
        next_retry = state.get("retry_count", 0) + 1
        raw_repaired = self.llm.repair_sql(
            question=state["question"],
            failed_sql=state.get("validated_sql", state.get("sql_candidate", "")),
            error_message=state.get("sql_error", "Unknown SQL error"),
            schemas=state.get("schema_context", {}),
            golden_examples=state.get("golden_examples", []),
        )
        repaired = self._sanitize_sql(raw_repaired)
        if not repaired:
            repaired = raw_repaired.strip()

        log_event(
            logger,
            "sql_repair_attempt",
            request_id=state["request_id"],
            retry_count=next_retry,
            repaired_sql=repaired,
        )
        return {"retry_count": next_retry, "sql_candidate": repaired, "error_message": ""}

    @staticmethod
    def _sanitize_sql(sql: str) -> str:
        text = sql or ""
        if "*/" in text:
            text = text.split("*/", 1)[1]
        match = re.search(r"(?mi)^[ 	]*(select|with)", text)
        if match:
            return text[match.start() :].strip()
        return text.strip()

    @traced()
    def sanitize_results(self, state: AgentState) -> Dict:
        rows = state.get("result_rows", [])
        dataframe = pd.DataFrame(rows)
        sanitized = self.pii_masker.sanitize_dataframe(dataframe)
        sanitized_rows: List[Dict] = sanitized.dataframe.to_dict(orient="records")

        log_event(
            logger,
            "results_sanitized",
            request_id=state["request_id"],
            removed_pii_columns=sanitized.removed_columns,
        )

        return {
            "result_rows": sanitized_rows,
            "result_columns": list(sanitized.dataframe.columns),
            "removed_pii_columns": sanitized.removed_columns,
        }

    @traced()
    def generate_report(self, state: AgentState) -> Dict:
        rows = state.get("result_rows", [])
        if not rows:
            return {
                "final_status": "empty_result",
                "final_report": (
                    "No matching records were found for this query. "
                    "Try widening the time range or reducing constraints."
                ),
            }

        pref = self.preference_store.get(state["user_id"])
        report = self.report_generator.generate(
            question=state["question"],
            rows=rows,
            preference_format=pref.get("format", "bullets"),
            golden_examples=state.get("golden_examples", []),
            removed_pii_columns=state.get("removed_pii_columns", []),
            persona_id=state.get("user_id", "default"),
        )
        report = self.pii_masker.mask_text(report)
        if state.get("pii_request") and "Safety Note:" not in report:
            report += (
                "\n\nSafety Note: Direct personal identifiers (email/phone) were requested "
                "and are not displayed. Provided aggregated results instead."
            )

        status = "success" if rows else "empty_result"
        log_event(logger, "completed", request_id=state.get("request_id", ""), status=status)

        return {
            "final_status": status,
            "final_report": report,
        }

    @traced()
    def finalize_response(self, state: AgentState) -> Dict:
        # Acting purely as an error handler for unhandled execution failures
        status = "failed_execution"
        log_event(
            logger,
            "completed",
            request_id=state.get("request_id", ""),
            status=status,
        )
        return {
            "final_status": status,
            "final_report": (
                "I hit a query execution issue after retry attempts. "
                "Please rephrase the request or try a narrower question."
            ),
        }

    @staticmethod
    def _df_to_state_payload(dataframe: pd.DataFrame) -> Dict:
        return {
            "result_rows": dataframe.to_dict(orient="records"),
            "result_columns": list(dataframe.columns),
            "row_count": int(len(dataframe)),
            "error_message": "",
            "sql_error": "",
        }
