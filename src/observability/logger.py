from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "event"):
            payload["event"] = record.event
        if hasattr(record, "context"):
            payload.update(record.context)

        # PII / secret sanitization hook – applied transparently
        from src.observability.security import get_security_observer

        sec = get_security_observer()
        if sec is not None:
            payload = sec.sanitize_log_payload(payload)

        return json.dumps(payload, default=str)


def setup_logging(debug: bool = False) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG if debug else logging.WARNING)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # Keep CLI debug readable: show app debug/info without third-party transport noise.
    noisy_loggers = [
        "google",
        "google.auth",
        "google_genai",
        "urllib3",
        "httpcore",
        "httpx",
    ]
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, event: str, **context: Any) -> None:
    logger.info(event, extra={"event": event, "context": context})
