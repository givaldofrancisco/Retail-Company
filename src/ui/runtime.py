from __future__ import annotations

import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app import build_app
from src.graph.state import new_state


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_USER = "manager_a"


class AppRuntime:
    def __init__(self) -> None:
        load_dotenv()
        (
            self.graph_app,
            self.pref_store,
            _llm_client,
            _version_snapshot,
            _security,
            self.report_store,
            self.learning_store,
            self.report_generator,
        ) = build_app(debug=True)

    def handle_question(self, question: str, user_id: str) -> dict[str, Any]:
        if question.lower().startswith("/format "):
            desired = question.split(" ", 1)[1].strip().lower()
            if desired not in {"table", "bullets"}:
                return {"final_status": "invalid_command", "final_report": "Supported formats: table, bullets"}
            self.pref_store.set_format(user_id, desired)
            return {"final_status": "success", "final_report": f"Saved format preference for {user_id}: {desired}"}

        if question.lower().startswith("/confirm "):
            token = question.split(" ", 1)[1].strip()
            ok, message = self.report_store.confirm_delete(token=token, user_id=user_id)
            return {
                "final_status": "success" if ok else "failed_confirmation",
                "final_report": message if ok else f"Confirmation failed: {message}",
            }

        if question.lower() == "/candidates":
            pending = self.learning_store.list_pending(limit=10)
            if not pending:
                return {"final_status": "success", "final_report": "No pending candidates."}
            lines = ["Pending candidates:"]
            for item in pending:
                lines.append(f"- {item['id']}: {item['question'][:100]}")
            return {"final_status": "success", "final_report": "\n".join(lines)}

        if question.lower().startswith("/approve_candidate "):
            candidate_id = question.split(" ", 1)[1].strip()
            ok, message = self.learning_store.approve_candidate(candidate_id)
            return {
                "final_status": "success" if ok else "failed_approval",
                "final_report": message if ok else f"Approval failed: {message}",
            }

        if question.lower() in {"exit", "quit"}:
            return {"final_status": "session_end", "final_report": "Session ended."}

        start = time.perf_counter()
        state = new_state(question=question, user_id=user_id)
        invoke_config = {"configurable": {"thread_id": f"{user_id}:ui:{uuid.uuid4().hex[:8]}"}}
        result = self.graph_app.invoke(state, config=invoke_config)
        elapsed_ms = (time.perf_counter() - start) * 1000

        if result.get("final_status") == "success" and result.get("validated_sql", "").strip():
            self.learning_store.capture_candidate(
                question=question,
                sql=result.get("validated_sql", ""),
                report=result.get("final_report", ""),
            )

        result_rows = result.get("result_rows", [])
        result_columns = result.get("result_columns", [])
        row_count = result.get("row_count", len(result_rows))
        return {
            "final_status": result.get("final_status", "unknown"),
            "final_report": result.get("final_report", "I could not complete this request."),
            "retry_count": result.get("retry_count", 0),
            "elapsed_ms": round(elapsed_ms, 2),
            "sql": result.get("validated_sql") or result.get("sql_candidate", ""),
            "rows": result_rows,
            "columns": result_columns,
            "row_count": row_count,
        }

    @staticmethod
    def run_command(args: list[str]) -> dict[str, Any]:
        started = time.perf_counter()
        completed = subprocess.run(
            args,
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            "returncode": completed.returncode,
            "elapsed_ms": round(elapsed_ms, 2),
            "output": completed.stdout[-24000:],
            "command": " ".join(args),
        }
