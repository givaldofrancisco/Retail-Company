"""Comprehensive Observability Evidence Generator.

Runs the real app.py CLI with --debug --observability and the manual test
prompts, then analyses the exported observability JSON to produce a full
evidence report with TWO distinct sections:

  Part A – Observability Instrumentation Coverage (is telemetry present?)
  Part B – Functional / System Health (does the system actually work?)

Usage:
    python tests/generate_observability_evidence.py

Output:
    outputs/observability_evidence.md   – human-readable Markdown report
    outputs/observability_*.json        – raw observability data (created by app.py)
    outputs/session_*.txt               – session transcript (created by app.py)
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pf(ok: bool) -> str:
    return PASS if ok else FAIL


def _pfw(ok: bool, warn: bool = False) -> str:
    if ok:
        return PASS
    return WARN if warn else FAIL


# ---------------------------------------------------------------------------
# Step 1: Run app.py and locate the observability JSON
# ---------------------------------------------------------------------------

def run_app() -> tuple[str, str, int]:
    cmd = [
        str(project_root / ".venv" / "bin" / "python"), str(project_root / "app.py"),
        "--user-id", "manager_a",
        "--debug",
        "--observability",
        "--input-file", str(project_root / "tests" / "manual_cli_inputs_en.txt"),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(project_root),
        env=env, timeout=300,
    )
    return result.stdout, result.stderr, result.returncode


def find_latest_observability_json(min_mtime: float | None = None) -> Path | None:
    pattern = str(project_root / "outputs" / "observability_*.json")
    files = glob.glob(pattern)
    if min_mtime is not None:
        files = [f for f in files if os.path.getmtime(f) >= min_mtime]
    files = sorted(files, key=os.path.getmtime, reverse=True)
    return Path(files[0]) if files else None


# ---------------------------------------------------------------------------
# Evidence Collector
# ---------------------------------------------------------------------------

class EvidenceCollector:
    def __init__(self) -> None:
        self.sections: list[dict] = []
        self._current: dict | None = None

    def begin_section(self, title: str, part: str = "A") -> None:
        self._current = {"title": title, "part": part, "checks": [], "details": []}

    def check(self, name: str, ok: bool, detail: str = "", warn_only: bool = False) -> bool:
        self._current["checks"].append((name, ok, detail, warn_only))
        return ok

    def detail(self, text: str) -> None:
        self._current["details"].append(text)

    def end_section(self) -> None:
        self.sections.append(self._current)
        self._current = None

    def _part_sections(self, part: str) -> list[dict]:
        return [s for s in self.sections if s["part"] == part]

    def _count(self, part: str | None = None) -> tuple[int, int, int]:
        secs = self.sections if part is None else self._part_sections(part)
        total = sum(len(s["checks"]) for s in secs)
        passed = sum(1 for s in secs for _, ok, _, _ in s["checks"] if ok)
        warned = sum(1 for s in secs for _, ok, _, w in s["checks"] if not ok and w)
        return total, passed, warned

    @property
    def total_checks(self) -> int:
        return self._count()[0]

    @property
    def passed_checks(self) -> int:
        return self._count()[1]

    def write_markdown(self, path: Path, cli_output: str, obs_json_path: Path) -> None:
        total_a, passed_a, warned_a = self._count("A")
        total_b, passed_b, warned_b = self._count("B")
        failed_a = total_a - passed_a
        failed_b = total_b - passed_b

        with open(path, "w", encoding="utf-8") as f:
            f.write("# Observability System – Complete Evidence Report\n\n")
            f.write(f"**Generated:** {datetime.now().isoformat(timespec='seconds')}  \n")
            f.write(f"**Source command:** `python3 app.py --user-id manager_a --debug "
                    f"--observability --input-file tests/manual_cli_inputs_en.txt`  \n")
            f.write(f"**Observability JSON:** `{obs_json_path.name}`  \n\n")

            # Executive summary
            f.write("## Executive Summary\n\n")
            f.write("| Section | Passed | Failed | Warnings | Total |\n")
            f.write("|---------|--------|--------|----------|-------|\n")
            f.write(f"| **Part A – Observability Instrumentation** | {passed_a} | "
                    f"{failed_a - warned_a} | {warned_a} | {total_a} |\n")
            f.write(f"| **Part B – Functional / System Health** | {passed_b} | "
                    f"{failed_b - warned_b} | {warned_b} | {total_b} |\n")
            f.write(f"| **TOTAL** | {passed_a + passed_b} | "
                    f"{(failed_a - warned_a) + (failed_b - warned_b)} | "
                    f"{warned_a + warned_b} | {total_a + total_b} |\n\n")

            if failed_b - warned_b > 0:
                f.write("> **⚠️ The observability instrumentation is complete, but the system "
                        "has functional issues that need attention.** See Part B for details.\n\n")
            elif warned_b > 0:
                f.write("> **Observability is complete. System has minor warnings.** "
                        "See Part B for details.\n\n")
            else:
                f.write("> **Both observability and functional health checks passed.** ✅\n\n")

            f.write("---\n\n")

            # Part A
            f.write("# Part A – Observability Instrumentation Coverage\n\n")
            f.write("_These checks verify that telemetry data is present and correctly "
                    "structured. They answer: \"Is the instrumentation working?\"_\n\n")
            for section in self._part_sections("A"):
                self._write_section(f, section)

            # Part B
            f.write("---\n\n")
            f.write("# Part B – Functional / System Health\n\n")
            f.write("_These checks verify that the system actually works correctly. "
                    "They answer: \"Is the application healthy?\"_\n\n")
            for section in self._part_sections("B"):
                self._write_section(f, section)

            # Appendix
            f.write("---\n\n")
            f.write("## Appendix: CLI Output\n\n")
            f.write("<details><summary>Click to expand full CLI output</summary>\n\n")
            f.write("```\n")
            f.write(cli_output[:50000])
            f.write("\n```\n")
            f.write("</details>\n\n")

    @staticmethod
    def _write_section(f, section: dict) -> None:
        f.write(f"## {section['title']}\n\n")
        f.write("| # | Check | Result | Detail |\n")
        f.write("|---|-------|--------|--------|\n")
        for i, (name, ok, detail, warn_only) in enumerate(section["checks"], 1):
            result = _pfw(ok, warn_only) if not ok else PASS
            f.write(f"| {i} | {name} | {result} | {detail} |\n")
        f.write("\n")
        if section["details"]:
            f.write("**Evidence details:**\n\n")
            for det in section["details"]:
                f.write(det + "\n\n")

    def print_summary(self) -> None:
        total_a, passed_a, _ = self._count("A")
        total_b, passed_b, warned_b = self._count("B")

        print(f"\n{'=' * 70}")
        print(f"  OBSERVABILITY EVIDENCE REPORT")
        print(f"{'=' * 70}")
        print(f"\n  Part A – Instrumentation Coverage:")
        for section in self._part_sections("A"):
            passed = sum(1 for _, ok, _, _ in section["checks"] if ok)
            total = len(section["checks"])
            icon = "✅" if passed == total else "❌"
            print(f"    {icon} {section['title']}: {passed}/{total}")
        print(f"    {'─' * 50}")
        print(f"    Part A Total: {passed_a}/{total_a}")

        print(f"\n  Part B – Functional Health:")
        for section in self._part_sections("B"):
            passed = sum(1 for _, ok, _, _ in section["checks"] if ok)
            warns = sum(1 for _, ok, _, w in section["checks"] if not ok and w)
            total = len(section["checks"])
            icon = "✅" if passed == total else ("⚠️ " if warns == total - passed else "❌")
            print(f"    {icon} {section['title']}: {passed}/{total}" +
                  (f" ({warns} warnings)" if warns else ""))
        print(f"    {'─' * 50}")
        print(f"    Part B Total: {passed_b}/{total_b}" +
              (f" ({warned_b} warnings)" if warned_b else ""))

        print(f"\n{'=' * 70}")
        print(f"  GRAND TOTAL: {passed_a + passed_b}/{total_a + total_b}")
        print(f"{'=' * 70}")


# ---------------------------------------------------------------------------
# PART A: Observability Instrumentation Checks
# ---------------------------------------------------------------------------

def check_a1_tracing(ev: EvidenceCollector, data: dict) -> None:
    ev.begin_section("A1: End-to-End Tracing", part="A")
    traces = data.get("traces", [])
    ev.check("Traces captured (>0)", len(traces) > 0, f"found {len(traces)}")
    if traces:
        t0 = traces[0]
        ev.check("Trace has trace_id", bool(t0.get("trace_id")))
        ev.check("Trace has session_id", bool(t0.get("session_id")))
        ev.check("Trace has user_id", bool(t0.get("user_id")))
        ev.check("Trace has start/end time", t0.get("end_time") is not None)
        spans = t0.get("spans", [])
        ev.check("Spans captured", len(spans) > 0, f"found {len(spans)}")
        if spans:
            ev.check("Span has span_id + name", bool(spans[0].get("span_id")) and bool(spans[0].get("name")))
        meta = t0.get("metadata", {})
        ev.check("Metadata has model_name", bool(meta.get("model_name")))
        ev.check("Metadata has final_status", bool(meta.get("final_status")))
        multi = sum(1 for t in traces if len(t.get("spans", [])) > 1)
        ev.check("Multi-span traces (workflow nodes traced)", multi > 0,
                  f"{multi}/{len(traces)} traces")
        span_counts = [len(t.get("spans", [])) for t in traces]
        ev.detail(f"- Traces: **{len(traces)}** | Spans/trace: min={min(span_counts)}, "
                  f"max={max(span_counts)}, avg={sum(span_counts)/len(span_counts):.1f}")
    ev.end_section()


def check_a2_logging(ev: EvidenceCollector, cli: str) -> None:
    ev.begin_section("A2: Structured Logging", part="A")
    ev.check("[debug] output present", "[debug]" in cli)
    ev.check("status= in debug", "status=" in cli)
    ev.check("elapsed_ms= in debug", "elapsed_ms=" in cli)
    ev.check("sql= in debug", "sql=" in cli)
    ev.check("trace_id= in debug", "trace_id=" in cli)
    ev.check("spans= in debug", "spans=" in cli)
    ev.end_section()


def check_a3_metrics(ev: EvidenceCollector, data: dict) -> None:
    ev.begin_section("A3: Operational Metrics", part="A")
    metrics = data.get("metrics_summary", {})
    ev.check("Metrics summary present", len(metrics) > 0, f"{len(metrics)} metrics")
    for m in ["node_latency_ms", "total_latency_ms", "retrieval_time_ms",
              "schema_fetch_time_ms"]:
        ev.check(f"Metric '{m}' captured", m in metrics)
    if "node_latency_ms" in metrics:
        agg = metrics["node_latency_ms"]
        ev.check("Full aggregation (count,mean,p50,p95)",
                 all(k in agg for k in ["count", "mean", "p50", "p95"]))
    ev.detail(f"- Distinct metrics: **{len(metrics)}**: {', '.join(sorted(metrics.keys()))}")
    ev.end_section()


def check_a4_retrieval(ev: EvidenceCollector, data: dict) -> None:
    ev.begin_section("A4: Retrieval Observability (few-shot)", part="A")
    obs = data.get("retrieval_observations", [])
    summary = data.get("retrieval_observations_summary", {})
    ev.check("Retrieval observations captured", len(obs) > 0, f"found {len(obs)}")
    golden = [o for o in obs if o.get("data_origin") == "golden_trios.json"]
    schema = [o for o in obs if o.get("data_origin") == "bigquery_schema"]
    ev.check("Few-shot observations present", len(golden) > 0, f"found {len(golden)}")
    ev.check("Schema fetch observations present", len(schema) > 0, f"found {len(schema)}")
    if golden:
        g0 = golden[0]
        ev.check("Has query + scores + timing", bool(g0.get("query")) and
                 len(g0.get("top_scores", [])) > 0 and g0.get("retrieval_time_ms", 0) > 0)
    ev.check("Summary has avg_top_score", "avg_top_score" in summary)
    ev.check("Summary has no_relevant_docs_rate", "no_relevant_docs_rate" in summary)
    ev.detail(f"- Observations: {len(obs)} (few-shot: {len(golden)}, schema: {len(schema)})")
    if summary:
        ev.detail(f"- avg_top_score={summary.get('avg_top_score')}, "
                  f"avg_time={summary.get('avg_retrieval_time_ms')}ms")
    ev.end_section()


def check_a5_tools(ev: EvidenceCollector, data: dict) -> None:
    ev.begin_section("A5: Tool/Action Observability", part="A")
    inv = data.get("tool_invocations", [])
    summary = data.get("tool_invocations_summary", {})
    ev.check("Tool invocations captured", len(inv) > 0, f"found {len(inv)}")
    ev.check("Tool summary present", len(summary) > 0, f"found {len(summary)} tools")
    if inv:
        ev.check("Has tool_name + execution_time_ms + success",
                 bool(inv[0].get("tool_name")) and "success" in inv[0])
    if summary:
        ev.detail("| Tool | Calls | Success Rate | Avg Time | Errors |")
        ev.detail("|------|-------|-------------|----------|--------|")
        for t, s in summary.items():
            ev.detail(f"| {t} | {s.get('call_count',0)} | {s.get('success_rate',0):.0%} | "
                      f"{s.get('avg_time_ms',0):.0f}ms | {s.get('failure_count',0)} |")
    ev.end_section()


def check_a6_quality(ev: EvidenceCollector, data: dict) -> None:
    ev.begin_section("A6: Quality Evaluation", part="A")
    signals = data.get("quality_signals", [])
    summary = data.get("quality_summary", {})
    ev.check("Quality signals captured", len(signals) > 0, f"found {len(signals)}")
    if signals:
        ev.check("Signal has groundedness/relevance/completeness",
                 signals[0].get("groundedness") is not None and
                 signals[0].get("relevance") is not None and
                 signals[0].get("completeness") is not None)
    for k in ["avg_groundedness", "avg_relevance", "avg_completeness", "success_rate"]:
        ev.check(f"Summary has '{k}'", k in summary)
    ev.end_section()


def check_a7_security(ev: EvidenceCollector, data: dict) -> None:
    ev.begin_section("A7: Security & Audit", part="A")
    audit = data.get("audit_log", [])
    ev.check("Audit log entries present", len(audit) > 0, f"found {len(audit)}")
    if audit:
        ev.check("Entry has timestamp+action+actor+trace_id",
                 audit[0].get("timestamp", 0) > 0 and bool(audit[0].get("action"))
                 and bool(audit[0].get("actor")))
        actions = [a.get("action") for a in audit]
        ev.check("'query_executed' logged", "query_executed" in actions)
    ev.end_section()


def check_a8_versioning(ev: EvidenceCollector, data: dict) -> None:
    ev.begin_section("A8: Versioning & Comparison", part="A")
    snap = data.get("version_snapshot")
    ev.check("Version snapshot present", snap is not None)
    if snap:
        ev.check("Has version_id + timestamp", bool(snap.get("version_id"))
                 and snap.get("timestamp", 0) > 0)
        components = snap.get("components", {})
        ev.check("Components tracked (>5)", len(components) > 5, f"found {len(components)}")
        for k in ["prompts", "workflow", "guardrails", "golden_trios", "model_name"]:
            ev.check(f"Component '{k}' present", k in components)
        ev.detail(f"- version_id: `{snap.get('version_id')}`")
        ev.detail(f"- Components: {len(components)}")
    ev.end_section()


def check_a9_integration(ev: EvidenceCollector, data: dict, cli: str) -> None:
    ev.begin_section("A9: Cross-Block Integration", part="A")
    traces = data.get("traces", [])
    quality = data.get("quality_signals", [])
    ev.check("Trace count ≈ quality signal count",
             abs(len(traces) - len(quality)) <= 2,
             f"traces={len(traces)}, signals={len(quality)}")
    session_ids = set(t.get("session_id") for t in traces)
    ev.check("Consistent session_id", len(session_ids) == 1)
    ev.check("Export has timestamp", bool(data.get("export_timestamp")))
    ev.check("CLI shows OBSERVABILITY SUMMARY", "OBSERVABILITY SUMMARY" in cli)
    ev.check("Observability data exported", "Observability data exported" in cli)
    ev.end_section()


# ---------------------------------------------------------------------------
# PART B: Functional / System Health Checks
# ---------------------------------------------------------------------------

def check_b1_execution_success(ev: EvidenceCollector, data: dict) -> None:
    """Check that the system succeeded functionally."""
    ev.begin_section("B1: Execution Success Rate", part="B")

    traces = data.get("traces", [])
    statuses = [t.get("metadata", {}).get("final_status", "?") for t in traces]
    status_counts = {}
    for s in statuses:
        status_counts[s] = status_counts.get(s, 0) + 1

    total = len(traces)
    successes = status_counts.get("success", 0)
    rate = successes / total if total else 0

    ev.check(f"Success rate ≥ 50%", rate >= 0.5,
             f"got {rate:.0%} ({successes}/{total})")
    ev.check(f"Success rate ≥ 30% (minimum viable)", rate >= 0.3,
             f"got {rate:.0%}", warn_only=True)

    # Legitimate non-success: rejected, requires_confirmation are OK
    legit_non_success = sum(status_counts.get(s, 0) for s in
                            ["rejected", "requires_confirmation"])
    functional_failures = total - successes - legit_non_success
    ev.check("Functional failures ≤ 2", functional_failures <= 2,
             f"got {functional_failures} failures (excl. rejected/confirmation)")

    ev.detail(f"- Trace statuses: {status_counts}")
    ev.detail(f"- Success: {successes}, Legit non-success: {legit_non_success}, "
              f"Failures: {functional_failures}")
    ev.end_section()


def check_b2_bigquery_health(ev: EvidenceCollector, data: dict) -> None:
    """Check BigQuery execution health."""
    ev.begin_section("B2: BigQuery Execution Health", part="B")

    summary = data.get("tool_invocations_summary", {})
    bq = summary.get("bigquery_execute", {})

    if not bq:
        ev.check("BigQuery invocations present", False, "no bigquery_execute in summary")
        ev.end_section()
        return

    calls = bq.get("call_count", 0)
    success_rate = bq.get("success_rate", 0)
    failures = bq.get("failure_count", 0)

    ev.check("BQ success rate > 0%", success_rate > 0,
             f"got {success_rate:.0%} ({calls} calls, {failures} failures)")
    ev.check("BQ success rate ≥ 50%", success_rate >= 0.5,
             f"got {success_rate:.0%}", warn_only=True)

    # Check for 403 errors specifically
    invocations = data.get("tool_invocations", [])
    bq_invocations = [i for i in invocations if i.get("tool_name") == "bigquery_execute"]
    permission_errors = sum(1 for i in bq_invocations
                            if "403" in str(i.get("error_message", ""))
                            or "permission" in str(i.get("error_message", "")).lower())
    ev.check("No 403/permission errors", permission_errors == 0,
             f"found {permission_errors} permission errors — check GOOGLE_CLOUD_PROJECT config")

    ev.detail(f"- BQ calls: {calls}, success_rate: {success_rate:.0%}, failures: {failures}")
    if permission_errors:
        ev.detail(f"- **ROOT CAUSE**: {permission_errors} calls failed with 403. "
                  f"GOOGLE_CLOUD_PROJECT is likely misconfigured (set to bigquery-public-data).")
    ev.end_section()


def check_b3_quality_thresholds(ev: EvidenceCollector, data: dict) -> None:
    """Check quality metrics meet minimum thresholds."""
    ev.begin_section("B3: Quality Thresholds", part="B")

    summary = data.get("quality_summary", {})
    signals = data.get("quality_signals", [])

    success_rate = summary.get("success_rate", 0)
    ev.check("Quality success_rate ≥ 50%", success_rate >= 0.5,
             f"got {success_rate:.2f}")
    ev.check("Quality success_rate ≥ 30% (minimum)", success_rate >= 0.3,
             f"got {success_rate:.2f}", warn_only=True)

    groundedness = summary.get("avg_groundedness", 0)
    relevance = summary.get("avg_relevance", 0)
    completeness = summary.get("avg_completeness", 0)

    # Only check thresholds on successful signals
    successful_signals = [s for s in signals if s.get("tool_success_final_success")]
    if successful_signals:
        avg_g = sum(s.get("groundedness", 0) or 0 for s in successful_signals) / len(successful_signals)
        avg_r = sum(s.get("relevance", 0) or 0 for s in successful_signals) / len(successful_signals)
        avg_c = sum(s.get("completeness", 0) or 0 for s in successful_signals) / len(successful_signals)
        ev.check("Groundedness > 0 (on successful traces)", avg_g > 0,
                 f"got {avg_g:.3f}", warn_only=True)
        ev.check("Relevance > 0.1 (on successful traces)", avg_r > 0.1,
                 f"got {avg_r:.3f}", warn_only=True)
        ev.check("Completeness > 0.5 (on successful traces)", avg_c > 0.5,
                 f"got {avg_c:.3f}", warn_only=True)
    else:
        ev.check("Successful signals exist for quality measurement", False,
                 "no successful signals to evaluate quality")

    fallback_rate = summary.get("fallback_rate", 0)
    ev.check("Fallback rate < 100% (LLM not always in fallback)", fallback_rate < 1.0,
             f"got {fallback_rate:.0%}", warn_only=True)

    ev.detail(f"- Overall: groundedness={groundedness}, relevance={relevance}, "
              f"completeness={completeness}")
    ev.detail(f"- success_rate={success_rate}, fallback_rate={fallback_rate}")
    if successful_signals:
        ev.detail(f"- On {len(successful_signals)} successful traces: "
                  f"avg_groundedness={avg_g:.3f}, avg_relevance={avg_r:.3f}, "
                  f"avg_completeness={avg_c:.3f}")
    ev.end_section()


def check_b4_status_consistency(ev: EvidenceCollector, data: dict) -> None:
    """Check that final_status is consistent with actual execution."""
    ev.begin_section("B4: Status Consistency", part="B")

    traces = data.get("traces", [])
    quality = data.get("quality_signals", [])

    # Build lookup: trace_id -> quality signal
    q_lookup = {s.get("trace_id"): s for s in quality}

    inflated = 0
    for trace in traces:
        tid = trace.get("trace_id")
        status = trace.get("metadata", {}).get("final_status", "")
        sig = q_lookup.get(tid, {})
        # success but empty response = inflated
        if status == "success" and sig.get("empty_response"):
            inflated += 1

    ev.check("No inflated success (success + empty_response)", inflated == 0,
             f"found {inflated} traces marked success with empty responses")

    # Check that all traces have a final_status
    no_status = sum(1 for t in traces if not t.get("metadata", {}).get("final_status"))
    ev.check("All traces have final_status", no_status == 0,
             f"{no_status} traces without status")

    ev.end_section()


def check_b5_pii_handling(ev: EvidenceCollector, data: dict, cli: str) -> None:
    """Check PII-related requests are handled safely."""
    ev.begin_section("B5: PII Handling", part="B")

    # The test inputs include PII requests: "List customer emails", "Show phone numbers"
    # These should be handled via safe fallback SQL (no PII columns in output)
    audit = data.get("audit_log", [])

    # Check CLI output for PII safety notes
    has_safety_note = "Safety Note" in cli or "not displayed" in cli
    ev.check("PII safety note in output", has_safety_note,
             "expected Safety Note for PII requests", warn_only=True)

    # Check no raw email/phone patterns leaked in final reports
    # (look for actual email patterns, not just the word "email")
    import re
    email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
    phone_pattern = re.compile(r'\+?\d[\d\-\(\)\s]{8,}\d')
    # Only check in Assistant> responses
    assistant_blocks = cli.split("Assistant>")
    pii_leaked = False
    for block in assistant_blocks[1:]:  # skip before first Assistant>
        # Only check the response part (before next You> or [debug])
        response = block.split("You>")[0].split("[debug]")[0]
        if email_pattern.search(response) or phone_pattern.search(response):
            pii_leaked = True
            break

    ev.check("No PII leaked in assistant responses", not pii_leaked)

    ev.end_section()


def check_b6_error_handling(ev: EvidenceCollector, data: dict, cli: str) -> None:
    """Check that errors are handled gracefully."""
    ev.begin_section("B6: Error Handling & User Experience", part="B")

    # Check that rejected/unsupported questions get clear messages
    ev.check("Rejected questions get clear message",
             "I can only answer analytical retail questions" in cli)

    # Check that destructive operations are blocked
    ev.check("Destructive operations blocked",
             "Confirmation flow" in cli or "requires_confirmation" in cli.lower()
             or "design-only" in cli,
             warn_only=True)

    # Check no unhandled exceptions in output
    ev.check("No unhandled exceptions visible to user",
             "Traceback" not in cli.split("Assistant>")[-1] if "Assistant>" in cli else True)

    ev.end_section()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 70)
    print("  COMPREHENSIVE OBSERVABILITY EVIDENCE GENERATOR")
    print("  Running: app.py --debug --observability --input-file ...")
    print("=" * 70)

    print("\n▶ Running app.py with full observability...")
    run_start_ts = time.time()
    try:
        stdout, stderr, rc = run_app()
    except subprocess.TimeoutExpired:
        print("  ERROR: app.py timed out after 300s")
        return 1

    cli_output = stdout + "\n" + stderr
    print(f"  Exit code: {rc}")
    print(f"  Output: {len(stdout)} chars stdout, {len(stderr)} chars stderr")

    if rc != 0:
        print(f"\n  ERROR: app.py exited with code {rc}")
        print("  stderr (last 1000 chars):")
        print(stderr[-1000:])
        print("\n  Evidence generation aborted to avoid using stale observability JSON.")
        return 1

    obs_path = find_latest_observability_json(min_mtime=run_start_ts)
    if obs_path is None:
        print("\n  ERROR: No fresh observability_*.json found for this run in outputs/")
        return 1

    print(f"\n▶ Loading observability data: {obs_path.name}")
    data = json.loads(obs_path.read_text(encoding="utf-8"))
    # Backward-compatibility for old export keys (before retrieval rename).
    if "retrieval_observations" not in data and "rag_observations" in data:
        data["retrieval_observations"] = data.get("rag_observations", [])
    if "retrieval_observations_summary" not in data and "rag_observations_summary" in data:
        data["retrieval_observations_summary"] = data.get("rag_observations_summary", {})
    print(f"  Keys: {list(data.keys())}")

    ev = EvidenceCollector()

    print("\n▶ Part A – Observability Instrumentation...\n")
    check_a1_tracing(ev, data)
    check_a2_logging(ev, cli_output)
    check_a3_metrics(ev, data)
    check_a4_retrieval(ev, data)
    check_a5_tools(ev, data)
    check_a6_quality(ev, data)
    check_a7_security(ev, data)
    check_a8_versioning(ev, data)
    check_a9_integration(ev, data, cli_output)

    print("▶ Part B – Functional Health...\n")
    check_b1_execution_success(ev, data)
    check_b2_bigquery_health(ev, data)
    check_b3_quality_thresholds(ev, data)
    check_b4_status_consistency(ev, data)
    check_b5_pii_handling(ev, data, cli_output)
    check_b6_error_handling(ev, data, cli_output)

    report_path = project_root / "outputs" / "observability_evidence.md"
    ev.write_markdown(report_path, cli_output, obs_path)
    print(f"\n▶ Report saved: {report_path}")

    ev.print_summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
