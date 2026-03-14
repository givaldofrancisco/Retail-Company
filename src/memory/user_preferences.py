from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


@dataclass
class UserPreferenceStore:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def get(self, user_id: str) -> Dict[str, str]:
        data = self._load()
        return data.get(user_id, {"format": "bullets"})

    def set_format(self, user_id: str, format_name: str) -> None:
        data = self._load()
        data.setdefault(user_id, {})["format"] = format_name
        self._save(data)

    def _load(self) -> Dict[str, Dict[str, str]]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, payload: Dict[str, Dict[str, str]]) -> None:
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
