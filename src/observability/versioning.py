"""Versioning – SHA256-based snapshot of all versioned components.

Enables comparing performance metrics across agent versions.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from src.observability.models import VersionSnapshot


def _hash_file(path: Path) -> str:
    """SHA256 hex digest of a file's contents, or 'missing' if absent."""
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _hash_string(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class VersionRegistry:
    """Captures and compares version snapshots of all agent components."""

    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path

    def capture_snapshot(
        self,
        model_name: str = "",
        temperature: float = 0.0,
        agent_version: str = "",
    ) -> VersionSnapshot:
        components: Dict[str, str] = {
            "agent_version": agent_version or self._read_pyproject_version(),
            "model_name": model_name,
            "temperature": str(temperature),
            "prompts": _hash_file(self.base_path / "src" / "llm" / "prompts.py"),
            "workflow": _hash_file(self.base_path / "src" / "graph" / "workflow.py"),
            "guardrails": _hash_file(self.base_path / "src" / "safety" / "guardrails.py"),
            "persona": _hash_file(self.base_path / "config" / "personas" / "default.yaml"),
            "golden_trios": _hash_file(self.base_path / "data" / "golden_trios.json"),
            "pii_masker": _hash_file(self.base_path / "src" / "safety" / "pii_masker.py"),
            "sql_validator": _hash_file(self.base_path / "src" / "tools" / "sql_validator.py"),
            "schema_tool": _hash_file(self.base_path / "src" / "tools" / "schema_tool.py"),
            "golden_retriever": _hash_file(self.base_path / "src" / "tools" / "golden_retriever.py"),
            "report_generator": _hash_file(self.base_path / "src" / "reporting" / "report_generator.py"),
        }

        version_id = _hash_string("".join(sorted(f"{k}={v}" for k, v in components.items())))

        return VersionSnapshot(
            version_id=version_id,
            timestamp=time.time(),
            components=components,
        )

    def _read_pyproject_version(self) -> str:
        pyproject = self.base_path / "pyproject.toml"
        if not pyproject.exists():
            return "unknown"
        try:
            content = pyproject.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.strip().startswith("version"):
                    # version = "0.1.0"
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
        return "unknown"

    @staticmethod
    def compare(snap_a: VersionSnapshot, snap_b: VersionSnapshot) -> Dict[str, Any]:
        """Compare two snapshots, returning changed components."""
        changed: Dict[str, Dict[str, str]] = {}
        all_keys = set(snap_a.components) | set(snap_b.components)
        for key in sorted(all_keys):
            val_a = snap_a.components.get(key, "absent")
            val_b = snap_b.components.get(key, "absent")
            if val_a != val_b:
                changed[key] = {"before": val_a, "after": val_b}
        return {
            "version_a": snap_a.version_id,
            "version_b": snap_b.version_id,
            "changed_components": changed,
            "total_changes": len(changed),
        }

    @staticmethod
    def save_snapshot(snapshot: VersionSnapshot, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version_id": snapshot.version_id,
            "timestamp": snapshot.timestamp,
            "components": snapshot.components,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def load_snapshot(path: Path) -> VersionSnapshot:
        data = json.loads(path.read_text(encoding="utf-8"))
        return VersionSnapshot(
            version_id=data["version_id"],
            timestamp=data["timestamp"],
            components=data["components"],
        )
