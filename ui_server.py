from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from src.ui.runtime import AppRuntime


BASE_DIR = Path(__file__).parent
UI_FILE = BASE_DIR / "ui.html"
DEFAULT_USER = "manager_a"


RUNTIME = AppRuntime()


class UiHandler(BaseHTTPRequestHandler):
    server_version = "RetailUiServer/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _json_response(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/ui.html"}:
            html = UI_FILE.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        if self.path == "/health":
            self._json_response({"ok": True, "connected": True})
            return

        self._json_response({"ok": False, "error": "not_found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path == "/api/message":
                body = self._read_json()
                question = str(body.get("question", "")).strip()
                user_id = str(body.get("user_id", DEFAULT_USER)).strip() or DEFAULT_USER
                if not question:
                    self._json_response({"ok": False, "error": "Question is required."}, status=400)
                    return
                result = RUNTIME.handle_question(question=question, user_id=user_id)
                self._json_response({"ok": True, "result": result})
                return

            if self.path == "/api/run-batch":
                body = self._read_json()
                prompts = body.get("prompts", [])
                user_id = str(body.get("user_id", DEFAULT_USER)).strip() or DEFAULT_USER
                if not isinstance(prompts, list) or not prompts:
                    self._json_response({"ok": False, "error": "prompts list is required."}, status=400)
                    return
                outputs: list[dict[str, Any]] = []
                for raw in prompts:
                    question = str(raw).strip()
                    if not question:
                        continue
                    outputs.append(
                        {
                            "question": question,
                            "result": RUNTIME.handle_question(question=question, user_id=user_id),
                        }
                    )
                self._json_response({"ok": True, "count": len(outputs), "outputs": outputs})
                return

            if self.path == "/api/run-tests":
                result = AppRuntime.run_command([str(BASE_DIR / ".venv" / "bin" / "python"), "run_tests.py"])
                self._json_response({"ok": True, "result": result})
                return

            if self.path == "/api/run-qa-gate":
                result = AppRuntime.run_command([str(BASE_DIR / ".venv" / "bin" / "python"), "-m", "src.evaluation.qa_gate"])
                self._json_response({"ok": True, "result": result})
                return

            self._json_response({"ok": False, "error": "not_found"}, status=404)
        except Exception as exc:  # pragma: no cover - runtime safety fallback
            self._json_response({"ok": False, "error": str(exc)}, status=500)


def main() -> None:
    port = int(os.getenv("UI_SERVER_PORT", "8787"))
    host = os.getenv("UI_SERVER_HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, port), UiHandler)
    print(f"UI server running at http://{host}:{port}")
    print("Use Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
