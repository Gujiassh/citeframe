"""Opt-in synthetic-fixture wire evidence; never use with real user/provider data.

The original stub and its wire timeline are unchanged. This test-only entry point
records received JSON bytes (no headers) separately for independent hash replay.
"""
import os
import json
import sys
import threading
import time
from urllib.parse import urlsplit

sys.path.insert(0, "/app/apps/api/scripts")
import provider_r800_stub as stub


class ProofState(stub.ProviderState):
    def __init__(self):
        super().__init__()
        self.context = threading.local()
        self.proofs = []

    def begin(self, *, node, request_sha256):
        ticket = super().begin(node=node, request_sha256=request_sha256)
        with self._lock:
            self.proofs.append({"epoch": ticket.epoch, "sequence": ticket.sequence,
                "node": node, "requestSha256": request_sha256,
                "startedAtNs": ticket.started_at_ns, "receivedAtUnixNs": time.time_ns(),
                "rawBody": self.context.raw_body, "path": self.context.path})
        return ticket

    def request_proofs(self):
        with self._lock:
            return {"scope": "synthetic R800 fixture only; received bytes; no headers",
                    "epoch": self._epoch,
                    "entries": [dict(p) for p in self.proofs if p["epoch"] == self._epoch]}


class ProofHandler(stub.R800ProviderHandler):
    @staticmethod
    def _generation_output(body):
        payload = stub._last_user_payload(body)
        if "investigation" in payload:
            from citeframe_research_persistence.conflict_contract import INVESTIGATOR_SCHEMA
            assert payload["resultSchema"] == INVESTIGATOR_SCHEMA, "unknown_investigator_contract"
            result = {
                "inspections": [{"evidenceHandleId": e["id"], "quote": e["excerpt"],
                    "version": None, "environment": None, "time": None, "conditions": None}
                    for e in payload["investigation"]["evidence"]],
                "revisions": [], "nextQuery": None,
                "gaps": ["The fixture evidence does not establish a source-backed correction."],
                "reason": "Inspected the original source; conflict remains unresolved.",
            }
            output_text = json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            return {"status": "completed", "output_text": output_text,
                    "usage": {"input_tokens": 64, "output_tokens": max(1, (len(output_text) + 3) // 4)}}
        output = stub.R800ProviderHandler._generation_output(body)
        if stub._detect_node(body) == "researcher":
            payload = stub._last_user_payload(body)
            schema = payload["resultSchema"]
            required = schema["required"]
            assert required in (["claims"], ["claims", "nextQuery"]), "unknown_researcher_contract"
            if required == ["claims", "nextQuery"]:
                result = json.loads(output["output_text"])
                result["nextQuery"] = None
                output["output_text"] = json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                output["usage"]["output_tokens"] = max(1, (len(output["output_text"]) + 3) // 4)
        return output

    def _provider_request(self, node, body_bytes, body, output_builder):
        if "investigation" in stub._last_user_payload(body):
            node = "investigator"
        self.provider_state.context.raw_body = body_bytes.decode("utf-8")
        self.provider_state.context.path = urlsplit(self.path).path
        try:
            return super()._provider_request(node, body_bytes, body, output_builder)
        finally:
            del self.provider_state.context.raw_body
            del self.provider_state.context.path

    def do_GET(self):
        if urlsplit(self.path).path == "/__r800__/request-proofs":
            self._send_json(200, self.provider_state.request_proofs())
        else:
            super().do_GET()


def create_server(host, port):
    class Handler(ProofHandler):
        provider_state = ProofState()
    return stub.R800ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    create_server(os.environ.get("R800_PROVIDER_HOST", "127.0.0.1"),
                  int(os.environ.get("R800_PROVIDER_PORT", "18082"))).serve_forever()
