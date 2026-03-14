#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


TEST_FILES = [
    "tests/test_assignment_acceptance.py",
    "tests/test_langgraph_memory_setup.py",
    "tests/test_manual_cli_replay.py",
    "tests/test_llm_resilience.py",
    "tests/test_sql_validator.py",
    "tests/test_pii_masking.py",
    "tests/test_repair_loop.py",
    "tests/test_guardrails_flow.py",
    "tests/test_report_actions.py",
    "tests/test_learning_loop.py",
    "tests/test_qa_gate.py",
]


def run_test_file(test_file: str) -> tuple[bool, float, str]:
    start = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", test_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    elapsed = time.perf_counter() - start
    return result.returncode == 0, elapsed, result.stdout.strip()


def main() -> int:
    root = Path(__file__).resolve().parent
    print("=" * 64)
    print("Retail Company - Test Runner")
    print(f"Python: {sys.executable}")
    print(f"Root:   {root}")
    print("=" * 64)

    check = subprocess.run(
        [sys.executable, "-m", "pytest", "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if check.returncode != 0:
        print("ERRO: pytest não encontrado neste Python.")
        print("Ative a venv e instale dependências:")
        print("  source .venv/bin/activate")
        print("  pip install -r requirements.txt")
        return 1

    passed = 0
    failed = 0
    total_time = 0.0

    for test_file in TEST_FILES:
        ok, elapsed, output = run_test_file(test_file)
        total_time += elapsed
        status = "PASSOU" if ok else "FALHOU"
        print(f"\n[{status}] {test_file} ({elapsed:.2f}s)")

        lines = [line for line in output.splitlines() if line.strip()]
        preview = lines[-5:] if len(lines) > 5 else lines
        for line in preview:
            print(f"  {line}")

        if ok:
            passed += 1
        else:
            failed += 1

    print("\n" + "-" * 64)
    print("Resumo Final")
    print(f"  Suítes executadas: {len(TEST_FILES)}")
    print(f"  Suítes aprovadas:  {passed}")
    print(f"  Suítes com falha:  {failed}")
    print(f"  Tempo total:       {total_time:.2f}s")
    print("-" * 64)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
