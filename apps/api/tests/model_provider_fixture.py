"""Opt-in localhost protocol fixture. Proves plumbing, never model quality.

Run with the Worker environment; no server setting or workspace is modified.
"""
import argparse
import json
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "infra/testing"))
from research_service_worker import FixtureGeneration

HITS = []
LOCK = threading.Lock()


def answer(messages):
    try:
        value = json.loads(messages[-1]["content"])
    except (ValueError, TypeError, KeyError, IndexError):
        return "The uploaded source is available for citation in this workspace. [1]"
    properties = value.get("resultSchema", {}).get("properties", {})
    if "conflictClaimIds" in properties:
        return json.dumps({"conflictClaimIds": []})
    if "factClaimIds" in properties:
        return json.dumps({"factClaimIds": [item["id"] for item in value.get("claims", [])], "unresolvedClaimIds": []})
    return FixtureGeneration().generate(messages, max_output_tokens=8192)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def send_json(self, status, value):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/hits":
            with LOCK:
                hits = list(HITS)
            self.send_json(200, {"hits": hits})
        else:
            self.send_json(200, {"fixture": "issue36-protocol-plumbing-only"})

    def do_POST(self):
        prefix = next((name for name in ("alpha", "beta") if self.path.startswith(f"/{name}/v1/")), None)
        if prefix is None:
            self.send_json(404, {"error": "unknown fixture prefix"})
            return
        expected = f"Bearer fixture-{prefix}-key"
        if self.headers.get("Authorization") != expected:
            self.send_json(401, {"error": "fixture authentication failed"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 2 * 1024 * 1024:
            self.send_json(413, {"error": "fixture request limit"})
            return
        try:
            body = json.loads(self.rfile.read(length))
            endpoint = self.path.rsplit("/", 1)[-1]
            if body.get("model") not in {f"fixture-{prefix}-generation", f"fixture-{prefix}-embedding"}:
                self.send_json(400, {"error": "unexpected fixture model"})
                return
            with LOCK:
                HITS.append({"prefix": prefix, "endpoint": endpoint, "model": body.get("model"), "stream": bool(body.get("stream")), "authorizedFixture": prefix})
                del HITS[:-1000]
            if endpoint == "embeddings":
                self.send_json(200, {"data": [{"index": i, "embedding": [1.0] + [0.0] * 1023} for i, _ in enumerate(body["input"])]})
                return
            chat = endpoint == "completions"
            text = answer(body["messages" if chat else "input"])
            if body.get("stream"):
                events = ([{"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]},
                           {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}] if chat else
                          [{"type": "response.output_text.delta", "delta": text}, {"type": "response.completed", "response": {"status": "completed"}}])
                data = ("".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif chat:
                self.send_json(200, {"choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]})
            else:
                self.send_json(200, {"status": "completed", "output_text": text})
        except Exception as error:
            self.send_json(400, {"error": "fixture request contract failed", "type": type(error).__name__})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18136)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Issue36 protocol fixture listening on 127.0.0.1:{args.port}", flush=True)
    server.serve_forever()
