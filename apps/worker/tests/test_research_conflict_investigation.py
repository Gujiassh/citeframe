from copy import deepcopy
from types import SimpleNamespace as N
import json
import pytest
from citeframe_contracts import EvidenceHandle, VerifiedClaim, ResearchExecutionError
from ai_pdf_worker.research_conflict_investigation import investigate


def evidence(id="h1", text="Version 1 Linux: use A. Version 2 Windows: use B."):
    return EvidenceHandle(
        id,
        "w",
        "r",
        "snapshot",
        "researcher",
        "branch",
        "asset",
        1,
        1,
        "representation",
        "parser",
        "locator",
        "pdf_page",
        text,
        "a" * 64,
        "tool",
    )


class Checkpoint:
    def __init__(self):
        self.rows = {}

    def __call__(self, lease, number, phase, request, result=None):
        canonical = lambda v: json.loads(json.dumps(v))
        old = self.rows.get(number)
        if old:
            assert old["phase"] == phase and old["request"] == canonical(request)
            if old["result"] is not None:
                if result is not None:
                    assert old["result"] == canonical(result)
                return {"status": "succeeded", "result": deepcopy(old["result"])}
            if result is None:
                return {"status": "outcome_unknown", "result": None}
            old["result"] = canonical(result)
            return {"status": "succeeded", "result": canonical(result)}
        self.rows[number] = {
            "phase": phase,
            "request": canonical(request),
            "result": None,
        }
        return {"status": "reserved", "result": None}


class Agents:
    def __init__(self, *, query=None, revision=True, conflict=False, unsupported=False):
        self.query = query
        self.revision = revision
        self.conflict = conflict
        self.unsupported = unsupported
        self.calls = []

    def investigator(self, payload, lease):
        self.calls.append("inspect")
        return {
            "inspections": [
                {
                    "evidenceHandleId": e["id"],
                    "quote": e["excerpt"],
                    "version": None,
                    "environment": None,
                    "time": None,
                    "conditions": None,
                }
                for e in payload["evidence"]
            ],
            "revisions": [
                {
                    "originalClaimIds": ["c1", "c2"],
                    "text": "Version 1 Linux uses A; Version 2 Windows uses B.",
                    "evidenceHandleIds": [e["id"] for e in payload["evidence"]],
                }
            ]
            if self.revision
            else [],
            "gaps": [],
            "reason": "Source version and environment were compared.",
            "nextQuery": self.query,
        }

    def verifier(self, claims, evidence, lease):
        self.calls.append("verify")
        return [
            VerifiedClaim(
                c.id,
                c.text,
                c.evidence_handle_ids,
                "unsupported" if self.unsupported else "supported",
            )
            for c in claims
        ]

    def critic(self, claims, lease):
        self.calls.append("critic")
        return [claims[-1].id] if self.conflict else []


class Tools:
    def __init__(self, values=()):
        self.values = values
        self.queries = []

    def search(self, **kwargs):
        assert kwargs["asset_ids"] == ["asset"] and kwargs["top_k"] == 4
        self.queries.append(kwargs["query"])
        return self.values

    def load(self, **kwargs):
        return []


def run(agents, checkpoint=None, tools=None):
    e = evidence()
    c1 = VerifiedClaim("c1", "Use A", ("h1",), "supported", "conflicted")
    c2 = VerifiedClaim("c2", "Use B", ("h1",), "supported", "conflicted")
    return investigate(
        execution=N(frozen_assets=[N(asset_id="asset")], retrieval_top_k=4),
        state={
            "conflicts": ["c1", "c2"],
            "verified_claims": [c1, c2],
            "branch_results": [N(evidence=[e])],
        },
        agents=agents,
        lease=N(step_id="gate"),
        tools=lambda _: tools or Tools(),
        checkpoint=checkpoint or Checkpoint(),
    )


def test_source_backed_revision_requires_verifier_and_critic_and_preserves_originals():
    agents = Agents()
    checkpoint = Checkpoint()
    out = run(agents, checkpoint)
    assert out["resolved"] and agents.calls == ["inspect", "verify", "critic"]
    assert out["originalClaims"][0]["text"] == "Use A"
    assert out["revisions"][0]["originalClaimIds"] == ["c1", "c2"]
    assert [r["phase"] for r in checkpoint.rows.values()] == [
        "inspect",
        "verify",
        "critic",
        "finish",
    ]
    # Reconstruct the worker and checkpoint from serialized durable contents.
    replay = Checkpoint()
    replay.rows = {
        int(k): v for k, v in json.loads(json.dumps(checkpoint.rows)).items()
    }
    agents2 = Agents()
    assert run(agents2, replay) == out and not agents2.calls


@pytest.mark.parametrize(
    "agents,reason",
    [
        (Agents(conflict=True), "persistent_contradiction"),
        (Agents(unsupported=True), "revision_unsupported"),
        (Agents(revision=False), "insufficient_evidence"),
    ],
)
def test_unverified_or_conflicting_revisions_are_not_published(agents, reason):
    out = run(agents)
    assert (
        not out["resolved"]
        and out["reason"] == reason
        and out["gaps"]
        and not out["revisions"]
    )


def test_no_new_content_stops_even_when_locator_handle_changes():
    tools = Tools([evidence("new-id")])
    agents = Agents(revision=False, query="check version")
    out = run(agents, tools=tools)
    assert out["reason"] == "no_new_evidence" and agents.calls == ["inspect"]


def test_new_evidence_is_retained_and_then_verified():
    class NewEvidence(Agents):
        def investigator(self, payload, lease):
            self.revision = len(payload["evidence"]) > 1
            return super().investigator(payload, lease)

    tools = Tools([evidence("new", "Version 2 Windows requires B.")])
    out = run(NewEvidence(query="version 2"), tools=tools)
    assert (
        out["resolved"]
        and len(out["evidence"]) == 2
        and out["queries"] == ["version 2"]
    )


def test_duplicate_query_stops_before_second_search():
    tools = Tools([evidence("new", "New passage")])
    out = run(Agents(revision=False, query="  SAME query "), tools=tools)
    assert out["reason"] == "duplicate_query" and len(tools.queries) == 1


def test_budget_exhaustion_is_unresolved():
    class Budget(Agents):
        def investigator(self, *args):
            raise ResearchExecutionError("research_budget_limit")

    out = run(Budget())
    assert not out["resolved"] and out["reason"] == "budget_exhausted"


def test_crash_before_external_acknowledgement_does_not_dispatch_again():
    checkpoint = Checkpoint()

    class Crash(Agents):
        def investigator(self, *args):
            raise RuntimeError("crash")

    with pytest.raises(RuntimeError):
        run(Crash(), checkpoint)
    agents = Agents()
    out = run(agents, checkpoint)
    assert out["reason"] == "operation_outcome_unknown" and not agents.calls


def test_model_cannot_invent_a_source_condition():
    class Invented(Agents):
        def investigator(self, *args):
            result = super().investigator(*args)
            result["inspections"][0]["version"] = "version 99"
            return result

    with pytest.raises(ValueError, match="invented_condition"):
        run(Invented())


def test_provider_error_never_becomes_success():
    class Failure(Agents):
        def verifier(self, *args):
            raise RuntimeError("provider failed")

    with pytest.raises(RuntimeError):
        run(Failure())
