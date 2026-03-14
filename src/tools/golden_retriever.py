from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


TOKEN_REGEX = re.compile(r"[a-zA-Z0-9_]+")


@dataclass
class GoldenRetriever:
    source_file: Path

    def __post_init__(self) -> None:
        self.examples = self._load_examples()

    def _load_examples(self) -> List[Dict[str, Any]]:
        if not self.source_file.exists():
            return []
        with self.source_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def retrieve(self, question: str, top_k: int = 3) -> List[Dict[str, Any]]:
        question_tokens = set(self._tokens(question))
        scored: List[tuple[int, Dict[str, Any]]] = []

        for example in self.examples:
            haystack = " ".join(
                [example.get("question", ""), " ".join(example.get("tags", []))]
            )
            overlap = len(question_tokens.intersection(set(self._tokens(haystack))))
            scored.append((overlap, example))

        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, item in scored[:top_k]:
            enriched = dict(item)
            enriched["score"] = score
            results.append(enriched)
        return results

    @staticmethod
    def _tokens(text: str) -> List[str]:
        return [token.lower() for token in TOKEN_REGEX.findall(text)]
