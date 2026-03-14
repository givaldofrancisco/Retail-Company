from __future__ import annotations

import argparse
import os
import time
import uuid
import warnings
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO

from dotenv import load_dotenv

from src.graph.nodes import WorkflowNodes
from src.graph.state import new_state
from src.graph.workflow import build_workflow
from src.memory.user_preferences import UserPreferenceStore
from src.memory.report_actions import ReportActionStore
from src.memory.learning_loop import LearningLoopStore
from src.observability import (
    ObservabilityExporter,
    ObservableBigQueryRunner,
    ObservableGoldenRetriever,
    ObservableLLMClient,
    ObservableSchemaTool,
    ObservableSQLValidator,
    QualityEvaluator,
    SecurityObserver,
    Tracer,
    TraceStore,
    VersionRegistry,
    get_collector,
    get_retrieval_store,
    get_tool_observer,
    record_metric,
    set_security_observer,
    setup_logging,
)
from src.observability.models import TraceMetadata
from src.reporting.report_generator import ReportGenerator
from src.safety.guardrails import Guardrails
from src.safety.pii_masker import PIIMasker


def build_app(debug: bool = False):
    setup_logging(debug=debug)

    # Initialize security observer (PII sanitization in all log payloads)
    security = SecurityObserver()
    set_security_observer(security)

    base = Path(__file__).parent
    allowed_tables = {"orders", "order_items", "products", "users"}
    dataset = "bigquery-public-data.thelook_ecommerce"

    # Use observable wrappers instead of raw classes.
    # Graceful degradation: if GOOGLE_CLOUD_PROJECT is not set, use a local-only
    # stub that returns fallback schemas and canned query results so the app can
    # still be exercised for observability / development purposes.
    import logging as _logging

    def _build_fallback_runner():
        from src.tools.schema_tool import FALLBACK_SCHEMAS

        class _FallbackBQRunner:  # noqa: N801
            """Minimal stub so the app starts without GCP credentials."""
            dataset_id = dataset

            def execute_query(self, sql_query: str):
                import pandas as _pd
                return _pd.DataFrame({
                    "product_id": [101, 102, 103],
                    "product_name": ["Widget A", "Widget B", "Widget C"],
                    "revenue": [15000.50, 12300.75, 9800.00],
                })

            def get_table_schema(self, table_name: str):
                return FALLBACK_SCHEMAS.get(table_name, [])

        return _FallbackBQRunner()

    _gcp_project = (os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip() or None
    if _gcp_project is None:
        _logging.getLogger(__name__).warning(
            "BigQuery unavailable (GOOGLE_CLOUD_PROJECT not set). Using local fallback runner."
        )
        bq_runner = _build_fallback_runner()  # type: ignore[assignment]
    else:
        try:
            bq_runner = ObservableBigQueryRunner(project_id=_gcp_project, dataset_id=dataset)
        except Exception:
            _logging.getLogger(__name__).warning(
                "BigQuery initialization failed. Using local fallback runner."
            )
            bq_runner = _build_fallback_runner()  # type: ignore[assignment]

    llm_default_model = os.getenv("GEMINI_MODEL") or os.getenv("OLLAMA_MODEL") or "gemini-2.0-flash"
    llm_client = ObservableLLMClient(model_name=llm_default_model)

    report_store = ReportActionStore(
        reports_path=base / "data" / "saved_reports.json",
        pending_path=base / "data" / "pending_report_actions.json",
    )

    learning_store = LearningLoopStore(
        candidates_path=base / "data" / "learning_candidates.json",
        golden_path=base / "data" / "golden_trios.json",
    )

    nodes = WorkflowNodes(
        guardrails=Guardrails(),
        schema_tool=ObservableSchemaTool(runner=bq_runner, tables=sorted(allowed_tables)),
        golden_retriever=ObservableGoldenRetriever(base / "data" / "golden_trios.json"),
        llm=llm_client,
        sql_validator=ObservableSQLValidator(allowed_dataset=dataset, allowed_tables=allowed_tables),
        bq_runner=bq_runner,
        pii_masker=PIIMasker(),
        report_generator=ReportGenerator(llm=llm_client, personas_dir=base / "config" / "personas"),
        preference_store=UserPreferenceStore(base / "data" / "user_preferences.json"),
        report_store=report_store,
    )

    # Capture version snapshot
    version_registry = VersionRegistry(base)
    version_snapshot = version_registry.capture_snapshot(
        model_name=llm_client.model_name,
        temperature=llm_client.temperature,
    )

    return (
        build_workflow(nodes),
        nodes.preference_store,
        llm_client,
        version_snapshot,
        security,
        report_store,
        learning_store,
        nodes.report_generator,
    )


class TranscriptWriter:
    def __init__(self, path: Optional[Path]) -> None:
        self.path = path
        self._fh: Optional[TextIO] = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self.path.open("w", encoding="utf-8")

    def write_line(self, text: str = "") -> None:
        if self._fh is not None:
            self._fh.write(text + "\n")
            self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def _default_transcript_path(base_dir: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return base_dir / "outputs" / f"session_{ts}.txt"


def main() -> None:
    warnings.filterwarnings(
        "ignore",
        message="BigQuery Storage module not found*",
        category=UserWarning,
    )
    load_dotenv()

    parser = argparse.ArgumentParser(description="Retail Analytics Assistant CLI")
    parser.add_argument("--user-id", default="manager_a", help="User identity for preference memory")
    parser.add_argument("--debug", action="store_true", help="Enable structured debug logs")
    parser.add_argument(
        "--transcript-file",
        default="",
        help="Optional output .txt path for session transcript. If omitted in non-interactive mode, auto-saves to outputs/.",
    )
    parser.add_argument(
        "--input-file",
        default="",
        help="Optional file with prompts (one per line). Prefer this over shell redirection when combining with --continue-interactive.",
    )
    parser.add_argument(
        "--step-delay",
        type=float,
        default=0.0,
        help="Sleep seconds between prompts in batch mode (helps avoid API rate limits).",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="If > 0, process only the first N prompts from input-file/stdin batch input.",
    )
    parser.add_argument(
        "--continue-interactive",
        action="store_true",
        help="After finishing --input-file, continue in interactive mode.",
    )
    parser.add_argument(
        "--observability",
        action="store_true",
        help="Export observability data (traces, metrics, quality) to outputs/ at session end.",
    )
    parser.add_argument(
        "--export-diagram",
        action="store_true",
        help="Export the LangGraph state workflow diagram to a PNG file.",
    )
    args = parser.parse_args()

    app, pref_store, llm_client, version_snapshot, security, report_store, learning_store, report_generator = build_app(debug=args.debug)

    if args.export_diagram:
        try:
            png_bytes = app.get_graph().draw_mermaid_png()
            diagram_path = Path(__file__).parent / "outputs" / "langgraph_diagram.png"
            diagram_path.parent.mkdir(parents=True, exist_ok=True)
            diagram_path.write_bytes(png_bytes)
            print(f"LangGraph diagram generated at: {diagram_path}")
        except Exception as e:
            print(f"Failed to generate LangGraph diagram: {e}")

    # Observability infrastructure
    session_id = str(uuid.uuid4())[:8]
    tracer = Tracer()
    quality_evaluator = QualityEvaluator()
    base = Path(__file__).parent

    stdin_is_tty = os.isatty(0)
    input_file = Path(args.input_file) if args.input_file else None

    transcript_path: Optional[Path]
    if args.transcript_file:
        transcript_path = Path(args.transcript_file)
    elif not stdin_is_tty or input_file is not None:
        transcript_path = _default_transcript_path(base)
    else:
        transcript_path = None

    transcript = TranscriptWriter(transcript_path)

    def emit(text: str = "") -> None:
        print(text)
        transcript.write_line(text)

    emit("Retail Analytics Assistant")
    emit(f"Logged in as: {args.user_id.upper()}")
    emit("Type 'exit' to quit")
    emit("Use '/user <ID>' to switch user profile (e.g., manager_a, manager_b, ceo)")
    emit("Use '/format bullets' or '/format table' to set your report preference")
    emit("Use '/confirm <TOKEN>' to confirm destructive Saved Reports actions")
    emit("Use '/candidates' and '/approve_candidate <ID>' for learning-loop promotion")

    if args.user_id == "manager_a":
        emit("\nAssistant> Would you like to switch to Manager B? (Type '/user manager_b' to switch)")
    elif args.user_id == "manager_b":
        emit("\nAssistant> Would you like to switch to Manager A? (Type '/user manager_a' to switch)")

    batch_prompts: list[str] = []
    if input_file is not None:
        if not input_file.exists():
            emit(f"ERROR: input file not found: {input_file}")
            transcript.close()
            return
        batch_prompts = [line.strip() for line in input_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    elif not stdin_is_tty:
        for line in os.sys.stdin:
            line = line.strip()
            if line:
                batch_prompts.append(line)

    try:
        user_options = {
        "Manager A (Table pref)": "manager_a",
        "Manager B (Bullet pref)": "manager_b",
        "CEO (Strategic)": "ceo"
    }
    # The `st.selectbox` call is a Streamlit UI component and cannot be directly inserted into a CLI application's main function without Streamlit being imported and the application being run as a Streamlit app.
    # To maintain syntactic correctness and avoid introducing a dependency/runtime error, this line is commented out.
    # selected_label = st.selectbox("Switch User / Persona:", user_options.keys())

        processed = 0
        idx = 0
        while True:
            question = ""
            from_batch = False

            # Identification logic for CLI
            if not from_batch and idx == 0:
                emit(f"\nAssistant> Logged in as: {args.user_id.upper()}")
                if args.user_id == "manager_a":
                    emit("Assistant> Current profile: Manager A (Prefers Tables).")
                    emit("Assistant> Would you like to switch to Manager B (Bullet Points)? Type: /user manager_b")
                elif args.user_id == "manager_b":
                    emit("Assistant> Current profile: Manager B (Prefers Bullet Points).")
                elif args.user_id == "ceo":
                    emit("Assistant> Current profile: CEO (Strategic Tone).")
                    emit("Assistant> You can update system instructions by typing: 'From now on, use a [tone] tone...'")
                emit("Assistant> Type your question or /help for commands.")

            if idx < len(batch_prompts):
                question = batch_prompts[idx]
                idx += 1
                from_batch = True
                emit(f"\nYou> {question}")
            else:
                if batch_prompts and input_file is not None and args.continue_interactive:
                    batch_prompts = []
                elif not stdin_is_tty and input_file is None:
                    emit("Session ended (EOF on stdin).")
                    break

                try:
                    question = input("\nYou> ").strip()
                except EOFError:
                    emit("Session ended (EOF on stdin).")
                    break

            if not question:
                continue

            if question.lower() in {"exit", "quit"}:
                emit("Session ended.")
                break

            if question.lower().startswith("/format "):
                desired = question.split(" ", 1)[1].strip().lower()
                if desired not in {"table", "bullets"}:
                    emit("Assistant> Supported formats: table, bullets")
                else:
                    pref_store.set_format(args.user_id, desired)
                    emit(f"Assistant> Saved format preference for {args.user_id}: {desired}")
                processed += 1
                if args.max_steps > 0 and processed >= args.max_steps:
                    emit("Session ended (max steps reached).")
                    break
                if from_batch and args.step_delay > 0:
                    time.sleep(args.step_delay)
                continue

            if question.lower().startswith("/user "):
                new_user = question.split(" ", 1)[1].strip().lower()
                args.user_id = new_user
                emit(f"Assistant> Switched to user: {new_user.upper()}")
                processed += 1
                if args.max_steps > 0 and processed >= args.max_steps:
                    emit("Session ended (max steps reached).")
                    break
                if from_batch and args.step_delay > 0:
                    time.sleep(args.step_delay)
                continue

            if question.lower().startswith("/confirm "):
                token = question.split(" ", 1)[1].strip()
                ok, message = report_store.confirm_delete(token=token, user_id=args.user_id)
                emit("\nAssistant>")
                emit(message if ok else f"Confirmation failed: {message}")
                processed += 1
                if args.max_steps > 0 and processed >= args.max_steps:
                    emit("Session ended (max steps reached).")
                    break
                if from_batch and args.step_delay > 0:
                    time.sleep(args.step_delay)
                continue

            if question.lower() == "/candidates":
                pending = learning_store.list_pending(limit=10)
                emit("\nAssistant>")
                if not pending:
                    emit("No pending candidates.")
                else:
                    emit("Pending candidates:")
                    for item in pending:
                        emit(f"- {item['id']}: {item['question'][:100]}")
                processed += 1
                if args.max_steps > 0 and processed >= args.max_steps:
                    emit("Session ended (max steps reached).")
                    break
                if from_batch and args.step_delay > 0:
                    time.sleep(args.step_delay)
                continue

            if question.lower().startswith("/approve_candidate "):
                candidate_id = question.split(" ", 1)[1].strip()
                ok, message = learning_store.approve_candidate(candidate_id)
                emit("\nAssistant>")
                emit(message if ok else f"Approval failed: {message}")
                processed += 1
                if args.max_steps > 0 and processed >= args.max_steps:
                    emit("Session ended (max steps reached).")
                    break
                if from_batch and args.step_delay > 0:
                    time.sleep(args.step_delay)
                continue

            state = new_state(question=question, user_id=args.user_id)
            conversation_id = str(uuid.uuid4())[:8]
            invoke_config = {
                "configurable": {
                    "thread_id": f"{args.user_id}:cli:{conversation_id}",
                }
            }

            # --- Begin trace ---
            trace_meta = TraceMetadata(
                agent_version=version_snapshot.components.get("agent_version", ""),
                prompt_version=version_snapshot.components.get("prompts", ""),
                model_name=llm_client.model_name,
                workflow_version=version_snapshot.components.get("workflow", ""),
                question=question[:500],
            )
            ctx = tracer.begin_trace(
                session_id=session_id,
                conversation_id=conversation_id,
                user_id=args.user_id,
                metadata=trace_meta,
            )

            # Prompt injection detection
            is_injection, injection_reason = security.detect_prompt_injection(question)
            if is_injection:
                security.record_audit(
                    action="prompt_injection_detected",
                    actor=args.user_id,
                    trace_id=ctx.trace.trace_id,
                    details={"reason": injection_reason, "question": question[:200]},
                )

            # Reset per-request flag so we can attribute fallback usage correctly.
            if hasattr(llm_client, "used_fallback"):
                llm_client.used_fallback = False

            start = time.perf_counter()
            try:
                result = app.invoke(state, config=invoke_config)
            except Exception:
                emit("\nAssistant>")
                emit(
                    "I hit an internal processing issue for this request. "
                    "Please try again with a shorter or clearer analytical question."
                )
                elapsed = (time.perf_counter() - start) * 1000
                record_metric("total_latency_ms", elapsed, status="error")

                # End trace on error
                try:
                    trace = tracer.end_trace()
                    trace.metadata.final_status = "failed_runtime"
                except Exception:
                    pass

                if args.debug:
                    emit("\n[debug]")
                    emit("status=failed_runtime")
                    emit(f"elapsed_ms={elapsed:.2f}")
                processed += 1
                if args.max_steps > 0 and processed >= args.max_steps:
                    emit("Session ended (max steps reached).")
                    break
                if from_batch and args.step_delay > 0:
                    time.sleep(args.step_delay)
                continue

            elapsed = (time.perf_counter() - start) * 1000
            final_status = result.get("final_status", "unknown")
            record_metric("total_latency_ms", elapsed, status=final_status)

            # Update trace metadata and end trace
            ctx.trace.metadata.final_status = final_status
            trace = tracer.end_trace()

            # Audit: record execution
            security.record_audit(
                action="query_executed",
                actor=args.user_id,
                trace_id=trace.trace_id,
                details={
                    "question": question[:200],
                    "status": final_status,
                    "elapsed_ms": round(elapsed, 2),
                },
            )

            # Quality evaluation
            quality_evaluator.evaluate(
                trace_id=trace.trace_id,
                question=question,
                final_report=result.get("final_report"),
                result_rows=result.get("result_rows"),
                final_status=final_status,
                used_fallback=bool(getattr(llm_client, "used_fallback", False)) or (not llm_client.enabled),
            )

            emit("\nAssistant>")
            emit(result.get("final_report", "I could not complete this request."))

            if (
                result.get("final_status") == "success"
                and result.get("validated_sql", "").strip()
            ):
                learning_store.capture_candidate(
                    question=question,
                    sql=result.get("validated_sql", ""),
                    report=result.get("final_report", ""),
                )

            if args.debug:
                debug_sql = result.get("validated_sql") or result.get("sql_candidate", "")
                emit("\n[debug]")
                emit(f"status={final_status}")
                emit(f"retry_count={result.get('retry_count', 0)}")
                emit(f"elapsed_ms={elapsed:.2f}")
                emit(f"sql={debug_sql}")
                emit(f"trace_id={trace.trace_id}")
                emit(f"spans={len(trace.spans)}")

            processed += 1
            if args.max_steps > 0 and processed >= args.max_steps:
                emit("Session ended (max steps reached).")
                break
            if from_batch and args.step_delay > 0:
                time.sleep(args.step_delay)
    finally:
        # Export observability data if requested
        if args.observability:
            tool_obs = get_tool_observer()
            retrieval_store = get_retrieval_store()
            exporter = ObservabilityExporter(base / "outputs")

            export_path = exporter.export_session(
                session_id=session_id,
                traces=tracer.store.traces,
                metrics_collector=get_collector(),
                tool_invocations=tool_obs.invocations,
                tool_summary=tool_obs.get_summary(),
                retrieval_observations=retrieval_store.observations,
                retrieval_summary=retrieval_store.get_summary(),
                quality_signals=quality_evaluator.signals,
                quality_summary=quality_evaluator.get_summary(),
                audit_log=security.audit_log,
                version_snapshot=version_snapshot,
            )

            summary = ObservabilityExporter.format_cli_summary(
                traces=tracer.store.traces,
                metrics_summary=get_collector().get_summary(),
                tool_summary=tool_obs.get_summary(),
                quality_summary=quality_evaluator.get_summary(),
            )
            print(summary)
            print(f"\nObservability data exported: {export_path}")

        if transcript.path is not None:
            print(f"\nTranscript saved: {transcript.path}")
        transcript.close()


if __name__ == "__main__":
    main()
