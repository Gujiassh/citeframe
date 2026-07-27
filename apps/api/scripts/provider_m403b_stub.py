"""Deterministic local provider for M403B plumbing acceptance.

This endpoint is intentionally limited to synthetic local acceptance traffic. It
does not represent model quality or a production provider response.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VECTOR = [1.0] + [0.0] * 1023
CAPTION = "Synthetic production image caption for M403B acceptance."
ANSWER = "The uploaded image is available as frozen Evidence from the production Image path."


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/api/tags":
            self._send_json(
                {
                    "models": [
                        {
                            "name": "qwen3-embedding:0.6b",
                            "model": "qwen3-embedding:0.6b",
                            "digest": "m403b-deterministic-acceptance",
                        }
                    ]
                }
            )
            return
        self.send_error(404)

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_error(400)
            return

        if self.path == "/api/embed":
            inputs = body.get("input")
            if not isinstance(inputs, list) or not inputs:
                self.send_error(400)
                return
            self._send_json({"embeddings": [VECTOR[:] for _ in inputs]})
            return

        if self.path == "/v1/responses":
            if body.get("stream") is True:
                self._send_stream()
            else:
                self._send_json({"output_text": CAPTION})
            return

        self.send_error(404)

    def _send_json(self, value: dict) -> None:
        payload = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_stream(self) -> None:
        events = [
            {"type": "response.output_text.delta", "delta": ANSWER},
            {"type": "response.completed"},
        ]
        payload = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
        encoded = payload.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        print(f"provider_m403b_stub {format % args}", flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("M403B_PROVIDER_PORT", "18081"))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
