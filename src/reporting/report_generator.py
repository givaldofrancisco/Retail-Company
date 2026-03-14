from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml

import sys

# Add project root to sys.path to resolve 'src' when run directly
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.llm.client import LLMClient


@dataclass
class ReportGenerator:
    llm: LLMClient
    personas_dir: Path

    def _load_persona(self, persona_id: str = "default") -> Dict[str, Any]:
        persona_path = self.personas_dir / f"{persona_id}.yaml"
        if not persona_path.exists():
            persona_path = self.personas_dir / "default.yaml"
        return yaml.safe_load(persona_path.read_text(encoding="utf-8"))

    def get_persona_voice(self, persona_id: str = "default") -> str:
        """Retrieve the 'voice' field from the persona YAML."""
        persona = self._load_persona(persona_id)
        return persona.get("voice", "concise, factual, business-oriented")

    def batch_update_personas(self, updated_voice: str):
        """Update the 'voice' field in all persona YAML files."""
        personas = list(self.personas_dir.glob("*.yaml"))
        for p_file in personas:
            try:
                content = yaml.safe_load(p_file.read_text(encoding="utf-8"))
                if content:
                    content["voice"] = updated_voice
                    p_file.write_text(yaml.dump(content, sort_keys=False), encoding="utf-8")
            except Exception as e:
                import logging
                logging.error(f"Failed to update persona {p_file.name}: {e}")

    def generate(
        self,
        question: str,
        rows: List[Dict[str, Any]],
        preference_format: str,
        golden_examples: List[Dict[str, Any]],
        removed_pii_columns: List[str],
        persona_id: str = "default",
    ) -> str:
        persona = self._load_persona(persona_id)
        persona_text = json.dumps(persona, indent=2)

        report = self.llm.generate_report(
            question=question,
            row_count=len(rows),
            data_preview=rows[:20],
            persona_text=persona_text,
            preference_format=preference_format,
            golden_examples=golden_examples,
        )

        compare_note = self._try_month_compare(question, rows)
        if compare_note:
            report += "\n\n" + compare_note

        if self._should_include_table(question, preference_format):
            table = self._format_table(rows[:10])
            if table:
                report += "\n\nTop results (preview):\n" + table

        if removed_pii_columns:
            report += (
                "\n\nSafety Note: Sensitive columns were removed before analysis output "
                f"({', '.join(removed_pii_columns)})."
            )
        return report

    @staticmethod
    def _should_include_table(question: str, preference_format: str) -> bool:
        q = question.lower()
        return (
            preference_format == "table"
            or "top" in q
            or "ranking" in q
            or "rank" in q
            or "top 10" in q
        )

    @staticmethod
    def _format_table(rows: List[Dict[str, Any]]) -> str:
        if not rows:
            return ""
        columns = list(rows[0].keys())
        header = "| " + " | ".join(columns) + " |"
        separator = "| " + " | ".join("---" for _ in columns) + " |"
        body_lines = []
        for row in rows:
            body_lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
        return "\n".join([header, separator] + body_lines)

    @staticmethod
    def _try_month_compare(question: str, rows: List[Dict[str, Any]]) -> str:
        q = question.lower()
        if "compare" not in q or "month" not in q:
            return ""
        if len(rows) < 2:
            return ""
        if any(("month" not in row or "revenue" not in row) for row in rows[:2]):
            return ""
        # Expect rows like: {"month": "YYYY-MM", "revenue": N}
        try:
            sorted_rows = sorted(rows, key=lambda r: str(r.get("month", "")))
            latest = sorted_rows[-1]
            prev = sorted_rows[-2]
            if latest.get("month") is None or prev.get("month") is None:
                return ""
            latest_rev = float(latest.get("revenue", 0))
            prev_rev = float(prev.get("revenue", 0))
        except Exception:
            return ""

        delta = latest_rev - prev_rev
        pct = (delta / prev_rev * 100.0) if prev_rev != 0 else 0.0
        direction = "increase" if delta >= 0 else "decrease"
        return (
            f"Month-over-month comparison: {latest.get('month')} vs {prev.get('month')}. "
            f"Revenue {direction} of {delta:.2f} ({pct:.2f}%)."
        )
