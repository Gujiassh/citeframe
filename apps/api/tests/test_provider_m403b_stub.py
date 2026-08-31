import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen

SCRIPT = Path(__file__).parents[1] / "scripts" / "provider_m403b_stub.py"
SPEC = spec_from_file_location("provider_m403b_stub", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
stub = module_from_spec(SPEC)
SPEC.loader.exec_module(stub)


def test_accept_stub_returns_completed_planner_contract() -> None:
    variables = {
        "question": "Compare pages.",
        "frozenAssetScope": {"assets": [{"assetId": "asset-1"}]},
        "planOutputSchema": {"type": "object"},
    }
    assert stub._research_output(variables) == {
        "summary": "Deterministic acceptance research plan.",
        "knownGaps": [],
        "estimatedProviderCalls": 5,
        "subproblems": [{
            "question": "Compare pages.",
            "assetIds": ["asset-1"],
            "expectedEvidence": ["Deterministic acceptance evidence"],
        }],
    }


def test_accept_stub_returns_scoped_research_and_terminal_contracts() -> None:
    researcher = stub._research_output({
        "toolContracts": {"evidence": [{"evidenceHandle": "handle-1"}]},
        "resultSchema": {"properties": {"claims": {}}},
    })
    assert researcher == {"claims": [{
        "text": "Deterministic acceptance claim grounded in the loaded evidence.",
        "evidenceHandleIds": ["handle-1"],
    }]}
    assert stub._research_output({
        "claims": [{"id": "claim-1"}],
        "resultSchema": {"properties": {"factClaimIds": {}, "unresolvedClaimIds": {}}},
    }) == {"factClaimIds": ["claim-1"], "unresolvedClaimIds": []}


def test_accept_stub_covers_verifier_and_critic_without_inventing_ids() -> None:
    verifier = stub._research_output({
        "claims": [{"id": "claim-a"}, {"id": 3}, {}],
        "resultSchema": {"properties": {"claims": {}}},
    })
    assert verifier == {"claims": [{"id": "claim-a", "status": "supported"}]}
    critic = stub._research_output({
        "claims": [{"id": "claim-a"}],
        "resultSchema": {"properties": {"conflictClaimIds": {}}},
    })
    assert critic == {"conflictClaimIds": []}
    assert stub._research_output({
        "claims": [],
        "resultSchema": {"properties": {"factClaimIds": {}, "unresolvedClaimIds": {}}},
    }) == {"factClaimIds": [], "unresolvedClaimIds": []}


def test_accept_stub_outputs_only_frozen_asset_and_evidence_ids() -> None:
    planner = stub._research_output({
        "question": "Q",
        "frozenAssetScope": {"assets": [{"assetId": "asset-ok"}, {"assetId": 2}, {}]},
        "planOutputSchema": {},
    })
    assert planner["subproblems"][0]["assetIds"] == ["asset-ok"]
    researcher = stub._research_output({
        "toolContracts": {"evidence": [{"evidenceHandle": "handle-ok"}, {"evidenceHandle": None}, {}]},
        "resultSchema": {"properties": {"claims": {}}},
    })
    assert researcher["claims"][0]["evidenceHandleIds"] == ["handle-ok"]
    empty = stub._research_output({
        "toolContracts": {"evidence": []},
        "resultSchema": {"properties": {"claims": {}}},
    })
    assert empty["claims"][0]["evidenceHandleIds"] == []


def test_accept_stub_http_response_is_completed() -> None:
    server = stub.ThreadingHTTPServer(("127.0.0.1", 0), stub.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = json.dumps({
            "input": [{"role": "user", "content": json.dumps({
                "claims": [{"id": "claim-http"}],
                "resultSchema": {"properties": {"claims": {}}},
            })}],
        }).encode()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/v1/responses",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=2) as response:
            payload = json.load(response)
        assert payload["status"] == "completed"
        assert json.loads(payload["output_text"]) == {
            "claims": [{"id": "claim-http", "status": "supported"}],
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
