from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from research_worker_test_support import (
    BranchClaimValue,
    BranchResultValue,
    add_step,
    assert_research_error,
    lease_default_step,
    seed_frozen_evidence,
    sha256,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ai_pdf_api.models import (
    ResearchBudgetLedger,
    ResearchClaim,
    ResearchClaimEvidence,
    ResearchEvent,
    ResearchProviderCall,
    ResearchRun,
    ResearchStep,
    ResearchStepAttempt,
    ResearchToolCall,
    WorkspaceMembership,
)
from ai_pdf_api.services import research_worker_provider, research_worker_tools
from ai_pdf_api.services.research_idempotency import ResearchError
from ai_pdf_api.services.research_worker import (
    VerificationResult,
    begin_tool_call,
    cancel_provider_reservation,
    claim_specific_research_step,
    complete_research_branch,
    complete_research_critique,
    complete_research_synthesis,
    complete_research_verification,
    complete_tool_call,
    fail_research_step,
    heartbeat_research_step,
    load_completed_branch,
    mark_provider_call_sent,
    reclaim_expired_research_steps,
    reconcile_provider_call,
    reserve_provider_call,
    restore_frozen_evidence,
)
from ai_pdf_api.services.research_worker_lease import (
    _active_attempt_chain,
    _locked_attempt,
    _locked_attempt_chain,
)
from ai_pdf_api.services.research_worker_policy import (
    is_transient_failure,
    normalize_failure_code,
)


@pytest.mark.parametrize(
    ("error_code", "max_attempts", "expected_run_status", "expected_step_status", "expected_event_types"),
    [
        ("generation_provider_unreachable", 3, "running", "queued", ["step_failed", "step_queued"]),
        ("generation_provider_unreachable", 1, "awaiting_retry", "failed", ["step_failed"]),
        ("generation_invalid_response", 3, "failed", "failed", ["step_failed", "run_failed"]),
    ],
)
def test_fail_step_persists_failure_status_and_events(
    research_worker_db,
    error_code: str,
    max_attempts: int,
    expected_run_status: str,
    expected_step_status: str,
    expected_event_types: list[str],
) -> None:
    fixture = research_worker_db
    fixture.step.max_attempts_snapshot = max_attempts
    fixture.db.commit()
    lease = lease_default_step(fixture)
    failed_at = fixture.now + timedelta(seconds=1)

    disposition = fail_research_step(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        error_code=error_code,
        now=failed_at,
    )

    fixture.db.expire_all()
    run = fixture.db.get(ResearchRun, fixture.run.id)
    step = fixture.db.get(ResearchStep, fixture.step.id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert run is not None and run.status == expected_run_status
    assert (run.finished_at is not None) is (expected_run_status == "failed")
    assert step is not None and step.status == expected_step_status
    assert attempt is not None and attempt.status == "failed"
    assert disposition.run_status == expected_run_status
    assert disposition.step_status == expected_step_status
    assert disposition.auto_requeued is (expected_step_status == "queued")
    events = list(
        fixture.db.scalars(
            select(ResearchEvent)
            .where(
                ResearchEvent.run_id == fixture.run.id,
                ResearchEvent.event_type.in_(("step_failed", "step_queued", "run_failed")),
            )
            .order_by(ResearchEvent.seq)
        ).all()
    )
    assert [event.event_type for event in events] == expected_event_types
    assert events[0].payload_json["retryable"] is (error_code == "generation_provider_unreachable")


def test_provider_reserve_send_and_reconcile_preserve_budget_accounting(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    reserved_at = fixture.now + timedelta(seconds=1)
    reservation = reserve_provider_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        logical_call_key="verify-generation",
        request_sha256=sha256("provider-request"),
        provider="openai",
        model="gpt-5.5",
        provider_config_fingerprint=fixture.snapshot.provider_config_fingerprint,
        reserved_input_tokens=300,
        reserved_output_tokens=200,
        now=reserved_at,
    )

    fixture.db.refresh(fixture.ledger)
    provider_call = fixture.db.get(ResearchProviderCall, reservation.provider_call_id)
    assert provider_call is not None and provider_call.status == "reserved"
    assert provider_call.usage_source == "reserved"
    assert provider_call.usage_final is False
    assert fixture.ledger.reserved_provider_calls == 1
    assert fixture.ledger.actual_provider_calls == 0
    assert fixture.ledger.reserved_input_tokens == 300
    assert fixture.ledger.reserved_output_tokens == 200
    assert fixture.ledger.reserved_cost_microunits == 3_750

    mark_provider_call_sent(fixture.db, reservation.provider_call_id, now=reserved_at + timedelta(seconds=1))
    fixture.db.refresh(fixture.ledger)
    fixture.db.refresh(provider_call)
    assert provider_call.status == "sent"
    assert fixture.ledger.reserved_provider_calls == 0
    assert fixture.ledger.actual_provider_calls == 1
    assert fixture.ledger.reserved_input_tokens == 300
    assert fixture.ledger.reserved_output_tokens == 200
    assert fixture.ledger.reserved_cost_microunits == 3_750

    reconcile_provider_call(
        fixture.db,
        provider_call_id=provider_call.id,
        status="succeeded",
        actual_input_tokens=250,
        actual_output_tokens=175,
        usage_source="actual",
        usage_final=True,
        provider_response_id_hash=sha256("provider-response-id"),
        now=reserved_at + timedelta(seconds=2),
    )

    fixture.db.refresh(fixture.ledger)
    fixture.db.refresh(provider_call)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert provider_call.status == "succeeded"
    assert fixture.ledger.reserved_input_tokens == 0
    assert fixture.ledger.reserved_output_tokens == 0
    assert fixture.ledger.reserved_cost_microunits == 0
    assert fixture.ledger.actual_provider_calls == 1
    assert fixture.ledger.actual_input_tokens == 250
    assert fixture.ledger.actual_output_tokens == 175
    assert fixture.ledger.actual_cost_microunits == 3_250
    assert fixture.ledger.usage_final is True
    assert attempt is not None
    assert attempt.provider_call_count == 1
    assert attempt.input_tokens == 250
    assert attempt.output_tokens == 175
    assert attempt.cost_microunits == 3_250

    reserve_provider_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        logical_call_key="verify-generation-2",
        request_sha256=sha256("provider-request-2"),
        provider="openai",
        model="gpt-5.5",
        provider_config_fingerprint=fixture.snapshot.provider_config_fingerprint,
        reserved_input_tokens=140,
        reserved_output_tokens=426,
        now=reserved_at + timedelta(seconds=3),
    )
    with pytest.raises(ResearchError) as budget_error:
        reserve_provider_call(
            fixture.db,
            attempt_id=lease.attempt_id,
            logical_call_key="verify-generation-3",
            request_sha256=sha256("provider-request-3"),
            provider="openai",
            model="gpt-5.5",
            provider_config_fingerprint=fixture.snapshot.provider_config_fingerprint,
            reserved_input_tokens=1,
            reserved_output_tokens=1,
            now=reserved_at + timedelta(seconds=4),
        )
    assert_research_error(budget_error, "research_budget_limit", 429)


@pytest.mark.parametrize(
    ("provider", "model", "fingerprint"),
    [
        ("other-provider", "gpt-5.5", sha256("provider-config")),
        ("openai", "other-model", sha256("provider-config")),
        ("openai", "gpt-5.5", sha256("other-provider-config")),
    ],
)
def test_provider_reservation_rejects_values_outside_frozen_execution_profile(
    research_worker_db,
    provider: str,
    model: str,
    fingerprint: str,
) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)

    with pytest.raises(ResearchError):
        reserve_provider_call(
            fixture.db,
            attempt_id=lease.attempt_id,
            logical_call_key="profile-mismatch",
            request_sha256=sha256("provider-request"),
            provider=provider,
            model=model,
            provider_config_fingerprint=fingerprint,
            reserved_input_tokens=100,
            reserved_output_tokens=100,
            now=fixture.now + timedelta(seconds=1),
        )
    fixture.db.rollback()
    fixture.db.refresh(fixture.ledger)
    assert fixture.ledger.reserved_provider_calls == 0
    assert fixture.ledger.reserved_input_tokens == 0
    assert fixture.db.scalar(select(ResearchProviderCall)) is None


def test_provider_outcome_unknown_marks_call_and_ledger_usage_non_final(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    reservation = reserve_provider_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        logical_call_key="unknown-outcome",
        request_sha256=sha256("provider-request"),
        provider=fixture.snapshot.generation_provider,
        model=fixture.snapshot.generation_model,
        provider_config_fingerprint=fixture.snapshot.provider_config_fingerprint,
        reserved_input_tokens=120,
        reserved_output_tokens=80,
        now=fixture.now + timedelta(seconds=1),
    )
    mark_provider_call_sent(
        fixture.db,
        reservation.provider_call_id,
        now=fixture.now + timedelta(seconds=2),
    )

    reconcile_provider_call(
        fixture.db,
        provider_call_id=reservation.provider_call_id,
        status="outcome_unknown",
        actual_input_tokens=120,
        actual_output_tokens=80,
        usage_source="estimated",
        usage_final=False,
        error_code="provider_outcome_unknown",
        now=fixture.now + timedelta(seconds=3),
    )

    fixture.db.expire_all()
    call = fixture.db.get(ResearchProviderCall, reservation.provider_call_id)
    ledger = fixture.db.get(ResearchBudgetLedger, fixture.ledger.id)
    assert call is not None and call.status == "outcome_unknown"
    assert call.usage_source == "estimated"
    assert call.usage_final is False
    assert ledger is not None and ledger.usage_final is False
    assert ledger.reserved_provider_calls == 0
    assert ledger.reserved_input_tokens == 0
    assert ledger.reserved_output_tokens == 0
    assert ledger.reserved_cost_microunits == 0


def test_tool_begin_and_complete_preserve_budget_and_attempt_accounting(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    first = begin_tool_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        tool_call_key="search-1",
        tool_name="evidence.search",
        request_sha256=sha256("search-request"),
        now=fixture.now + timedelta(seconds=1),
    )

    fixture.db.refresh(fixture.ledger)
    first_call = fixture.db.get(ResearchToolCall, first.tool_call_id)
    assert first_call is not None and first_call.status == "running"
    assert first_call.call_attempt_number == 1
    assert first_call.call_order == 0
    assert fixture.ledger.reserved_tool_calls == 1
    assert fixture.ledger.actual_tool_calls == 0

    complete_tool_call(
        fixture.db,
        tool_call_id=first.tool_call_id,
        status="succeeded",
        complete=lambda _db, _call: 3,
        now=fixture.now + timedelta(seconds=2),
    )
    fixture.db.refresh(fixture.ledger)
    fixture.db.refresh(first_call)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert first_call.status == "succeeded"
    assert first_call.result_count == 3
    assert fixture.ledger.reserved_tool_calls == 0
    assert fixture.ledger.actual_tool_calls == 1
    assert attempt is not None and attempt.tool_call_count == 1

    second = begin_tool_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        tool_call_key="load-1",
        tool_name="evidence.load",
        request_sha256=sha256("load-request"),
        now=fixture.now + timedelta(seconds=3),
    )
    second_call = fixture.db.get(ResearchToolCall, second.tool_call_id)
    assert second_call is not None and second_call.call_order == 1
    complete_tool_call(
        fixture.db,
        tool_call_id=second.tool_call_id,
        status="failed",
        error_code="tool_temporarily_unavailable",
        error_message="Tool failed.",
        now=fixture.now + timedelta(seconds=4),
    )
    fixture.db.refresh(fixture.ledger)
    fixture.db.refresh(attempt)
    assert fixture.ledger.reserved_tool_calls == 0
    assert fixture.ledger.actual_tool_calls == 2
    assert attempt.tool_call_count == 2

    with pytest.raises(ResearchError) as budget_error:
        begin_tool_call(
            fixture.db,
            attempt_id=lease.attempt_id,
            tool_call_key="search-over-budget",
            tool_name="evidence.search",
            request_sha256=sha256("over-budget-request"),
            now=fixture.now + timedelta(seconds=5),
        )
    assert_research_error(budget_error, "research_budget_limit", 429)


def test_branch_verification_critique_and_synthesis_ports_preserve_opaque_handles(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    handle = seed_frozen_evidence(fixture, lease.attempt_id)
    claim_id = str(uuid4())
    stored: dict[str, bytes] = {}
    result = BranchResultValue(
        branch_key=fixture.step.branch_key or "",
        claims=(BranchClaimValue(claim_id, "Supported branch claim.", (handle.id,)),),
    )

    complete_research_branch(
        fixture.db,
        attempt_id=lease.attempt_id,
        lease_token=lease.lease_token,
        result=result,
        output_sha256=sha256("branch-output"),
        store_bytes=lambda key, content, _content_type: stored.__setitem__(key, content),
        now=fixture.now + timedelta(seconds=1),
    )

    claim = fixture.db.get(ResearchClaim, claim_id)
    relation = fixture.db.scalar(
        select(ResearchClaimEvidence).where(ResearchClaimEvidence.claim_id == claim_id)
    )
    restored_branch = load_completed_branch(fixture.db, fixture.run.id, fixture.step.branch_key or "")
    restored_evidence = restore_frozen_evidence(
        fixture.db,
        run_id=fixture.run.id,
        execution_snapshot_id=fixture.snapshot.id,
        owner_step_id=fixture.step.id,
    )
    assert claim is not None and claim.verification_status == "pending"
    assert relation is not None and relation.evidence_snapshot_id == handle.evidence_snapshot_id
    assert restored_branch is not None
    assert restored_branch["claims"] == [
        {"id": claim_id, "text": "Supported branch claim.", "evidenceHandleIds": [handle.id]}
    ]
    assert [item.evidence_handle for item in restored_evidence] == [handle.id]

    verifier = add_step(fixture, step_key="verifier", step_kind="verifier")
    verifier_lease = claim_specific_research_step(
        fixture.db,
        run_id=fixture.run.id,
        step_key=verifier.step_key,
        branch_key=None,
        worker_instance_id="worker-verifier",
        now=fixture.now + timedelta(seconds=2),
    )
    complete_research_verification(
        fixture.db,
        attempt_id=verifier_lease.attempt_id,
        lease_token=verifier_lease.lease_token,
        results=(VerificationResult(claim_id, "supported"),),
        now=fixture.now + timedelta(seconds=3),
    )
    fixture.db.refresh(claim)
    assert claim.verification_status == "supported"
    assert claim.verified_by_step_id == verifier.id

    critic = add_step(fixture, step_key="critic", step_kind="critic")
    critic_lease = claim_specific_research_step(
        fixture.db,
        run_id=fixture.run.id,
        step_key=critic.step_key,
        branch_key=None,
        worker_instance_id="worker-critic",
        now=fixture.now + timedelta(seconds=4),
    )
    complete_research_critique(
        fixture.db,
        attempt_id=critic_lease.attempt_id,
        lease_token=critic_lease.lease_token,
        conflict_claim_ids=(),
        now=fixture.now + timedelta(seconds=5),
    )

    synthesizer = add_step(fixture, step_key="synthesizer", step_kind="synthesizer")
    synthesizer_lease = claim_specific_research_step(
        fixture.db,
        run_id=fixture.run.id,
        step_key=synthesizer.step_key,
        branch_key=None,
        worker_instance_id="worker-synthesizer",
        now=fixture.now + timedelta(seconds=6),
    )
    complete_research_synthesis(
        fixture.db,
        attempt_id=synthesizer_lease.attempt_id,
        lease_token=synthesizer_lease.lease_token,
        fact_claim_ids=(claim_id,),
        unresolved_claim_ids=(),
        store_bytes=lambda key, content, _content_type: stored.__setitem__(key, content),
        now=fixture.now + timedelta(seconds=7),
    )
    fixture.db.refresh(synthesizer)
    assert synthesizer.status == "succeeded"
    assert len(stored) == 2


def test_branch_rejects_noncanonical_claim_uuid_and_verifier_rejects_partial_claim_set(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    handle = seed_frozen_evidence(fixture, lease.attempt_id)
    for invalid_claim_id in ("MODEL-CLAIM-ID", str(uuid4()).upper()):
        invalid = BranchResultValue(
            branch_key=fixture.step.branch_key or "",
            claims=(BranchClaimValue(invalid_claim_id, "Unsafe id.", (handle.id,)),),
        )
        with pytest.raises(ResearchError) as invalid_id:
            complete_research_branch(
                fixture.db,
                attempt_id=lease.attempt_id,
                lease_token=lease.lease_token,
                result=invalid,
                output_sha256=sha256("invalid-branch"),
                store_bytes=lambda *_args: None,
                now=fixture.now + timedelta(seconds=1),
            )
        assert_research_error(invalid_id, "research_state_conflict", 409)

    pending = ResearchClaim(
        id=str(uuid4()),
        workspace_id=fixture.run.workspace_id,
        run_id=fixture.run.id,
        claim_key="uncovered-pending-claim",
        claim_order=0,
        statement_text="Pending claim.",
        statement_sha256=sha256("Pending claim."),
        produced_by_step_id=fixture.step.id,
        verification_status="pending",
        conflict_status="none",
        created_at=fixture.now,
    )
    fixture.db.add(pending)
    fixture.db.commit()
    verifier = add_step(fixture, step_key="verifier", step_kind="verifier")
    verifier_lease = claim_specific_research_step(
        fixture.db,
        run_id=fixture.run.id,
        step_key=verifier.step_key,
        branch_key=None,
        worker_instance_id="worker-verifier",
        now=fixture.now + timedelta(seconds=2),
    )
    with pytest.raises(ResearchError) as partial:
        complete_research_verification(
            fixture.db,
            attempt_id=verifier_lease.attempt_id,
            lease_token=verifier_lease.lease_token,
            results=(),
            now=fixture.now + timedelta(seconds=3),
        )
    assert_research_error(partial, "research_state_conflict", 409)
    fixture.db.rollback()
    fixture.db.refresh(verifier)
    assert verifier.status == "running"


def test_provider_reservation_cancel_and_expired_lease_reclaim(research_worker_db) -> None:
    fixture = research_worker_db
    lease = claim_specific_research_step(
        fixture.db,
        run_id=fixture.run.id,
        step_key=fixture.step.step_key,
        branch_key=fixture.step.branch_key,
        worker_instance_id="worker-expiring",
        lease_seconds=5,
        now=fixture.now,
    )
    reservation = reserve_provider_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        logical_call_key="cancel-before-send",
        request_sha256=sha256("cancel-request"),
        provider=fixture.snapshot.generation_provider,
        model=fixture.snapshot.generation_model,
        provider_config_fingerprint=fixture.snapshot.provider_config_fingerprint,
        reserved_input_tokens=10,
        reserved_output_tokens=10,
        now=fixture.now + timedelta(seconds=1),
    )
    cancel_provider_reservation(
        fixture.db,
        reservation.provider_call_id,
        now=fixture.now + timedelta(seconds=2),
    )
    fixture.db.refresh(fixture.ledger)
    call = fixture.db.get(ResearchProviderCall, reservation.provider_call_id)
    assert call is not None and call.status == "cancelled" and call.usage_final is True
    assert fixture.ledger.reserved_provider_calls == 0
    assert fixture.ledger.reserved_input_tokens == 0

    assert reclaim_expired_research_steps(
        fixture.db,
        now=fixture.now + timedelta(seconds=6),
    ) == 1
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    fixture.db.refresh(fixture.step)
    assert attempt is not None and attempt.status == "abandoned"
    assert fixture.step.status == "queued"
    assert fixture.db.scalar(
        select(ResearchEvent).where(ResearchEvent.event_type == "attempt_abandoned")
    ) is not None


def test_provider_reservation_allows_unknown_pricing_and_records_null_cost(research_worker_db) -> None:
    fixture = research_worker_db
    fixture.snapshot.pricing_version = "unknown-pricing-version"
    fixture.db.commit()
    lease = lease_default_step(fixture)

    reservation = reserve_provider_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        logical_call_key="missing-pricing",
        request_sha256=sha256("missing-pricing"),
        provider=fixture.snapshot.generation_provider,
        model=fixture.snapshot.generation_model,
        provider_config_fingerprint=fixture.snapshot.provider_config_fingerprint,
        reserved_input_tokens=10,
        reserved_output_tokens=10,
        now=fixture.now + timedelta(seconds=1),
    )
    call = fixture.db.get(ResearchProviderCall, reservation.provider_call_id)
    assert call is not None
    assert call.reserved_cost_microunits is None
    fixture.db.refresh(fixture.ledger)
    assert fixture.ledger.reserved_cost_microunits is None
    mark_provider_call_sent(fixture.db, reservation.provider_call_id, now=fixture.now + timedelta(seconds=2))
    reconcile_provider_call(
        fixture.db,
        provider_call_id=reservation.provider_call_id,
        status="succeeded",
        actual_input_tokens=10,
        actual_output_tokens=10,
        usage_source="actual",
        usage_final=True,
        now=fixture.now + timedelta(seconds=3),
    )
    fixture.db.refresh(call)
    assert call.actual_cost_microunits is None
    fixture.db.refresh(fixture.ledger)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert fixture.ledger.actual_cost_microunits is None
    assert attempt is not None and attempt.cost_microunits is None


def test_creator_membership_loss_cancels_idle_run_and_blocks_active_attempt(research_worker_db) -> None:
    fixture = research_worker_db
    membership = fixture.db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == fixture.run.workspace_id,
            WorkspaceMembership.user_id == fixture.run.created_by_user_id,
        )
    )
    assert membership is not None
    fixture.db.delete(membership)
    fixture.db.commit()

    with pytest.raises(ResearchError) as idle_denied:
        claim_specific_research_step(
            fixture.db,
            run_id=fixture.run.id,
            step_key=fixture.step.step_key,
            branch_key=fixture.step.branch_key,
            worker_instance_id="removed-creator-worker",
            now=fixture.now,
        )
    assert_research_error(idle_denied, "research_permission_denied", 403)
    fixture.db.expire_all()
    run = fixture.db.get(ResearchRun, fixture.run.id)
    assert run is not None and run.status == "cancelled"


def test_creator_membership_loss_requests_cancel_for_running_attempt(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    membership = fixture.db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == fixture.run.workspace_id,
            WorkspaceMembership.user_id == fixture.run.created_by_user_id,
        )
    )
    assert membership is not None
    fixture.db.delete(membership)
    fixture.db.commit()

    with pytest.raises(ResearchError) as active_denied:
        heartbeat_research_step(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            now=fixture.now + timedelta(seconds=1),
        )
    assert_research_error(active_denied, "research_permission_denied", 403)
    fixture.db.expire_all()
    run = fixture.db.get(ResearchRun, fixture.run.id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    assert run is not None and run.status == "cancel_requested"
    assert attempt is not None and attempt.status == "running"


def _scalar_lock_trace(session: Session):
    events: list[tuple[str, bool, bool]] = []
    original_scalar = session.scalar

    def recording_scalar(statement, *args, **kwargs):
        entity = statement.column_descriptions[0]["entity"]
        entity_name = getattr(entity, "__name__", None) or type(entity).__name__
        for_update = statement._for_update_arg is not None
        populate_existing = bool(statement.get_execution_options().get("populate_existing"))
        events.append((entity_name, for_update, populate_existing))
        return original_scalar(statement, *args, **kwargs)

    return events, recording_scalar


def test_provider_and_tool_call_chains_lock_attempt_step_run_before_call_and_ledger(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    provider_reservation = reserve_provider_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        logical_call_key="lock-order-provider",
        request_sha256=sha256("provider-lock-order"),
        provider=fixture.snapshot.generation_provider,
        model=fixture.snapshot.generation_model,
        provider_config_fingerprint=fixture.snapshot.provider_config_fingerprint,
        reserved_input_tokens=50,
        reserved_output_tokens=25,
        now=fixture.now + timedelta(seconds=1),
    )
    tool_reservation = begin_tool_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        tool_call_key="lock-order-tool",
        tool_name="evidence.search",
        request_sha256=sha256("tool-lock-order"),
        now=fixture.now + timedelta(seconds=2),
    )

    provider_events, provider_scalar = _scalar_lock_trace(fixture.db)
    with patch.object(fixture.db, "scalar", side_effect=provider_scalar):
        research_worker_provider._provider_call_chain(fixture.db, provider_reservation.provider_call_id)
    provider_locked = [name for name, for_update, _populate in provider_events if for_update]
    assert provider_locked == [
        "ResearchStepAttempt",
        "ResearchStep",
        "ResearchRun",
        "ResearchProviderCall",
        "ResearchBudgetLedger",
    ]
    assert all(populate for _name, for_update, populate in provider_events if for_update)
    assert ("ResearchProviderCall", False, False) in provider_events
    assert ("ResearchProviderCall", True, True) in provider_events
    assert ("ResearchBudgetLedger", True, True) in provider_events

    tool_events, tool_scalar = _scalar_lock_trace(fixture.db)
    with patch.object(fixture.db, "scalar", side_effect=tool_scalar):
        research_worker_tools._tool_call_chain(fixture.db, tool_reservation.tool_call_id)
    tool_locked = [name for name, for_update, _populate in tool_events if for_update]
    assert tool_locked == [
        "ResearchStepAttempt",
        "ResearchStep",
        "ResearchRun",
        "ResearchToolCall",
        "ResearchBudgetLedger",
    ]
    assert all(populate for _name, for_update, populate in tool_events if for_update)
    assert ("ResearchToolCall", False, False) in tool_events
    assert ("ResearchToolCall", True, True) in tool_events
    assert ("ResearchBudgetLedger", True, True) in tool_events


def test_active_and_lease_attempt_helpers_reuse_locked_attempt_chain(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    calls: list[str] = []
    original_chain = _locked_attempt_chain

    def tracking_chain(db, attempt_id):
        calls.append(attempt_id)
        return original_chain(db, attempt_id)

    with patch(
        "ai_pdf_api.services.research_worker_lease._locked_attempt_chain",
        side_effect=tracking_chain,
    ):
        _active_attempt_chain(fixture.db, lease.attempt_id, now=fixture.now + timedelta(seconds=1))
        _locked_attempt(
            fixture.db,
            attempt_id=lease.attempt_id,
            lease_token=lease.lease_token,
            now=fixture.now + timedelta(seconds=1),
        )
    assert calls == [lease.attempt_id, lease.attempt_id]


def test_locked_attempt_chain_refreshes_concurrent_terminal_run_state(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    cached_run = fixture.db.get(ResearchRun, fixture.run.id)
    assert cached_run is not None and cached_run.status == "running"
    factory = sessionmaker(
        bind=fixture.db.get_bind(),
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    cancelled_at = fixture.now + timedelta(seconds=1)
    with factory() as concurrent_db:
        concurrent_run = concurrent_db.get(ResearchRun, fixture.run.id)
        assert concurrent_run is not None
        concurrent_run.status = "cancel_requested"
        concurrent_run.cancel_requested_by_user_id = concurrent_run.created_by_user_id
        concurrent_run.cancel_requested_at = cancelled_at
        concurrent_run.cancel_reason_code = "user_cancel"
        concurrent_db.commit()

    run, step, attempt = _locked_attempt_chain(fixture.db, lease.attempt_id)

    assert run is cached_run
    assert run.status == "cancel_requested"
    assert run.cancel_requested_at is not None
    assert step is not None and step.id == fixture.step.id
    assert attempt is not None and attempt.id == lease.attempt_id


def test_reconcile_provider_call_after_run_cancel_preserves_usage_accounting(
    research_worker_db,
) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    reservation = reserve_provider_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        logical_call_key="cancel-reconcile",
        request_sha256=sha256("cancel-reconcile"),
        provider=fixture.snapshot.generation_provider,
        model=fixture.snapshot.generation_model,
        provider_config_fingerprint=fixture.snapshot.provider_config_fingerprint,
        reserved_input_tokens=100,
        reserved_output_tokens=40,
        now=fixture.now + timedelta(seconds=1),
    )
    mark_provider_call_sent(
        fixture.db,
        reservation.provider_call_id,
        now=fixture.now + timedelta(seconds=2),
    )
    fixture.run.status = "cancel_requested"
    fixture.run.cancel_requested_by_user_id = fixture.run.created_by_user_id
    fixture.run.cancel_requested_at = fixture.now + timedelta(seconds=2)
    fixture.run.cancel_reason_code = "user_cancel"
    fixture.db.commit()

    reconcile_provider_call(
        fixture.db,
        provider_call_id=reservation.provider_call_id,
        status="succeeded",
        actual_input_tokens=90,
        actual_output_tokens=30,
        usage_source="actual",
        usage_final=True,
        now=fixture.now + timedelta(seconds=3),
    )

    fixture.db.expire_all()
    call = fixture.db.get(ResearchProviderCall, reservation.provider_call_id)
    ledger = fixture.db.get(ResearchBudgetLedger, fixture.ledger.id)
    attempt = fixture.db.get(ResearchStepAttempt, lease.attempt_id)
    run = fixture.db.get(ResearchRun, fixture.run.id)
    assert call is not None and call.status == "succeeded"
    assert call.actual_input_tokens == 90
    assert call.actual_output_tokens == 30
    assert call.usage_final is True
    assert ledger is not None
    assert ledger.reserved_provider_calls == 0
    assert ledger.reserved_input_tokens == 0
    assert ledger.reserved_output_tokens == 0
    assert ledger.reserved_cost_microunits == 0
    assert ledger.actual_provider_calls == 1
    assert ledger.actual_input_tokens == 90
    assert ledger.actual_output_tokens == 30
    assert attempt is not None and attempt.provider_call_count == 1
    assert attempt.input_tokens == 90
    assert attempt.output_tokens == 30
    assert run is not None and run.status == "cancel_requested"


def test_mark_provider_call_sent_rejects_after_run_cancellation(research_worker_db) -> None:
    fixture = research_worker_db
    lease = lease_default_step(fixture)
    reservation = reserve_provider_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        logical_call_key="send-after-cancel",
        request_sha256=sha256("send-after-cancel"),
        provider=fixture.snapshot.generation_provider,
        model=fixture.snapshot.generation_model,
        provider_config_fingerprint=fixture.snapshot.provider_config_fingerprint,
        reserved_input_tokens=20,
        reserved_output_tokens=10,
        now=fixture.now + timedelta(seconds=1),
    )
    fixture.run.status = "cancel_requested"
    fixture.run.cancel_requested_by_user_id = fixture.run.created_by_user_id
    fixture.run.cancel_requested_at = fixture.now + timedelta(seconds=1)
    fixture.run.cancel_reason_code = "user_cancel"
    fixture.db.commit()

    with pytest.raises(ResearchError) as sent_error:
        mark_provider_call_sent(
            fixture.db,
            reservation.provider_call_id,
            now=fixture.now + timedelta(seconds=2),
        )
    assert_research_error(sent_error, "research_state_conflict", 409)
    fixture.db.rollback()
    fixture.db.refresh(fixture.ledger)
    call = fixture.db.get(ResearchProviderCall, reservation.provider_call_id)
    assert call is not None and call.status == "reserved"
    assert fixture.ledger.reserved_provider_calls == 1
    assert fixture.ledger.actual_provider_calls == 0

def test_embedding_index_mismatch_is_non_retryable_failure_code() -> None:
    reason = normalize_failure_code("embedding_index_mismatch")
    assert reason == "embedding_index_mismatch"
    assert is_transient_failure(reason) is False
    # Generic unmapped codes remain non-retryable execution failures.
    assert is_transient_failure(normalize_failure_code("some_unknown_code")) is False


def test_cumulative_token_usage_is_not_a_reservation_gate(research_worker_db) -> None:
    fixture = research_worker_db
    # Raise call limit so only token/cost cumulative gates could have blocked previously.
    fixture.snapshot.max_provider_calls = 10
    fixture.snapshot.max_input_tokens = 100
    fixture.snapshot.max_output_tokens = 100
    fixture.db.commit()
    lease = lease_default_step(fixture)

    first = reserve_provider_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        logical_call_key="token-usage-1",
        request_sha256=sha256("token-usage-1"),
        provider=fixture.snapshot.generation_provider,
        model=fixture.snapshot.generation_model,
        provider_config_fingerprint=fixture.snapshot.provider_config_fingerprint,
        reserved_input_tokens=90,
        reserved_output_tokens=90,
        now=fixture.now + timedelta(seconds=1),
    )
    mark_provider_call_sent(fixture.db, first.provider_call_id, now=fixture.now + timedelta(seconds=2))
    reconcile_provider_call(
        fixture.db,
        provider_call_id=first.provider_call_id,
        status="succeeded",
        actual_input_tokens=90,
        actual_output_tokens=90,
        usage_source="actual",
        usage_final=True,
        now=fixture.now + timedelta(seconds=3),
    )
    # Cumulative tokens already equal the frozen max, but a second per-call reserve still succeeds.
    second = reserve_provider_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        logical_call_key="token-usage-2",
        request_sha256=sha256("token-usage-2"),
        provider=fixture.snapshot.generation_provider,
        model=fixture.snapshot.generation_model,
        provider_config_fingerprint=fixture.snapshot.provider_config_fingerprint,
        reserved_input_tokens=90,
        reserved_output_tokens=90,
        now=fixture.now + timedelta(seconds=4),
    )
    assert second.provider_call_id
