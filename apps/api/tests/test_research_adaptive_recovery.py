"""Retry actual ledgered search/load and model checkpoints with fresh registries/attempts.

Provider and retrieval outputs are deterministic injected doubles; no external calls.
"""
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace as N
from uuid import uuid4
import sys
import pytest
from sqlalchemy import select, func, delete
from ai_pdf_api.models import (AssetRepresentation, EvidenceLocator, ContentUnit, PdfLocatorDetail,
    ResearchExecutionAsset, ResearchToolCall, WorkspaceMembership, ResearchProviderCall)
from citeframe_persistence.models import ResearchAdaptiveTurn
from ai_pdf_api.services.research import research_worker_evidence as service
from ai_pdf_api.services.retrieval import RetrievedContent
from ai_pdf_api.services.research.research_worker import fail_research_step, claim_specific_research_step
from citeframe_research_persistence.adaptive_turns import adaptive_turn
from citeframe_research_persistence.provider import reserve_provider_call, mark_provider_call_sent, reconcile_provider_call
from citeframe_research_persistence.errors import ResearchError, canonical_sha256
from research_worker_test_support import lease_default_step, sha256
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker" / "src"))
from ai_pdf_worker.research_adaptive_retrieval import research_adaptively
from ai_pdf_worker.research_executor_tools import EvidenceToolRegistry
from ai_pdf_worker.research_runtime_core import _evidence_handle, _loaded_evidence
from citeframe_contracts import ToolExecutionContext, FrozenAsset


@pytest.fixture
def adaptive_case(research_worker_db, monkeypatch):
    f = research_worker_db; db = f.db
    f.snapshot.agent_result_schema_version = "research-agent-results-v2"
    f.snapshot.max_tool_calls = 10
    f.snapshot.max_provider_calls = 8
    rep = AssetRepresentation(id=str(uuid4()), workspace_id=f.run.workspace_id, asset_id=f.asset.id,
        representation_kind='pdf_page_layout', processing_generation=f.asset.current_processing_generation,
        generator_provider='parser', generator_model='parser', generator_version='v1',
        object_key='test-representation', content_sha256=sha256('rep'), created_at=f.now)
    loc = EvidenceLocator(id=str(uuid4()), workspace_id=f.run.workspace_id, asset_id=f.asset.id,
        locator_kind='pdf_page', locator_version=1, processing_generation_snapshot=f.asset.current_processing_generation,
        representation_id_snapshot=rep.id, created_at=f.now)
    unit = ContentUnit(id=str(uuid4()), workspace_id=f.run.workspace_id, asset_id=f.asset.id,
        representation_id=rep.id, source_locator_id=loc.id, unit_kind='pdf_text', unit_order=0,
        text_content='The missing date is 2026.', token_count=8,
        index_version=f.asset.current_index_version, created_at=f.now)
    db.add_all([rep, loc, unit, PdfLocatorDetail(locator_id=loc.id, page_number=1),
        ResearchExecutionAsset(execution_snapshot_id=f.snapshot.id, workspace_id=f.run.workspace_id,
            asset_id=f.asset.id, asset_order=0, asset_kind_snapshot='pdf', asset_title_snapshot='source',
            processing_generation_snapshot=f.asset.current_processing_generation,
            index_version_snapshot=f.asset.current_index_version)])
    db.commit()
    state = N(f=f, db=db, lease=lease_default_step(f), tick=1, queries=[], models=[],
              fault=None, fired=False, alternate="supplement A")
    class Embedding:
        provider=f.snapshot.embedding_provider; model=f.snapshot.embedding_model; version=f.snapshot.embedding_version
        def embed_query(self, query): return [0.25, 0.75]
    def retrieve(session, workspace, query, vector, **kw):
        state.queries.append(query)
        if state.fault == "tool" and query == "supplement A" and not state.fired:
            state.fired = True
            raise TimeoutError("injected tool failure")
        return [] if query == "initial" else [RetrievedContent(content_unit=unit, asset=f.asset,
            locator=loc, channel="text", distance=0.1, location_key=(f.asset.id, "pdf_page:1"))]
    monkeypatch.setattr(service, "retrieve_query_content", retrieve)
    def now(): return f.now + timedelta(seconds=state.tick)
    class Port:
        def restore_handles(self, ctx):
            return tuple(_evidence_handle(row) for row in service.restore_frozen_evidence(db,
                run_id=ctx.run_id, execution_snapshot_id=ctx.execution_snapshot_id, owner_step_id=ctx.step_id))
        def search(self, ctx, **kwargs):
            rows = service.search_frozen_evidence(db, run_id=ctx.run_id, execution_snapshot_id=ctx.execution_snapshot_id,
                step_id=ctx.step_id, attempt_id=ctx.attempt_id, branch_key=ctx.branch_key,
                embedding_provider=Embedding(), now=now(), **kwargs)
            db.commit()
            if state.fault == "search" and kwargs["query"] == "supplement A" and not state.fired:
                state.fired=True
                raise TimeoutError("after search commit")
            return tuple(_evidence_handle(row) for row in rows)
        def load(self, ctx, *, tool_call_key, handle_ids):
            rows = service.load_frozen_evidence(db, run_id=ctx.run_id, execution_snapshot_id=ctx.execution_snapshot_id,
                step_id=ctx.step_id, attempt_id=ctx.attempt_id, branch_key=ctx.branch_key,
                tool_call_key=tool_call_key, evidence_handle_ids=handle_ids, now=now())
            db.commit()
            return tuple(_loaded_evidence(row) for row in rows)
    def checkpoint(lease, turn, request, result=None):
        if result is not None and state.fault == "before_save" and not state.fired:
            state.fired=True
            raise TimeoutError("after model before checkpoint")
        value=adaptive_turn(db, attempt_id=lease.attempt_id, lease_token=lease.lease_token,
            turn_number=turn, request=request, result=result, now=now())
        db.commit()
        if result is not None and state.fault == "after_save" and not state.fired:
            state.fired=True
            raise TimeoutError("after checkpoint commit")
        return value
    def model(lease, role, request):
        reservation=reserve_provider_call(db, attempt_id=lease.attempt_id,
            logical_call_key="adaptive:"+request["toolContracts"]["retrievalQuery"], request_sha256=canonical_sha256(request),
            provider=f.snapshot.generation_provider, model=f.snapshot.generation_model,
            provider_config_fingerprint=f.snapshot.provider_config_fingerprint,
            reserved_input_tokens=10, reserved_output_tokens=10, now=now(), provider_config_matcher=lambda *a: True)
        mark_provider_call_sent(db, reservation.provider_call_id, now=now())
        state.models.append(request["toolContracts"]["retrievalQuery"])
        failure = state.fault == "provider" and len(state.models) == 2 and not state.fired
        reconcile_provider_call(db, provider_call_id=reservation.provider_call_id,
            status="failed" if failure else "succeeded", actual_input_tokens=10, actual_output_tokens=10,
            usage_source="actual", usage_final=True, now=now())
        db.commit()
        if failure:
            state.fired=True
            raise TimeoutError("provider timeout")
        handles=request["toolContracts"]["evidence"]
        return {"claims": [{"text": "fact", "evidenceHandleIds": [handles[0]["evidenceHandle"]]}] if handles else [],
                "nextQuery": None if handles else state.alternate}
    def execute():
        ctx=ToolExecutionContext(f.run.workspace_id, f.run.id, f.snapshot.id, f.snapshot.execution_snapshot_sha256,
            f.step.id, state.lease.attempt_id, f.step.branch_key,
            (FrozenAsset(f.asset.id, f.asset.current_processing_generation, f.asset.current_index_version),))
        return research_adaptively(N(question="initial", asset_ids=(f.asset.id,), branch_key=f.step.branch_key),
            EvidenceToolRegistry(Port(), ctx), state.lease, top_k=f.snapshot.retrieval_top_k,
            result_schema={}, generate_json=model, checkpoint=checkpoint)
    def retry():
        # Session/registry/attempt-local state must not be needed to choose the same query.
        db.rollback()
        state.tick += 2
        outcome=fail_research_step(db, attempt_id=state.lease.attempt_id, lease_token=state.lease.lease_token,
            error_code="provider_timeout", now=now())
        assert outcome.auto_requeued
        db.commit(); state.tick += 1
        state.lease=claim_specific_research_step(db, run_id=f.run.id, step_key=f.step.step_key,
            branch_key=f.step.branch_key, worker_instance_id="retry", lease_seconds=300, now=now())
        db.commit()
        assert state.lease is not None
        state.alternate="supplement B"
    state.execute=execute; state.retry=retry; state.checkpoint=checkpoint
    return state


@pytest.mark.parametrize("fault", ["search", "after_save", "before_save", "provider", "tool"])
def test_retry_resumes_durable_query_and_reuses_successful_tool_ledger(adaptive_case, fault):
    c=adaptive_case; c.fault=fault
    with pytest.raises(Exception): c.execute()
    assert c.fired
    c.retry(); answer=c.execute()
    expected="supplement B" if fault == "before_save" else "supplement A"
    assert c.queries == ["initial", expected] + ([expected] if fault == "tool" else [])
    assert len(answer.claims) == len(answer.evidence) == 1
    checkpoints=list(c.db.scalars(select(ResearchAdaptiveTurn).order_by(ResearchAdaptiveTurn.turn_number)))
    assert [t.query for t in checkpoints] == ["initial", expected]
    successes=list(c.db.scalars(select(ResearchToolCall).where(ResearchToolCall.status == "succeeded")))
    assert len(successes) == 3
    assert len({call.tool_call_key for call in successes}) == 3
    c.db.refresh(c.f.ledger)
    assert c.f.ledger.reserved_tool_calls == c.f.ledger.reserved_provider_calls == 0
    assert c.f.ledger.actual_provider_calls == len(c.models)
    assert c.f.ledger.actual_tool_calls == (4 if fault == "tool" else 3)
    previous_ids=[row.id for row in successes]
    # Replay the completed loop after another real attempt, without generating new claims or billing.
    c.retry(); repeated=c.execute()
    assert repeated == answer
    assert list(c.db.scalars(select(ResearchToolCall.id).where(ResearchToolCall.status == "succeeded"))) == previous_ids
    assert c.db.scalar(select(func.count()).select_from(ResearchProviderCall)) == len(c.models)


@pytest.mark.parametrize("stop", ["cancel", "revoke", "tool_budget", "provider_budget"])
def test_resume_obeys_current_permissions_and_run_budgets(adaptive_case, stop):
    c=adaptive_case; c.fault="after_save"
    with pytest.raises(TimeoutError): c.execute()
    c.retry()
    if stop == "cancel":
        c.f.run.status="cancel_requested"; c.f.run.cancel_requested_at=c.f.now
        c.f.run.cancel_requested_by_user_id=c.f.run.created_by_user_id; c.f.run.cancel_reason_code="user_requested"
    elif stop == "revoke":
        c.db.execute(delete(WorkspaceMembership).where(WorkspaceMembership.user_id == c.f.run.created_by_user_id))
    elif stop == "tool_budget": c.f.snapshot.max_tool_calls=1
    else: c.f.snapshot.max_provider_calls=1
    c.db.commit()
    with pytest.raises(ResearchError): c.execute()
    assert c.models == ["initial"]
    if stop != "provider_budget": assert c.queries == ["initial"]
    assert c.db.scalar(select(func.count()).select_from(ResearchAdaptiveTurn)) == 1


def test_checkpoint_refuses_changed_request_and_out_of_bound_turn(adaptive_case):
    c=adaptive_case; c.execute()
    with pytest.raises(ResearchError, match="changed"):
        c.checkpoint(c.lease, 0, {"toolContracts": {"retrievalQuery": "different"}})
    with pytest.raises(ResearchError, match="scope"):
        c.checkpoint(c.lease, 3, {"toolContracts": {"retrievalQuery": "initial"}})


def test_production_checkpoint_adapter_commits_and_reopens(adaptive_case, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from ai_pdf_worker.research_runtime_ports import LedgeredGeneration
    from ai_pdf_worker.research_persistence_service import build_worker_research_service
    import ai_pdf_worker.research_runtime_ports as ports
    c=adaptive_case
    monkeypatch.setattr(ports, "_now", lambda: c.f.now+timedelta(seconds=c.tick))
    factory=sessionmaker(bind=c.db.get_bind(), expire_on_commit=False)
    def adapter():
        return LedgeredGeneration(factory, build_worker_research_service(), N(), provider=N(provider="test", model="test"))
    request={"toolContracts": {"retrievalQuery": "initial"}}
    result={"claims": [], "nextQuery": "supplement A"}
    assert adapter().adaptive_turn(c.lease, 0, request) is None
    assert adapter().adaptive_turn(c.lease, 0, request, result) == result
    c.retry()
    assert adapter().adaptive_turn(c.lease, 0, request) == result
    with pytest.raises(ResearchError, match="changed"):
        adapter().adaptive_turn(c.lease, 0, request, {"claims": [], "nextQuery": "supplement B"})
    assert adapter().adaptive_turn(c.lease, 0, request) == result
