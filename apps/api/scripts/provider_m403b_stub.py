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


def _user_variables(body: dict) -> dict:
    messages = body.get("input")
    if not isinstance(messages, list):
        return {}
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        try:
            value = json.loads(content)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}
    return {}


def _research_output(variables: dict) -> dict | None:
    if "planOutputSchema" in variables:
        assets = variables.get("frozenAssetScope", {}).get("assets", [])
        asset_ids = [item["assetId"] for item in assets if isinstance(item, dict) and isinstance(item.get("assetId"), str)]
        return {
            "summary": "Deterministic acceptance research plan.",
            "knownGaps": [],
            "estimatedProviderCalls": 5,
            "subproblems": [{
                "question": str(variables.get("question") or "Inspect the selected evidence."),
                "assetIds": asset_ids,
                "expectedEvidence": ["Deterministic acceptance evidence"],
            }],
        }
    schema = variables.get("resultSchema")
    if not isinstance(schema, dict):
        return None
    if "toolContracts" in variables:
        evidence = variables.get("toolContracts", {}).get("evidence", [])
        handle_ids = [item["evidenceHandle"] for item in evidence if isinstance(item, dict) and isinstance(item.get("evidenceHandle"), str)]
        return {"claims": [{"text": "Deterministic acceptance claim grounded in the loaded evidence.", "evidenceHandleIds": handle_ids[:1]}]}
    claims = variables.get("claims")
    claim_ids = [item["id"] for item in claims if isinstance(item, dict) and isinstance(item.get("id"), str)] if isinstance(claims, list) else []
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return None
    if "conflictClaimIds" in properties:
        return {"conflictClaimIds": []}
    if "factClaimIds" in properties:
        return {"factClaimIds": claim_ids, "unresolvedClaimIds": []}
    if "claims" in properties:
        return {"claims": [{"id": claim_id, "status": "supported"} for claim_id in claim_ids]}
    return None


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
                research_output = _research_output(_user_variables(body))
                output_text = json.dumps(research_output, separators=(",", ":")) if research_output is not None else CAPTION
                self._send_json({"status": "completed", "output_text": output_text})
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
