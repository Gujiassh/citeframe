"""Deterministic private provider used by the R800 deployment acceptance harness.

The stub deliberately records only request hashes and bounded execution metadata.
Prompt, Evidence, authorization headers, and response bodies never enter its
timeline or logs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit


VECTOR_DIMENSIONS = 1024
MAX_BODY_BYTES = 2 * 1024 * 1024
CONTROL_PREFIX = "/__r800__/control"
KNOWN_NODES = {
    "planner",
    "researcher",
    "verifier",
    "critic",
    "synthesizer",
    "embedding",
    "unknown",
}
UUID_PATTERN = re.compile(
    r"(?<![0-9a-fA-F])[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}"
    r"-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}(?![0-9a-fA-F])"
)


@dataclass
class Behavior:
    fail_first: int = 0
    delay_ms: int = 0
    barrier: bool = False
    released: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        if not self.barrier:
            self.released.set()


@dataclass(frozen=True)
class RequestTicket:
    epoch: int
    sequence: int
    node: str
    request_sha256: str
    started_at_ns: int
    behavior: Behavior
    should_fail: bool


class ProviderState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._epoch = 0
        self._sequence = 0
        self._active = 0
        self._max_active = 0
        self._node_calls: dict[str, int] = {}
        self._behaviors: dict[str, Behavior] = {}
        self._in_flight: dict[int, dict[str, object]] = {}
        self._entries: list[dict[str, object]] = []

    def reset(self) -> None:
        with self._lock:
            for behavior in self._behaviors.values():
                behavior.released.set()
            self._epoch += 1
            self._sequence = 0
            self._active = 0
            self._max_active = 0
            self._node_calls.clear()
            self._behaviors.clear()
            self._in_flight.clear()
            self._entries.clear()

    def configure(
        self, *, node: str, fail_first: int, delay_ms: int, barrier: bool
    ) -> None:
        if node not in KNOWN_NODES:
            raise ValueError("unknown node")
        if not 0 <= fail_first <= 20:
            raise ValueError("failFirst must be between 0 and 20")
        if not 0 <= delay_ms <= 300_000:
            raise ValueError("delayMs must be between 0 and 300000")
        replacement = Behavior(
            fail_first=fail_first, delay_ms=delay_ms, barrier=barrier
        )
        with self._lock:
            previous = self._behaviors.get(node)
            if previous is not None:
                previous.released.set()
            self._behaviors[node] = replacement
            self._node_calls[node] = 0

    def release(self, node: str) -> None:
        if node not in KNOWN_NODES:
            raise ValueError("unknown node")
        with self._lock:
            behavior = self._behaviors.get(node)
            if behavior is None or not behavior.barrier:
                raise ValueError("node has no configured barrier")
            behavior.released.set()

    def begin(self, *, node: str, request_sha256: str) -> RequestTicket:
        started_at_ns = time.monotonic_ns()
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
            self._active += 1
            self._max_active = max(self._max_active, self._active)
            call_number = self._node_calls.get(node, 0) + 1
            self._node_calls[node] = call_number
            behavior = self._behaviors.get(node) or Behavior()
            entry = {
                "sequence": sequence,
                "node": node,
                "requestSha256": request_sha256,
                "startedAtNs": started_at_ns,
                "activeAtStart": self._active,
                "maxActive": self._max_active,
            }
            self._in_flight[sequence] = entry
            return RequestTicket(
                epoch=self._epoch,
                sequence=sequence,
                node=node,
                request_sha256=request_sha256,
                started_at_ns=started_at_ns,
                behavior=behavior,
                should_fail=call_number <= behavior.fail_first,
            )

    def finish(self, ticket: RequestTicket, *, result: str, http_status: int) -> None:
        finished_at_ns = time.monotonic_ns()
        with self._lock:
            if ticket.epoch != self._epoch:
                return
            entry = self._in_flight.pop(ticket.sequence, None)
            if entry is None:
                return
            self._active = max(0, self._active - 1)
            self._entries.append(
                {
                    **entry,
                    "finishedAtNs": finished_at_ns,
                    "result": result,
                    "httpStatus": http_status,
                }
            )

    def timeline(self) -> dict[str, object]:
        with self._lock:
            return {
                "active": self._active,
                "maxActive": self._max_active,
                "inFlight": [
                    dict(self._in_flight[key]) for key in sorted(self._in_flight)
                ],
                "entries": [dict(entry) for entry in self._entries],
            }


class R800ThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


def create_server(host: str, port: int) -> R800ThreadingHTTPServer:
    state = ProviderState()

    class Handler(R800ProviderHandler):
        provider_state = state

    server = R800ThreadingHTTPServer((host, port), Handler)
    server.provider_state = state  # type: ignore[attr-defined]
    return server


class R800ProviderHandler(BaseHTTPRequestHandler):
    provider_state: ProviderState

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = urlsplit(self.path).path
        if path == "/__r800__/health":
            self._send_json(200, {"status": "ok"})
            return
        if path in {
            f"{CONTROL_PREFIX}/timeline",
            "/__r800__/admin/timeline",
            "/__r800__/timeline",
        }:
            self._send_json(200, self.provider_state.timeline())
            return
        if path == "/api/tags":
            self._send_json(
                200,
                {
                    "models": [
                        {
                            "name": "qwen3-embedding:0.6b",
                            "model": "qwen3-embedding:0.6b",
                            "digest": "r800-deterministic-provider",
                        }
                    ]
                },
            )
            return
        self._send_json(404, {"error": "not_found"})

    def do_PUT(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = urlsplit(self.path).path
        if path in {"/__r800__/admin/reset", "/__r800__/reset"}:
            try:
                body = _decode_json_object(self._read_body())
            except ValueError as error:
                self._send_json(400, {"error": str(error)})
                return
            if body:
                self._send_json(400, {"error": "reset body must be empty"})
                return
            self.provider_state.reset()
            self._send_json(200, {"status": "reset"})
            return
        self._send_json(404, {"error": "not_found"})

    def do_PATCH(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = urlsplit(self.path).path
        try:
            body = _decode_json_object(self._read_body())
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
            return
        if path in {"/__r800__/admin/configure", "/__r800__/configure"}:
            self._configure(body)
            return
        if path in {"/__r800__/admin/release", "/__r800__/release"}:
            self._release(body)
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = urlsplit(self.path).path
        try:
            body_bytes = self._read_body()
            body = _decode_json_object(body_bytes)
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
            return

        if path == f"{CONTROL_PREFIX}/reset":
            if body:
                self._send_json(400, {"error": "reset body must be empty"})
                return
            self.provider_state.reset()
            self._send_json(200, {"status": "reset"})
            return
        if path == f"{CONTROL_PREFIX}/configure":
            self._configure(body)
            return
        if path == f"{CONTROL_PREFIX}/fail-first":
            self._configure_alias(body, field_name="failFirst", value_field="count")
            return
        if path == f"{CONTROL_PREFIX}/delay":
            self._configure_alias(body, field_name="delayMs", value_field="delayMs")
            return
        if path == f"{CONTROL_PREFIX}/barrier":
            self._configure_alias(body, field_name="barrier", value_field="enabled")
            return
        if path == f"{CONTROL_PREFIX}/release":
            self._release(body)
            return
        if path == f"{CONTROL_PREFIX}/barrier/release":
            self._release(body)
            return
        if path == "/api/embed":
            self._provider_request(
                "embedding", body_bytes, body, self._embedding_output
            )
            return
        if path == "/v1/responses":
            node = _detect_node(body)
            self._provider_request(node, body_bytes, body, self._generation_output)
            return
        self._send_json(404, {"error": "not_found"})

    def _configure(self, body: dict[str, object]) -> None:
        try:
            if not set(body).issubset({"node", "failFirst", "delayMs", "barrier"}):
                raise ValueError("configure contains unknown fields")
            node = _required_string(body, "node")
            fail_first = _bounded_int(body.get("failFirst", 0), "failFirst")
            delay_ms = _bounded_int(body.get("delayMs", 0), "delayMs")
            barrier = body.get("barrier", False)
            if not isinstance(barrier, bool):
                raise ValueError("barrier must be boolean")
            self.provider_state.configure(
                node=node,
                fail_first=fail_first,
                delay_ms=delay_ms,
                barrier=barrier,
            )
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
            return
        self._send_json(200, {"status": "configured", "node": node})

    def _release(self, body: dict[str, object]) -> None:
        try:
            if set(body) != {"node"}:
                raise ValueError("release requires only node")
            node = _required_string(body, "node")
            self.provider_state.release(node)
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
            return
        self._send_json(200, {"status": "released", "node": node})

    def _configure_alias(
        self,
        body: dict[str, object],
        *,
        field_name: str,
        value_field: str,
    ) -> None:
        if set(body) != {"node", value_field}:
            self._send_json(
                400, {"error": f"alias requires only node and {value_field}"}
            )
            return
        translated: dict[str, object] = {
            "node": body.get("node"),
            field_name: body.get(value_field),
        }
        self._configure(translated)

    def _provider_request(
        self,
        node: str,
        body_bytes: bytes,
        body: dict[str, object],
        output_builder: Any,
    ) -> None:
        request_sha256 = hashlib.sha256(body_bytes).hexdigest()
        ticket = self.provider_state.begin(node=node, request_sha256=request_sha256)
        result = "internal_error"
        status = 500
        try:
            if ticket.should_fail:
                result = "http_503"
                status = 503
                self._send_json(
                    503,
                    {
                        "error": {
                            "type": "r800_transient",
                            "message": "Synthetic transient failure.",
                        }
                    },
                )
                return
            if not ticket.behavior.released.wait(timeout=300):
                result = "barrier_timeout"
                status = 504
                self._send_json(504, {"error": {"type": "r800_barrier_timeout"}})
                return
            if ticket.behavior.delay_ms:
                time.sleep(ticket.behavior.delay_ms / 1000)
            output = output_builder(body)
            if body.get("stream") is True and node != "embedding":
                status = 200
                result = "succeeded"
                self._send_sse(str(output["output_text"]))
                return
            status = 200
            result = "succeeded"
            self._send_json(200, output)
        except (BrokenPipeError, ConnectionResetError):
            result = "client_disconnected"
            status = 499
        except ValueError as error:
            result = "invalid_request"
            status = 400
            self._send_json(400, {"error": str(error)})
        finally:
            self.provider_state.finish(ticket, result=result, http_status=status)

    @staticmethod
    def _embedding_output(body: dict[str, object]) -> dict[str, object]:
        inputs = body.get("input")
        if isinstance(inputs, str):
            inputs = [inputs]
        if (
            not isinstance(inputs, list)
            or not inputs
            or any(not isinstance(item, str) for item in inputs)
        ):
            raise ValueError("input must be a non-empty string array")
        vector = [1.0, *([0.0] * (VECTOR_DIMENSIONS - 1))]
        return {"embeddings": [list(vector) for _ in inputs]}

    @staticmethod
    def _generation_output(body: dict[str, object]) -> dict[str, object]:
        node = _detect_node(body)
        payload = _last_user_payload(body)
        if node == "planner":
            output = _planner_response(payload)
        elif node == "researcher":
            output = _researcher_response(payload)
        elif node == "verifier":
            output = _verifier_response(payload)
        elif node == "critic":
            output = _critic_response(payload)
        elif node == "synthesizer":
            output = _synthesizer_response(payload)
        else:
            output = {"status": "ok"}
        output_text = json.dumps(
            output, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        return {
            "status": "completed",
            "output_text": output_text,
            "usage": {
                "input_tokens": 64,
                "output_tokens": max(1, (len(output_text) + 3) // 4),
            },
        }

    def _read_body(self) -> bytes:
        raw_length = self.headers.get("content-length", "0")
        if not raw_length.isdecimal():
            raise ValueError("invalid content length")
        length = int(raw_length)
        if length > MAX_BODY_BYTES:
            raise ValueError("request body too large")
        return self.rfile.read(length)

    def _send_json(self, status: int, value: dict[str, object]) -> None:
        payload = json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_sse(self, output_text: str) -> None:
        events = (
            {"type": "response.output_text.delta", "delta": output_text},
            {"type": "response.completed"},
        )
        payload = "".join(
            f"data: {json.dumps(event, separators=(',', ':'))}\n\n" for event in events
        )
        payload += "data: [DONE]\n\n"
        encoded = payload.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _decode_json_object(payload: bytes) -> dict[str, object]:
    if not payload:
        return {}
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError("invalid JSON") from error
    if not isinstance(value, dict):
        raise ValueError("JSON body must be an object")
    return value


def _required_string(body: dict[str, object], field_name: str) -> str:
    value = body.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _bounded_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _message_texts(body: dict[str, object]) -> list[str]:
    messages = body.get("input")
    if not isinstance(messages, list):
        return []
    texts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        texts.append(text)
    return texts


def _detect_node(body: dict[str, object]) -> str:
    text = "\n".join(_message_texts(body)).lower()
    signatures = (
        (
            "planner",
            ("bounded research planner", "estimatedprovidercalls", "subproblems"),
        ),
        ("verifier", ("claim verifier", "preserve every claim id", "reason taxonomy")),
        (
            "critic",
            ("conflict critic", "conflictclaimids", "supported persisted claims"),
        ),
        ("synthesizer", ("synthesis selector", "factclaimids", "unresolvedclaimids")),
        ("researcher", ("evidence researcher", "evidencehandleids", "opaque handles")),
    )
    for node, markers in signatures:
        if any(marker in text for marker in markers):
            return node
    return "unknown"


def _last_user_payload(body: dict[str, object]) -> dict[str, object]:
    messages = body.get("input")
    if not isinstance(messages, list):
        return {}
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            try:
                value = json.loads(content)
            except json.JSONDecodeError:
                return {"text": content}
            return value if isinstance(value, dict) else {"value": value}
    return {}


def _find_values(value: object, key_names: set[str]) -> list[object]:
    found: list[object] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in key_names:
                found.append(item)
            found.extend(_find_values(item, key_names))
    elif isinstance(value, list):
        for item in value:
            found.extend(_find_values(item, key_names))
    return found


def _strings_from_values(values: list[object]) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            result.append(value)
        elif isinstance(value, list):
            result.extend(item for item in value if isinstance(item, str))
    return list(dict.fromkeys(result))


def _planner_response(payload: dict[str, object]) -> dict[str, object]:
    questions = _strings_from_values(_find_values(payload, {"question"}))
    question = questions[0] if questions else "Evaluate the frozen evidence."
    asset_ids = _strings_from_values(_find_values(payload, {"assetIds", "assetId"}))
    subproblems = [
        {
            "question": f"{question} [R800 branch {index}]",
            "assetIds": asset_ids,
            "expectedEvidence": [f"R800 branch {index} evidence"],
        }
        for index in range(1, 4)
    ]
    return {
        "summary": "Evaluate the frozen scope with three bounded parallel branches.",
        "knownGaps": [],
        "estimatedProviderCalls": 8,
        "subproblems": subproblems,
    }


def _researcher_response(payload: dict[str, object]) -> dict[str, object]:
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    questions = _strings_from_values(_find_values(payload, {"question"}))
    question = questions[0] if questions else "R800 evidence finding"
    handles = _strings_from_values(
        _find_values(
            payload, {"evidenceHandle", "evidenceHandleId", "evidenceHandleIds"}
        )
    )
    handles.extend(UUID_PATTERN.findall(serialized))
    handles = list(dict.fromkeys(handles))
    if not handles:
        raise ValueError("researcher request has no Evidence handle")
    claims = [
        {
            "text": f"SUPPORTED {question}",
            "evidenceHandleIds": [handles[0]],
        }
    ]
    if "unsupported" in question.lower():
        claims.append(
            {
                "text": f"UNSUPPORTED synthetic claim for {question}",
                "evidenceHandleIds": [handles[0]],
            }
        )
    return {"claims": claims}


def _claim_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    values = _find_values(payload, {"claims"})
    for value in values:
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return list(value)
    return []


def _verifier_response(payload: dict[str, object]) -> dict[str, object]:
    claims = _claim_rows(payload)
    return {
        "claims": [
            {
                "id": str(claim.get("id", "")),
                "status": (
                    "unsupported"
                    if str(claim.get("text", "")).startswith("UNSUPPORTED ")
                    else "supported"
                ),
            }
            for claim in claims
        ]
    }


def _critic_response(payload: dict[str, object]) -> dict[str, object]:
    claims = _claim_rows(payload)
    conflict_ids = [
        str(claim.get("id"))
        for claim in claims
        if claim.get("status") == "supported"
        and "conflict" in str(claim.get("text", "")).lower()
        and claim.get("id")
    ]
    return {"conflictClaimIds": list(dict.fromkeys(conflict_ids))}


def _synthesizer_response(payload: dict[str, object]) -> dict[str, object]:
    claim_rows = _claim_rows(payload)
    if claim_rows:
        facts: list[str] = []
        unresolved: list[str] = []
        for claim in claim_rows:
            claim_id = claim.get("id")
            if not isinstance(claim_id, str) or not claim_id:
                continue
            if claim.get("conflictStatus") == "resolved_unresolved":
                unresolved.append(claim_id)
            else:
                facts.append(claim_id)
        return {
            "factClaimIds": list(dict.fromkeys(facts)),
            "unresolvedClaimIds": list(dict.fromkeys(unresolved)),
        }

    claim_ids = _strings_from_values(
        _find_values(payload, {"claims", "claimIds", "factClaimIds"})
    )
    unresolved_ids = _strings_from_values(
        _find_values(payload, {"unresolved", "unresolvedClaimIds"})
    )
    unresolved_set = set(unresolved_ids)
    return {
        "factClaimIds": [
            claim_id for claim_id in claim_ids if claim_id not in unresolved_set
        ],
        "unresolvedClaimIds": unresolved_ids,
    }


if __name__ == "__main__":
    host = os.environ.get("R800_PROVIDER_HOST", "0.0.0.0")
    port = int(os.environ.get("R800_PROVIDER_PORT", "18082"))
    create_server(host, port).serve_forever()
