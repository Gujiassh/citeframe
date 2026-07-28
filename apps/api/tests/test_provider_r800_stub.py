from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import time
from collections.abc import Generator

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from provider_r800_stub import create_server


@pytest.fixture()
def provider_stub() -> Generator[str, None, None]:
    server = create_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _response_request(
    system: str, user: dict[str, object], *, stream: bool = False
) -> dict[str, object]:
    return {
        "model": "gpt-5.5",
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, sort_keys=True)},
        ],
        "max_output_tokens": 1200,
        "stream": stream,
    }


def _timeline(client: httpx.Client) -> dict[str, object]:
    response = client.get("/__r800__/control/timeline")
    assert response.status_code == 200
    return response.json()


def test_ollama_and_openai_compatibility(provider_stub: str) -> None:
    handle_id = "123e4567-e89b-42d3-a456-426614174000"
    with httpx.Client(base_url=provider_stub, timeout=2) as client:
        tags = client.get("/api/tags")
        assert tags.status_code == 200
        assert tags.json()["models"][0]["model"] == "qwen3-embedding:0.6b"

        embeddings = client.post(
            "/api/embed",
            json={"model": "qwen3-embedding:0.6b", "input": ["one", "two"]},
        )
        assert embeddings.status_code == 200
        assert len(embeddings.json()["embeddings"]) == 2
        assert all(len(vector) == 1024 for vector in embeddings.json()["embeddings"])

        planner = client.post(
            "/v1/responses",
            json=_response_request(
                "You are Citeframe's bounded research planner. Return subproblems and estimatedProviderCalls.",
                {"question": "Compare", "assetIds": ["asset-1"]},
            ),
        )
        plan = json.loads(planner.json()["output_text"])
        assert planner.status_code == 200
        assert len(plan["subproblems"]) == 3
        assert all(item["assetIds"] == ["asset-1"] for item in plan["subproblems"])

        researcher = client.post(
            "/v1/responses",
            json=_response_request(
                "You are a Citeframe evidence researcher. Return evidenceHandleIds.",
                {
                    "question": "Unsupported comparison",
                    "evidence": f"[{handle_id}] bounded excerpt",
                },
            ),
        )
        claims = json.loads(researcher.json()["output_text"])["claims"]
        assert researcher.status_code == 200
        assert len(claims) == 2
        assert all(claim["evidenceHandleIds"] == [handle_id] for claim in claims)

        verification = client.post(
            "/v1/responses",
            json=_response_request(
                "You are Citeframe's claim verifier. Preserve every claim id.",
                {
                    "claims": [
                        {
                            "id": "claim-1",
                            "text": "SUPPORTED Compare unsupported conflict evidence.",
                        },
                        {
                            "id": "claim-2",
                            "text": "UNSUPPORTED synthetic claim for unsupported conflict evidence.",
                        },
                    ]
                },
            ),
        )
        assert json.loads(verification.json()["output_text"])["claims"] == [
            {"id": "claim-1", "status": "supported"},
            {"id": "claim-2", "status": "unsupported"},
        ]

        stream = client.post(
            "/v1/responses",
            json=_response_request(
                "You are Citeframe's conflict critic. Return conflictClaimIds.",
                {
                    "claims": [
                        {
                            "id": "claim-1",
                            "text": "SUPPORTED Compare unsupported conflict evidence.",
                            "status": "supported",
                        },
                        {
                            "id": "claim-2",
                            "text": "UNSUPPORTED synthetic conflict claim.",
                            "status": "unsupported",
                        },
                    ]
                },
                stream=True,
            ),
        )
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        assert "response.output_text.delta" in stream.text
        assert "claim-1" in stream.text
        assert "claim-2" not in stream.text

        synthesis = client.post(
            "/v1/responses",
            json=_response_request(
                "You are Citeframe's bounded synthesis selector. Return factClaimIds and unresolvedClaimIds.",
                {
                    "question": "Synthesize",
                    "claims": [
                        {
                            "id": "claim-fact",
                            "text": "Supported fact",
                            "verificationStatus": "supported",
                            "conflictStatus": "none",
                        },
                        {
                            "id": "claim-unresolved",
                            "text": "Retained conflict",
                            "verificationStatus": "supported",
                            "conflictStatus": "resolved_unresolved",
                        },
                    ],
                },
            ),
        )
        assert json.loads(synthesis.json()["output_text"]) == {
            "factClaimIds": ["claim-fact"],
            "unresolvedClaimIds": ["claim-unresolved"],
        }


def test_fail_first_and_timeline_never_store_sensitive_content(
    provider_stub: str,
) -> None:
    secret = "secret-prompt-evidence-api-key-material"
    request = _response_request(
        "You are Citeframe's bounded research planner. Return subproblems.",
        {"question": secret, "assetIds": ["asset-1"]},
    )
    with httpx.Client(base_url=provider_stub, timeout=2) as client:
        configured = client.post(
            "/__r800__/control/configure",
            json={"node": "planner", "failFirst": 1, "delayMs": 0, "barrier": False},
        )
        assert configured.status_code == 200
        assert (
            client.post(
                "/__r800__/control/configure",
                json={"node": "planner", "prompt": secret},
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/__r800__/control/reset",
                json={"secret": secret},
            ).status_code
            == 400
        )

        first = client.post(
            "/v1/responses", json=request, headers={"Authorization": f"Bearer {secret}"}
        )
        second = client.post(
            "/v1/responses", json=request, headers={"Authorization": f"Bearer {secret}"}
        )
        assert first.status_code == 503
        assert second.status_code == 200

        timeline = _timeline(client)
        assert timeline["active"] == 0
        assert [entry["result"] for entry in timeline["entries"]] == [
            "http_503",
            "succeeded",
        ]
        assert all(len(entry["requestSha256"]) == 64 for entry in timeline["entries"])
        assert secret not in json.dumps(timeline, sort_keys=True)
        assert set(timeline["entries"][0]) == {
            "sequence",
            "node",
            "requestSha256",
            "startedAtNs",
            "finishedAtNs",
            "activeAtStart",
            "maxActive",
            "result",
            "httpStatus",
        }

        reset = client.post("/__r800__/control/reset", json={})
        assert reset.status_code == 200
        assert _timeline(client) == {
            "active": 0,
            "maxActive": 0,
            "inFlight": [],
            "entries": [],
        }


def test_private_admin_aliases_support_harness_control(provider_stub: str) -> None:
    request = _response_request(
        "You are Citeframe's bounded research planner. Return subproblems.",
        {"question": "Admin alias", "assetIds": ["asset-1"]},
    )
    with httpx.Client(base_url=provider_stub, timeout=2) as client:
        assert (
            client.patch(
                "/__r800__/admin/configure",
                json={"node": "planner", "failFirst": 1},
            ).status_code
            == 200
        )
        assert client.post("/v1/responses", json=request).status_code == 503
        assert client.put("/__r800__/admin/reset", json={}).status_code == 200
        assert (
            client.post(
                "/__r800__/control/fail-first",
                json={"node": "planner", "count": 1},
            ).status_code
            == 200
        )
        assert client.post("/v1/responses", json=request).status_code == 503
        assert (
            client.post(
                "/__r800__/control/delay",
                json={"node": "planner", "delayMs": 1},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/__r800__/control/barrier",
                json={"node": "planner", "enabled": False},
            ).status_code
            == 200
        )
        assert client.get("/__r800__/admin/timeline").status_code == 200
        assert client.put("/__r800__/admin/reset", json={}).status_code == 200
        assert _timeline(client)["entries"] == []


def test_patch_configure_and_release_preserve_the_single_request_body(
    provider_stub: str,
) -> None:
    request = _response_request(
        "You are Citeframe's bounded research planner. Return subproblems.",
        {"question": "PATCH barrier", "assetIds": ["asset-1"]},
    )
    results: list[int] = []
    with httpx.Client(base_url=provider_stub, timeout=3) as client:
        configured = client.patch(
            "/__r800__/admin/configure",
            json={"node": "planner", "barrier": True},
        )
        assert configured.status_code == 200

        def send() -> None:
            with httpx.Client(base_url=provider_stub, timeout=3) as thread_client:
                results.append(
                    thread_client.post("/v1/responses", json=request).status_code
                )

        thread = threading.Thread(target=send)
        thread.start()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not _timeline(client)["inFlight"]:
            time.sleep(0.01)
        assert _timeline(client)["inFlight"]

        released = client.patch(
            "/__r800__/admin/release",
            json={"node": "planner"},
        )
        assert released.status_code == 200
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert results == [200]


def test_barrier_delay_release_and_concurrency_timeline(provider_stub: str) -> None:
    handle_id = "123e4567-e89b-42d3-a456-426614174000"
    request = _response_request(
        "You are a Citeframe evidence researcher. Return evidenceHandleIds.",
        {"question": "Parallel evidence", "evidence": f"[{handle_id}] excerpt"},
    )
    results: list[int] = []

    with httpx.Client(base_url=provider_stub, timeout=3) as client:
        configured = client.post(
            "/__r800__/control/configure",
            json={"node": "researcher", "failFirst": 0, "delayMs": 30, "barrier": True},
        )
        assert configured.status_code == 200

        def send() -> None:
            with httpx.Client(base_url=provider_stub, timeout=3) as thread_client:
                results.append(
                    thread_client.post("/v1/responses", json=request).status_code
                )

        threads = [threading.Thread(target=send) for _ in range(2)]
        for thread in threads:
            thread.start()

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            timeline = _timeline(client)
            if len(timeline["inFlight"]) == 2:
                break
            time.sleep(0.01)
        else:
            pytest.fail("provider requests did not reach the barrier")

        assert timeline["active"] == 2
        assert timeline["maxActive"] == 2
        assert all(
            set(entry)
            == {
                "sequence",
                "node",
                "requestSha256",
                "startedAtNs",
                "activeAtStart",
                "maxActive",
            }
            for entry in timeline["inFlight"]
        )

        released_at = time.monotonic_ns()
        released = client.post("/__r800__/control/release", json={"node": "researcher"})
        assert released.status_code == 200
        for thread in threads:
            thread.join(timeout=2)
            assert not thread.is_alive()

        timeline = _timeline(client)
        assert sorted(results) == [200, 200]
        assert timeline["active"] == 0
        assert timeline["maxActive"] == 2
        assert len(timeline["entries"]) == 2
        assert all(entry["result"] == "succeeded" for entry in timeline["entries"])
        assert all(entry["finishedAtNs"] > released_at for entry in timeline["entries"])
        assert all(
            entry["finishedAtNs"] - released_at >= 20_000_000
            for entry in timeline["entries"]
        )


def test_reset_releases_blocked_request_without_leaking_old_epoch(
    provider_stub: str,
) -> None:
    handle_id = "123e4567-e89b-42d3-a456-426614174000"
    request = _response_request(
        "You are a Citeframe evidence researcher. Return evidenceHandleIds.",
        {"question": "Reset barrier", "evidence": f"[{handle_id}] excerpt"},
    )
    completed = threading.Event()

    with httpx.Client(base_url=provider_stub, timeout=3) as client:
        assert (
            client.post(
                "/__r800__/control/configure",
                json={"node": "researcher", "barrier": True},
            ).status_code
            == 200
        )

        def send() -> None:
            with httpx.Client(base_url=provider_stub, timeout=3) as thread_client:
                thread_client.post("/v1/responses", json=request)
            completed.set()

        thread = threading.Thread(target=send)
        thread.start()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not _timeline(client)["inFlight"]:
            time.sleep(0.01)
        assert _timeline(client)["inFlight"]

        assert client.post("/__r800__/control/reset", json={}).status_code == 200
        assert completed.wait(timeout=2)
        thread.join(timeout=2)
        assert _timeline(client) == {
            "active": 0,
            "maxActive": 0,
            "inFlight": [],
            "entries": [],
        }
