"""Migrated-PG Research context and accounting oracles; no Worker integration claim."""
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from functools import partial
import re
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from citeframe_contracts.compaction import ContextOwner, CoverageUnit, UsageSettlement
from citeframe_memory.compaction.guards import digest
from citeframe_memory.compaction.journal import NativeAccounting
from test_compaction_call_fixture import FixtureJournal as CallJournal
from citeframe_memory.compaction.policy import CompactionError
from citeframe_memory.compaction.repository import CompactionRepository
from citeframe_memory.compaction.summary import ARRAYS
from citeframe_persistence.models import (
    Asset, AssetRepresentation, EvidenceLocator, HumanDecision, MemoryCall,
    PromptVersion, ResearchArtifact, ResearchBudgetLedger, ResearchEvidenceHandle,
    ResearchEvidenceSnapshot, ResearchExecutionAsset, ResearchExecutionSnapshot,
    ResearchPlanRevision, ResearchPlanRevisionAsset, ResearchRun,
    ResearchStep, ResearchStepAttempt, ResearchToolCall, WorkflowVersion,
)
from citeframe_research_persistence.provider import (
    cancel_provider_reservation, mark_provider_call_sent, reconcile_provider_call, reserve_provider_call,
)
from test_compaction_fixture import pg43, seed_chat

MARKER = "RESEARCH_SEMANTIC_SENTINEL_43"
PROFILE = "f" * 64


@dataclass(frozen=True)
class ResearchFixture:
    owner: ContextOwner
    run_id: str
    step_id: str
    ledger_id: str
    scope: object
    now: datetime
    policy: dict
    handles: tuple[str, ...]
    excerpts: tuple[str, ...]
    asset_id: str | None
    phase: str
    checkpoint_id: str


def add(db, model, **values):
    row = model(**values)
    db.add(row)
    db.flush()
    return row


def make_research(engine, phase="execution", *, excerpt_padding=0):
    scope = seed_chat(engine)
    now = datetime.now(UTC)
    policy = dict(schemaVersion="compaction-policy-v1", maxCalls=20, maxInputTokens=10000,
                  maxOutputTokens=10000, maxSummaryCalls=10, maxEpisodes=4,
                  deadlineAt=(now + timedelta(hours=1)).isoformat())
    with Session(engine) as db, db.begin():
        workflow = add(db, WorkflowVersion, workflow_key="fixture-"+str(uuid4()), version_number=1,
            availability="active", manifest_schema_version="fixture-v1", manifest_json={"marker": MARKER},
            manifest_sha256=digest({"marker": MARKER}), created_by_user_id=scope.user_id, created_at=now)
        prompt = add(db, PromptVersion, prompt_key="fixture-"+str(uuid4()), version_number=1,
            step_kind="planner", availability="active", template_text=MARKER, variables_schema_version="fixture-v1",
            variables_schema_json={}, template_sha256=digest(MARKER), created_by_user_id=scope.user_id, created_at=now)
        run = add(db, ResearchRun, workspace_id=scope.workspace_id, created_by_user_id=scope.user_id,
                  status="planning", state_version=1, next_event_seq=1, cost_currency="USD", created_at=now, updated_at=now)
        frozen = dict(generation_provider="openai", generation_model="gpt-5.5", provider_config_fingerprint=PROFILE,
            pricing_version="research-pricing-v1", data_boundary_policy_version="fixture-boundary-v1",
            embedding_provider="fixture", embedding_model="fixture", embedding_version="fixture-v1",
            retrieval_strategy="hybrid", retrieval_top_k=6, max_parallel_researchers=2, max_step_attempts=3,
            max_provider_calls=20, max_tool_calls=20, max_input_tokens=10000, max_output_tokens=10000,
            max_cost_microunits=10000000, cost_currency="USD", budget_policy_version="fixture-v1",
            retry_policy_version="fixture-v1", max_run_timeout_seconds=3600, max_step_timeout_seconds=600,
            max_provider_timeout_seconds=120)
        plan = add(db, ResearchPlanRevision, workspace_id=scope.workspace_id, run_id=run.id, revision_number=1,
            created_by_user_id=scope.user_id, question_text=MARKER+": compare evidence", scope_mode="selected",
            proposed_workflow_version_id=workflow.id, planner_prompt_version_id=prompt.id,
            **{"proposed_"+key:value for key,value in frozen.items()}, planning_max_provider_calls=20,
            planning_max_input_tokens=10000, planning_max_output_tokens=10000, planning_max_cost_microunits=10000000,
            planning_cost_currency="USD", planning_max_step_attempts=3, planning_budget_policy_version="fixture-v1",
            planning_retry_policy_version="fixture-v1", planning_max_step_timeout_seconds=600,
            planning_max_provider_timeout_seconds=120, planning_snapshot_sha256=digest(frozen), created_at=now)
        run.current_plan_revision_id = plan.id
        planner = add(db, ResearchStep, workspace_id=scope.workspace_id, run_id=run.id, plan_revision_id=plan.id,
            step_key="planner", step_kind="planner", status="running", state_version=1,
            max_attempts_snapshot=3, current_attempt_number=1, input_sha256=digest("planner"), created_at=now, updated_at=now)
        planning_attempt = add(db, ResearchStepAttempt, workspace_id=scope.workspace_id, step_id=planner.id,
            attempt_number=1, status="running", lease_token_hash="a"*64, worker_instance_id="fixture",
            lease_expires_at=now+timedelta(hours=1), heartbeat_at=now, input_sha256=digest("planner"), started_at=now)
        step, attempt = planner, planning_attempt
        snapshot, asset_id, handles, excerpts = None, None, [], []
        if phase == "execution":
            plan_artifact = add(db, ResearchArtifact, workspace_id=scope.workspace_id, run_id=run.id,
                generated_by_step_id=planner.id, generated_by_attempt_id=planning_attempt.id, artifact_kind="research_plan",
                visibility="user", logical_key="plan", schema_version="fixture-v1", object_key="fixture/"+str(uuid4()),
                content_type="application/json", byte_size=1, content_sha256=digest("plan"), workflow_version_id=workflow.id,
                retention_class="workspace_lifetime", created_at=now)
            gate = add(db, ResearchStep, workspace_id=scope.workspace_id, run_id=run.id, plan_revision_id=plan.id,
                step_key="approval", step_kind="plan_approval_gate", status="succeeded", state_version=1,
                max_attempts_snapshot=1, current_attempt_number=0, created_at=now, updated_at=now)
            decision = add(db, HumanDecision, workspace_id=scope.workspace_id, run_id=run.id, gate_step_id=gate.id,
                decision_type="plan_approval", request_number=1, status="submitted", input_artifact_id=plan_artifact.id,
                input_artifact_sha256=plan_artifact.content_sha256, input_snapshot_sha256=plan.planning_snapshot_sha256,
                requested_at=now, decided_by_user_id=scope.user_id, action="approve", decided_at=now)
            snapshot = add(db, ResearchExecutionSnapshot, workspace_id=scope.workspace_id, run_id=run.id,
                approved_plan_revision_id=plan.id, approval_decision_id=decision.id, approved_plan_artifact_id=plan_artifact.id,
                approved_plan_artifact_sha256=plan_artifact.content_sha256, input_version=1,
                question_text=MARKER+": compare evidence", scope_mode="selected", workflow_version_id=workflow.id,
                **frozen, execution_snapshot_sha256=digest(frozen), created_at=now)
            run.status, run.approved_execution_snapshot_id = "running", snapshot.id
            planner.status, planning_attempt.status, planning_attempt.finished_at = "succeeded", "succeeded", now
            step = add(db, ResearchStep, workspace_id=scope.workspace_id, run_id=run.id,
                execution_snapshot_id=snapshot.id, step_key="researcher", step_kind="researcher", branch_key="branch-a",
                status="running", state_version=1, max_attempts_snapshot=3, current_attempt_number=1,
                input_sha256=digest("researcher"), created_at=now, updated_at=now)
            attempt = add(db, ResearchStepAttempt, workspace_id=scope.workspace_id, step_id=step.id,
                attempt_number=1, status="running", lease_token_hash="a"*64, worker_instance_id="fixture",
                lease_expires_at=now+timedelta(hours=1), heartbeat_at=now, input_sha256=digest("researcher"), started_at=now)
            asset = add(db, Asset, workspace_id=scope.workspace_id, created_by_user_id=scope.user_id,
                asset_kind="pdf", title=MARKER, source_filename="fixture.pdf", object_key="fixture/"+str(uuid4()),
                mime_type="application/pdf", byte_size=1, source_sha256=digest("asset"), status="ready")
            asset_id = asset.id
            add(db, ResearchPlanRevisionAsset, plan_revision_id=plan.id, asset_id=asset.id, workspace_id=scope.workspace_id,
                asset_order=0, asset_kind_snapshot="pdf", asset_title_snapshot=MARKER, processing_generation_snapshot=1, index_version_snapshot=1)
            add(db, ResearchExecutionAsset, execution_snapshot_id=snapshot.id, asset_id=asset.id, workspace_id=scope.workspace_id,
                asset_order=0, asset_kind_snapshot="pdf", asset_title_snapshot=MARKER, processing_generation_snapshot=1, index_version_snapshot=1)
            representation = add(db, AssetRepresentation, workspace_id=scope.workspace_id, asset_id=asset.id,
                representation_kind="pdf_page_layout", processing_generation=1, generator_version="fixture-v1")
            tool = add(db, ResearchToolCall, workspace_id=scope.workspace_id, run_id=run.id, execution_snapshot_id=snapshot.id,
                step_id=step.id, attempt_id=attempt.id, tool_call_key="fixture-evidence", call_attempt_number=1, call_order=0,
                tool_name="evidence.search", status="succeeded", request_sha256=digest("tool"), result_count=2, created_at=now,
                started_at=now, finished_at=now)
            for ordinal in range(2):
                locator = add(db, EvidenceLocator, workspace_id=scope.workspace_id, asset_id=asset.id,
                    locator_kind="pdf_page", locator_version=1, processing_generation_snapshot=1,
                    representation_id_snapshot=representation.id)
                excerpt = f"{MARKER}: {37.5 + ordinal} ms; never production; only batch=8." + " x" * excerpt_padding
                evidence = add(db, ResearchEvidenceSnapshot, workspace_id=scope.workspace_id, run_id=run.id,
                    captured_by_step_id=step.id, evidence_locator_id=locator.id, asset_id=asset.id,
                    asset_kind_snapshot="pdf", asset_title_snapshot=MARKER, excerpt_snapshot=excerpt,
                    processing_generation_snapshot=1, representation_id_snapshot=representation.id,
                    parser_version_snapshot="fixture-v1", index_version_snapshot=1, retrieval_channel="hybrid",
                    source_fingerprint_sha256=digest({"locator":locator.id,"excerpt":excerpt}), created_at=now)
                handle = add(db, ResearchEvidenceHandle, workspace_id=scope.workspace_id, run_id=run.id,
                    execution_snapshot_id=snapshot.id, owner_step_id=step.id, created_by_tool_call_id=tool.id,
                    evidence_snapshot_id=evidence.id, result_order=ordinal,
                    handle_fingerprint_sha256=digest({"evidence":evidence.id}), created_at=now)
                handles.append(handle.id); excerpts.append(excerpt)
            attempt.tool_call_count = 1
        checkpoint = add(db, ResearchArtifact, workspace_id=scope.workspace_id, run_id=run.id,
            generated_by_step_id=step.id, generated_by_attempt_id=attempt.id, artifact_kind="execution_checkpoint",
            visibility="internal", logical_key="business-checkpoint", schema_version="fixture-v1",
            object_key="fixture/"+str(uuid4()), content_type="application/json", byte_size=1,
            content_sha256=digest("business-checkpoint"), workflow_version_id=workflow.id,
            retention_class="workspace_lifetime", created_at=now)
        attempt.checkpoint_artifact_id = run.latest_checkpoint_artifact_id = checkpoint.id
        ledger = add(db, ResearchBudgetLedger, workspace_id=scope.workspace_id, run_id=run.id,
            plan_revision_id=plan.id if phase=="planning" else None,
            execution_snapshot_id=snapshot.id if snapshot else None, currency="USD", updated_at=now,
            actual_tool_calls=1 if snapshot else 0)
        owner = ContextOwner(scope.workspace_id, scope.user_id, "research", attempt.id, "a"*64)
        result = ResearchFixture(owner, run.id, step.id, ledger.id, scope, now, policy,
                                 tuple(handles), tuple(excerpts), asset_id, phase, checkpoint.id)
    return result


def services(engine, fixture, *, fault=None):
    repository = CompactionRepository(lambda: Session(engine), clock=lambda: fixture.now, fault=fault)
    callbacks = NativeAccounting(partial(reserve_provider_call,
        provider_config_matcher=lambda db, step, fingerprint: fingerprint == PROFILE),
        mark_provider_call_sent, reconcile_provider_call)
    return repository, CallJournal(repository, native_accounting=callbacks)


def capture_fixture(repository, fixture):
    units = tuple(CoverageUnit("evidence-"+str(i), repository.register_source(fixture.owner,"research_evidence",id_))
                  for i,id_ in enumerate(fixture.handles))
    return repository.capture(fixture.owner, units, fixture.policy)


def reserve(journal, captured, fixture, key="call-1"):
    return journal.reserve(captured, fixture.policy, logical_key=key, purpose="compact_chunk" if captured.units else "main",
        request_sha256=digest(key), input_tokens=90, output_tokens=80, provider="openai", model="gpt-5.5", profile_fingerprint=PROFILE)


def projection(engine, tables):
    with engine.connect() as connection:
        return {table:connection.execute(text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY to_jsonb(t)::text")).scalars().all() for table in tables}


def summary(fixture, units):
    value = {key:[] for key in ARRAYS}
    value.update(conflicts=[], progress={"stepId":fixture.step_id,"stateVersion":1,"status":"running","artifactIds":[fixture.checkpoint_id]})
    value["facts"] = [{"key":"fact-"+str(i),"text":fixture.excerpts[i],"attribution":"sourced_observation",
        "sourceRefs":[asdict(unit.source)],"conditions":["only batch=8"],
        "quantities":[{"value":str(37.5+i),"unit":"ms","qualifier":""}],"negated":True} for i,unit in enumerate(units)]
    return value


def test_two_checkpoints_keep_same_research_attempt_and_frozen_originals(pg43):
    fixture = make_research(pg43)
    repository, _ = services(pg43, fixture)
    captured = capture_fixture(repository, fixture)
    originals = ["research_runs","research_steps","research_step_attempts","research_execution_snapshots",
        "research_plan_revisions","research_execution_assets","research_plan_revision_assets","research_budget_ledgers",
        "research_evidence_handles","research_evidence_snapshots","research_tool_calls","research_artifacts"]
    before = projection(pg43, originals)
    receipts = []
    for count in (1,2):
        receipts.append(repository.adopt(captured, covered_count=count, summary=summary(fixture,captured.units[:count]),
            policy=fixture.policy, operation_key=digest(f"adopt-{count}"), input_sha256=digest(f"input-{count}"),
            before_tokens=1000, after_tokens=400, count_source="exact", provider_fingerprint=PROFILE, counter_version="fixture-v1"))
        captured = repository.capture(fixture.owner, captured.units, fixture.policy)
    assert [r.context_version for r in receipts] == [1,2]
    after = projection(pg43, originals)
    for row in after["research_step_attempts"]:
        if row["id"] == fixture.owner.owner_id:
            assert row["memory_context_version"] == 2 and row["memory_checkpoint_id"] == receipts[-1].snapshot_id
            row["memory_context_version"], row["memory_checkpoint_id"] = 0,None
    assert before == after
    assert tuple(repository.read_source(fixture.owner,unit.source) for unit in captured.units) == fixture.excerpts
    with pg43.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM task_memory_coverage WHERE snapshot_id=:id"), {"id":receipts[-1].snapshot_id}) == 2


@pytest.mark.parametrize("phase", ["planning","execution"])
def test_native_journal_reserve_send_settle_idempotently(pg43, phase):
    fixture = make_research(pg43, phase)
    repository, journal = services(pg43,fixture)
    captured = capture_fixture(repository,fixture)
    receipt = reserve(journal,captured,fixture)
    journal.mark_sent(captured,fixture.policy,receipt)
    usage = UsageSettlement("succeeded",40,30,"reported")
    assert journal.settle(receipt,usage) == dict(state="succeeded",input_tokens=40,output_tokens=30)
    tables=["research_provider_calls","research_budget_ledgers","research_step_attempts","memory_calls"]
    before=projection(pg43,tables)
    assert journal.settle(receipt,usage) == dict(state="succeeded",input_tokens=40,output_tokens=30)
    assert projection(pg43,tables)==before
    with pg43.connect() as connection:
        assert connection.execute(text("SELECT actual_provider_calls,reserved_provider_calls,actual_input_tokens,actual_output_tokens,actual_cost_microunits FROM research_budget_ledgers WHERE id=:id"),{"id":fixture.ledger_id}).one()==(1,0,40,30,550)
        assert connection.execute(text("SELECT provider_call_count,input_tokens,output_tokens,cost_microunits FROM research_step_attempts WHERE id=:id"),{"id":fixture.owner.owner_id}).one()==(1,40,30,550)


def deny_semantic_attribute_access(monkeypatch):
    fields = {
        ResearchRun: {"failure_message"}, ResearchStep: {"error_message"}, ResearchStepAttempt: {"error_message"},
        ResearchPlanRevision: {"question_text"}, ResearchExecutionSnapshot: {"question_text"},
        MemoryCall: {"input_manifest","result_manifest","request_object_key","result_object_key"},
    }
    for model, denied in fields.items():
        original = model.__getattribute__
        def guarded(self, name, original=original, denied=denied):
            if name in denied:
                raise AssertionError("semantic attribute accessed during accounting: " + name)
            return original(self,name)
        monkeypatch.setattr(model,"__getattribute__",guarded)


def audited_settlement(engine, journal, receipt, usage, phase, monkeypatch):
    queries, parameters = [], []
    def record(connection,cursor,statement,params,context,executemany):
        queries.append(statement)
        parameters.append(repr(params))
    with monkeypatch.context() as patch:
        deny_semantic_attribute_access(patch)
        event.listen(engine,"before_cursor_execute",record)
        try:
            result=journal.settle(receipt,usage)
        finally:
            event.remove(engine,"before_cursor_execute",record)
    allowed={"research_provider_calls","research_runs","research_steps","research_step_attempts",
             "research_budget_ledgers","memory_calls",
             "research_plan_revisions" if phase=="planning" else "research_execution_snapshots"}
    observed=set()
    for query in queries:
        observed.update(name for pair in re.findall(r"\b(?:FROM|JOIN|INTO)\s+([a-z_]+)|^\s*UPDATE\s+([a-z_]+)",query,re.IGNORECASE) for name in pair if name)
    assert observed <= allowed, observed - allowed
    assert {"research_provider_calls","research_budget_ledgers","memory_calls"} <= observed
    assert not any(MARKER in value for value in parameters)
    assert type(result) is dict and all(type(value) in (str,int) for value in result.values())
    assert MARKER not in repr(result)
    return result, observed


@pytest.mark.parametrize("phase,boundary", [(p,b) for p in ("planning","execution")
    for b in ("revoke","cancel","expiry","archive")] + [("execution","source_delete")])
def test_accounting_after_authority_loss_has_only_allowed_native_queries(pg43, phase, boundary, monkeypatch):
    from citeframe_research_persistence.cancellation import cancel_research_run_transition
    fixture=make_research(pg43,phase)
    repository,journal=services(pg43,fixture)
    captured=capture_fixture(repository,fixture)
    receipt=reserve(journal,captured,fixture)
    journal.mark_sent(captured,fixture.policy,receipt)
    if boundary=="expiry":
        repository.clock=lambda:fixture.now+timedelta(hours=2)
    elif boundary=="cancel":
        with Session(pg43) as db,db.begin():
            cancel_research_run_transition(db,workspace_id=fixture.owner.workspace_id,actor_user_id=fixture.owner.actor_user_id,
                actor_role="owner",run_id=fixture.run_id,expected_state_version=1,reason_code="user_requested",now=fixture.now)
    else:
        with pg43.begin() as connection:
            if boundary=="revoke":
                connection.execute(text("DELETE FROM workspace_memberships WHERE id=:id"),{"id":fixture.scope.membership_id})
            elif boundary=="archive":
                connection.execute(text("UPDATE workspaces SET archived_at=:now WHERE id=:id"),{"now":fixture.now,"id":fixture.owner.workspace_id})
            else:
                connection.execute(text("UPDATE assets SET deleted_at=:now WHERE id=:id"),{"now":fixture.now,"id":fixture.asset_id})
    with pytest.raises(CompactionError):
        repository.capture(fixture.owner,captured.units,fixture.policy)
    result, observed=audited_settlement(pg43,journal,receipt,UsageSettlement("succeeded",40,30,"reported"),phase,monkeypatch)
    assert result==dict(state="succeeded",input_tokens=40,output_tokens=30)
    assert ("research_plan_revisions" if phase=="planning" else "research_execution_snapshots") in observed
    with pg43.connect() as connection:
        assert connection.execute(text("SELECT provider_call_count,input_tokens,output_tokens FROM research_step_attempts WHERE id=:id"),{"id":fixture.owner.owner_id}).one()==(1,40,30)


@pytest.mark.parametrize("phase",["planning","execution"])
@pytest.mark.parametrize("stage",["native_settlement","sidecar_settlement"])
def test_native_and_sidecar_settlement_fault_rolls_back_together(pg43,phase,stage):
    fixture=make_research(pg43,phase)
    repository,journal=services(pg43,fixture)
    captured=capture_fixture(repository,fixture)
    receipt=reserve(journal,captured,fixture)
    journal.mark_sent(captured,fixture.policy,receipt)
    tables=["research_provider_calls","research_budget_ledgers","research_step_attempts","memory_calls"]
    before=projection(pg43,tables)
    def fail(actual):
        if actual==stage: raise RuntimeError("fault:"+stage)
    repository.fault=fail
    usage=UsageSettlement("succeeded",40,30,"reported")
    with pytest.raises(RuntimeError,match="fault:"+stage):
        journal.settle(receipt,usage)
    assert projection(pg43,tables)==before
    repository.fault=lambda stage:None
    assert journal.settle(receipt,usage)==dict(state="succeeded",input_tokens=40,output_tokens=30)


@pytest.mark.parametrize("phase",["planning","execution"])
@pytest.mark.parametrize("sent",[False,True])
def test_native_reclaim_winner_is_mirrored_without_second_charge(pg43,phase,sent,monkeypatch):
    from citeframe_research_persistence.state import reclaim_expired_research_steps
    fixture=make_research(pg43,phase)
    repository,journal=services(pg43,fixture)
    captured=capture_fixture(repository,fixture)
    receipt=reserve(journal,captured,fixture)
    if sent: journal.mark_sent(captured,fixture.policy,receipt)
    with Session(pg43) as db,db.begin():
        assert reclaim_expired_research_steps(db,now=fixture.now+timedelta(hours=2))==1
    native_tables=["research_provider_calls","research_budget_ledgers","research_step_attempts","research_runs","research_steps","research_events"]
    before=projection(pg43,native_tables)
    def forbidden_reconcile(*args,**kwargs):
        raise AssertionError("reclaim winner must not reconcile twice")
    journal.accounting=replace(journal.accounting,reconcile=forbidden_reconcile)
    usage=UsageSettlement("succeeded",1,1,"reported")
    expected=dict(state="outcome_unknown" if sent else "cancelled",input_tokens=90 if sent else 0,output_tokens=80 if sent else 0)
    result,_=audited_settlement(pg43,journal,receipt,usage,phase,monkeypatch)
    assert result==expected
    assert projection(pg43,native_tables)==before
    assert journal.settle(receipt,usage)==expected
    assert projection(pg43,native_tables)==before


@pytest.mark.parametrize("field",["workspace_id","owner_id","request_sha256","native_ledger_id","native_provider_call_id","call_id"])
def test_forged_accounting_receipt_is_rejected_without_charge(pg43,field):
    fixture=make_research(pg43)
    repository,journal=services(pg43,fixture)
    captured=capture_fixture(repository,fixture)
    receipt=reserve(journal,captured,fixture)
    journal.mark_sent(captured,fixture.policy,receipt)
    tables=["research_provider_calls","research_budget_ledgers","research_step_attempts","memory_calls"]
    before=projection(pg43,tables)
    forged=replace(receipt,**{field:"b"*64 if field=="request_sha256" else str(uuid4())})
    with pytest.raises(CompactionError,match="accounting_receipt_invalid"):
        journal.settle(forged,UsageSettlement("succeeded",40,30,"reported"))
    assert projection(pg43,tables)==before



@pytest.mark.parametrize("phase",["planning","execution"])
def test_mark_sent_native_call_contention_fails_before_ledger_lock(pg43,phase):
    fixture=make_research(pg43,phase)
    repository,journal=services(pg43,fixture)
    captured=capture_fixture(repository,fixture)
    receipt=reserve(journal,captured,fixture)
    queries=[]
    def record(connection,cursor,statement,parameters,context,executemany):
        queries.append(statement)
    with pg43.connect() as blocker:
        blocker.execute(text("SELECT id FROM research_provider_calls WHERE id=:id FOR UPDATE"),{"id":receipt.native_provider_call_id})
        event.listen(pg43,"before_cursor_execute",record)
        try:
            with pytest.raises(CompactionError,match="context_busy"):
                journal.mark_sent(captured,fixture.policy,receipt)
        finally:
            event.remove(pg43,"before_cursor_execute",record)
        assert not any("FROM research_budget_ledgers" in query and "FOR UPDATE" in query for query in queries)
        with pg43.connect() as observer:
            observer.execute(text("SELECT id FROM research_runs WHERE id=:id FOR UPDATE NOWAIT"),{"id":fixture.run_id})
            observer.execute(text("SELECT id FROM research_budget_ledgers WHERE id=:id FOR UPDATE NOWAIT"),{"id":fixture.ledger_id})
            assert observer.scalar(text("SELECT status FROM research_provider_calls WHERE id=:id"),{"id":receipt.native_provider_call_id})=="reserved"
        blocker.rollback()
    journal.mark_sent(captured,fixture.policy,receipt)
    with pg43.connect() as connection:
        assert connection.execute(text("SELECT reserved_provider_calls,actual_provider_calls FROM research_budget_ledgers WHERE id=:id"),{"id":fixture.ledger_id}).one()==(0,1)


@pytest.mark.parametrize("phase",["planning","execution"])
def test_actual_concurrent_settle_and_native_reclaim_charge_once(pg43,phase):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from citeframe_research_persistence.state import reclaim_expired_research_steps
    fixture=make_research(pg43,phase)
    repository,journal=services(pg43,fixture)
    captured=capture_fixture(repository,fixture)
    receipt=reserve(journal,captured,fixture)
    journal.mark_sent(captured,fixture.policy,receipt)
    barrier=Barrier(2)
    usage=UsageSettlement("succeeded",40,30,"reported")
    def settle():
        barrier.wait(timeout=5)
        try:
            return journal.settle(receipt,usage)
        except CompactionError as error:
            assert str(error)=="context_busy"
            return None
    def reclaim():
        barrier.wait(timeout=5)
        with Session(pg43) as db,db.begin():
            return reclaim_expired_research_steps(db,now=fixture.now+timedelta(hours=2))
    with ThreadPoolExecutor(max_workers=2) as pool:
        settling,reclaiming=pool.submit(settle),pool.submit(reclaim)
        settling.result(timeout=10)
        assert reclaiming.result(timeout=10) in (0,1)
    outcome=journal.settle(receipt,usage)
    with pg43.connect() as connection:
        native=connection.execute(text("SELECT status,actual_input_tokens,actual_output_tokens FROM research_provider_calls WHERE id=:id"),{"id":receipt.native_provider_call_id}).one()
        assert native in (("succeeded",40,30),("outcome_unknown",90,80))
        assert outcome==dict(state=native[0],input_tokens=native[1],output_tokens=native[2])
        assert connection.execute(text("SELECT actual_provider_calls,reserved_provider_calls,actual_input_tokens,actual_output_tokens FROM research_budget_ledgers WHERE id=:id"),{"id":fixture.ledger_id}).one()==(1,0,native[1],native[2])
        assert connection.execute(text("SELECT provider_call_count,input_tokens,output_tokens FROM research_step_attempts WHERE id=:id"),{"id":fixture.owner.owner_id}).one()==(1,native[1],native[2])


@pytest.mark.parametrize("phase",["planning","execution"])
def test_known_settlement_rejects_conflicting_repeat_without_mutation(pg43,phase):
    fixture=make_research(pg43,phase)
    repository,journal=services(pg43,fixture)
    captured=capture_fixture(repository,fixture)
    receipt=reserve(journal,captured,fixture)
    journal.mark_sent(captured,fixture.policy,receipt)
    journal.settle(receipt,UsageSettlement("succeeded",40,30,"reported"))
    tables=["research_provider_calls","research_budget_ledgers","research_step_attempts","memory_calls"]
    before=projection(pg43,tables)
    with pytest.raises(CompactionError,match="accounting_receipt_conflict"):
        journal.settle(receipt,UsageSettlement("succeeded",41,30,"reported"))
    assert projection(pg43,tables)==before


def test_two_context_adoptions_do_not_reset_native_or_cumulative_call_budget(pg43):
    fixture=make_research(pg43)
    fixture=replace(fixture,policy={**fixture.policy,"maxInputTokens":100})
    repository,journal=services(pg43,fixture)
    captured=capture_fixture(repository,fixture)
    for count in (1,2):
        repository.adopt(captured,covered_count=count,summary=summary(fixture,captured.units[:count]),
            policy=fixture.policy,operation_key=digest(f"budget-adopt-{count}"),input_sha256=digest(f"budget-input-{count}"),
            before_tokens=1000,after_tokens=400,count_source="exact",provider_fingerprint=PROFILE,counter_version="fixture-v1")
        captured=repository.capture(fixture.owner,captured.units,fixture.policy)
        if count==1:
            receipt=reserve(journal,captured,fixture)
            journal.mark_sent(captured,fixture.policy,receipt)
            journal.settle(receipt,UsageSettlement("succeeded",90,80,"reported"))
    tables=["research_provider_calls","research_budget_ledgers","research_step_attempts","memory_calls"]
    before=projection(pg43,tables)
    with pytest.raises(CompactionError,match="context_budget_exhausted"):
        reserve(journal,captured,fixture,"call-2")
    assert projection(pg43,tables)==before
    with pg43.connect() as connection:
        assert connection.execute(text("SELECT memory_context_version,provider_call_count,input_tokens,output_tokens FROM research_step_attempts WHERE id=:id"),{"id":fixture.owner.owner_id}).one()==(2,1,90,80)
        assert connection.scalar(text("SELECT count(*) FROM research_provider_calls"))==1


@pytest.mark.parametrize("phase",["planning","execution"])
def test_native_unsent_cancel_mirrors_zero_and_cannot_be_sent(pg43,phase):
    fixture=make_research(pg43,phase)
    repository,journal=services(pg43,fixture)
    captured=capture_fixture(repository,fixture)
    receipt=reserve(journal,captured,fixture)
    with Session(pg43) as db,db.begin():
        cancel_provider_reservation(db,receipt.native_provider_call_id,now=fixture.now)
    native_tables=["research_provider_calls","research_budget_ledgers","research_step_attempts"]
    before=projection(pg43,native_tables)
    usage=UsageSettlement("succeeded",1,1,"reported")
    assert journal.settle(receipt,usage)==dict(state="cancelled",input_tokens=0,output_tokens=0)
    assert journal.settle(receipt,usage)==dict(state="cancelled",input_tokens=0,output_tokens=0)
    with pytest.raises(CompactionError,match="call_not_sendable"):
        journal.mark_sent(captured,fixture.policy,receipt)
    assert projection(pg43,native_tables)==before
    with pg43.connect() as connection:
        assert connection.execute(text("SELECT reserved_provider_calls,actual_provider_calls,reserved_input_tokens,reserved_output_tokens,actual_input_tokens,actual_output_tokens FROM research_budget_ledgers WHERE id=:id"),{"id":fixture.ledger_id}).one()==(0,0,0,0,0,0)



