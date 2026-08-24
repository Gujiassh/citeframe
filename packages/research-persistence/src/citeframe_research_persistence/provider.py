from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from citeframe_persistence.models import (ResearchBudgetLedger, ResearchExecutionSnapshot, ResearchPlanRevision, ResearchProviderCall, ResearchRun, ResearchStep, ResearchStepAttempt)
from .errors import ResearchError
from .lease import _active_attempt_chain, _ledger_and_limits, _locked_attempt_chain
from .membership import ensure_creator_membership
from .policy import add_optional_cost, estimate_provider_cost, subtract_optional_cost
from .types import ProviderReservation


def _frozen_retrieval_top_k(db: Session, step: ResearchStep) -> int:
    if step.execution_snapshot_id is not None:
        snapshot = db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
        if snapshot is None:
            raise ResearchError("research_state_conflict", "Research execution snapshot is missing for provider profile resolution.", 409)
        return snapshot.retrieval_top_k
    if step.plan_revision_id is not None:
        revision = db.get(ResearchPlanRevision, step.plan_revision_id)
        if revision is None:
            raise ResearchError("research_state_conflict", "Research plan revision is missing for provider profile resolution.", 409)
        return revision.proposed_retrieval_top_k
    raise ResearchError("research_state_conflict", "Research step is missing a frozen plan revision or execution snapshot.", 409)


def resolve_actual_research_provider_config_fingerprint(db: Session, step: ResearchStep, resolver: Callable[[int], str] | None = None) -> str:
    if resolver is None:
        raise ResearchError("research_provider_config_unavailable", "A provider capability resolver is required at the composition boundary.", 503)
    return resolver(_frozen_retrieval_top_k(db, step))


def frozen_provider_config_matches_actual(db: Session, step: ResearchStep, frozen_fingerprint: str, resolver: Callable[[int], str] | None = None) -> bool:
    # The provider capability check is an injected composition port; the DB package never imports its implementation.
    return resolver(_frozen_retrieval_top_k(db, step)) == frozen_fingerprint if resolver is not None else True

def reserve_provider_call(
    db: Session,
    *,
    attempt_id: str,
    logical_call_key: str,
    request_sha256: str,
    provider: str,
    model: str,
    provider_config_fingerprint: str,
    reserved_input_tokens: int,
    reserved_output_tokens: int,
    now: datetime | None = None,
    provider_config_matcher: Callable[[Session, ResearchStep, str], bool] | None = None,
) -> ProviderReservation:
    reserved_at = now or datetime.now(UTC)
    _run, step, attempt = _active_attempt_chain(db, attempt_id, now=reserved_at)
    if (
        min(reserved_input_tokens, reserved_output_tokens) < 0
        or not logical_call_key
        or len(logical_call_key) > 160
        or len(request_sha256) != 64
    ):
        raise ValueError("invalid provider reservation")
    if step.plan_revision_id is not None:
        revision = db.get(ResearchPlanRevision, step.plan_revision_id)
        assert revision is not None
        frozen_provider = (
            revision.proposed_generation_provider,
            revision.proposed_generation_model,
            revision.proposed_provider_config_fingerprint,
        )
        pricing_version = revision.proposed_pricing_version
    else:
        snapshot = db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
        assert snapshot is not None
        frozen_provider = (
            snapshot.generation_provider,
            snapshot.generation_model,
            snapshot.provider_config_fingerprint,
        )
        pricing_version = snapshot.pricing_version
    if (provider, model, provider_config_fingerprint) != frozen_provider:
        raise ResearchError("research_state_conflict", "Provider reservation does not match the frozen profile.", 409)
    if provider_config_matcher is None:
        raise ResearchError(
            "research_provider_config_unavailable",
            "A provider capability matcher is required at the composition boundary.",
            503,
        )
    if not provider_config_matcher(db, step, provider_config_fingerprint):
        raise ResearchError(
            "research_provider_config_drift",
            "Actual provider capability profile does not match the frozen Research fingerprint.",
            409,
        )
    # Pricing is optional accounting metadata. Unknown cost stays null/unavailable.
    estimated_cost = estimate_provider_cost(
        provider=provider,
        model=model,
        pricing_version=pricing_version,
        input_tokens=reserved_input_tokens,
        output_tokens=reserved_output_tokens,
    )
    reserved_cost_microunits = estimated_cost
    ledger, max_calls, _max_tools, max_input, max_output, _max_cost = _ledger_and_limits(db, step)
    # Hard start/reserve gates: provider calls only. Input/output tokens are
    # per-call context limits enforced at provider send, not cumulative budgets.
    # Cost is never a reservation gate in V5-C.
    if ledger.actual_provider_calls + ledger.reserved_provider_calls + 1 > max_calls:
        raise ResearchError("research_budget_limit", "Research provider budget is exhausted.", 429)
    # Per-call context/output ceilings still bound a single reservation size.
    if reserved_input_tokens > max_input or reserved_output_tokens > max_output:
        raise ResearchError(
            "research_context_limit_exceeded",
            "Reserved provider tokens exceed the frozen per-call context/output limits.",
            422,
        )
    send_attempt = (
        db.scalar(
            select(func.coalesce(func.max(ResearchProviderCall.send_attempt), 0)).where(
                ResearchProviderCall.attempt_id == attempt.id,
                ResearchProviderCall.logical_call_key == logical_call_key,
            )
        )
        or 0
    ) + 1
    call = ResearchProviderCall(
        workspace_id=step.workspace_id,
        run_id=step.run_id,
        budget_ledger_id=ledger.id,
        step_id=step.id,
        attempt_id=attempt.id,
        logical_call_key=logical_call_key,
        send_attempt=send_attempt,
        status="reserved",
        request_sha256=request_sha256,
        provider=provider,
        model=model,
        provider_config_fingerprint=provider_config_fingerprint,
        reserved_input_tokens=reserved_input_tokens,
        reserved_output_tokens=reserved_output_tokens,
        reserved_cost_microunits=reserved_cost_microunits,
        usage_source="reserved",
        usage_final=False,
        reserved_at=reserved_at,
    )
    db.add(call)
    ledger.reserved_provider_calls += 1
    ledger.reserved_input_tokens += reserved_input_tokens
    ledger.reserved_output_tokens += reserved_output_tokens
    ledger.reserved_cost_microunits = add_optional_cost(
        ledger.reserved_cost_microunits,
        reserved_cost_microunits,
    )
    ledger.state_version += 1
    ledger.updated_at = reserved_at
    db.flush()
    return ProviderReservation(provider_call_id=call.id, budget_ledger_id=ledger.id)


def _provider_call_chain(
    db: Session,
    provider_call_id: str,
) -> tuple[ResearchProviderCall, ResearchBudgetLedger, ResearchStepAttempt, ResearchStep, ResearchRun]:
    # The first read is a location hint only. Every mutable row is refreshed after
    # acquiring Run -> Step -> Attempt -> Call -> Ledger.
    with db.no_autoflush:
        locator = db.execute(
            select(
                ResearchProviderCall.run_id,
                ResearchProviderCall.step_id,
                ResearchProviderCall.attempt_id,
                ResearchProviderCall.budget_ledger_id,
            ).where(ResearchProviderCall.id == provider_call_id)
        ).one_or_none()
    if locator is None:
        raise ResearchError("research_state_conflict", "Provider call chain is invalid.", 409)
    run, step, attempt = _locked_attempt_chain(db, locator.attempt_id)
    call = db.scalar(
        select(ResearchProviderCall)
        .where(
            ResearchProviderCall.id == provider_call_id,
            ResearchProviderCall.run_id == locator.run_id,
            ResearchProviderCall.step_id == locator.step_id,
            ResearchProviderCall.attempt_id == locator.attempt_id,
            ResearchProviderCall.budget_ledger_id == locator.budget_ledger_id,
        )
        .with_for_update(of=ResearchProviderCall)
        .execution_options(populate_existing=True)
    )
    ledger = (
        db.scalar(
            select(ResearchBudgetLedger)
            .where(ResearchBudgetLedger.id == call.budget_ledger_id)
            .with_for_update(of=ResearchBudgetLedger)
            .execution_options(populate_existing=True)
        )
        if call
        else None
    )
    if (
        call is None
        or ledger is None
        or attempt is None
        or step is None
        or run is None
        or locator.run_id != run.id
        or locator.step_id != step.id
        or locator.attempt_id != attempt.id
        or locator.budget_ledger_id != ledger.id
        or attempt.step_id != step.id
        or call.attempt_id != attempt.id
        or call.step_id != step.id
        or step.run_id != run.id
        or call.run_id != run.id
        or call.workspace_id != run.workspace_id
        or step.workspace_id != run.workspace_id
        or attempt.workspace_id != run.workspace_id
        or ledger.workspace_id != run.workspace_id
        or ledger.run_id != run.id
        or (
            step.plan_revision_id is not None
            and ledger.plan_revision_id != step.plan_revision_id
        )
        or (
            step.execution_snapshot_id is not None
            and ledger.execution_snapshot_id != step.execution_snapshot_id
        )
    ):
        raise ResearchError("research_state_conflict", "Provider call chain is invalid.", 409)
    return call, ledger, attempt, step, run


def mark_provider_call_sent(db: Session, provider_call_id: str, now: datetime | None = None) -> None:
    call, ledger, _attempt, _step, run = _provider_call_chain(db, provider_call_id)
    ensure_creator_membership(db, run, now=now or datetime.now(UTC))
    if call.status != "reserved" or run.status not in {"planning", "running"}:
        raise ResearchError("research_state_conflict", "Provider reservation cannot be sent.", 409)
    call.status = "sent"
    call.sent_at = now or datetime.now(UTC)
    ledger.reserved_provider_calls -= 1
    ledger.actual_provider_calls += 1
    ledger.state_version += 1
    ledger.updated_at = call.sent_at
    db.flush()


def cancel_provider_reservation(
    db: Session,
    provider_call_id: str,
    *,
    now: datetime | None = None,
) -> None:
    call, ledger, _attempt, _step, _run = _provider_call_chain(db, provider_call_id)
    if call.status != "reserved":
        raise ResearchError("research_state_conflict", "Provider reservation cannot be cancelled.", 409)
    cancelled_at = now or datetime.now(UTC)
    call.status = "cancelled"
    call.usage_final = True
    call.finished_at = cancelled_at
    ledger.reserved_provider_calls -= 1
    ledger.reserved_input_tokens -= call.reserved_input_tokens
    ledger.reserved_output_tokens -= call.reserved_output_tokens
    ledger.reserved_cost_microunits = subtract_optional_cost(
        ledger.reserved_cost_microunits,
        call.reserved_cost_microunits,
    )
    ledger.state_version += 1
    ledger.updated_at = cancelled_at
    db.flush()


def reconcile_provider_call(
    db: Session,
    *,
    provider_call_id: str,
    status: str,
    actual_input_tokens: int,
    actual_output_tokens: int,
    usage_source: str,
    usage_final: bool,
    error_code: str | None = None,
    provider_response_id_hash: str | None = None,
    now: datetime | None = None,
) -> None:
    if status not in {"succeeded", "failed", "outcome_unknown"}:
        raise ValueError("invalid provider terminal status")
    if min(actual_input_tokens, actual_output_tokens) < 0:
        raise ValueError("provider usage must be non-negative")
    if usage_source not in {"actual", "estimated"}:
        raise ValueError("invalid provider usage source")
    if status == "outcome_unknown" and usage_final:
        raise ValueError("outcome_unknown usage cannot be final")
    if usage_source == "estimated" and usage_final:
        raise ValueError("estimated usage cannot be final")
    call, ledger, attempt, step, _run = _provider_call_chain(db, provider_call_id)
    if call.status != "sent":
        raise ResearchError("research_state_conflict", "Provider call cannot be reconciled.", 409)
    if step.plan_revision_id is not None:
        revision = db.get(ResearchPlanRevision, step.plan_revision_id)
        pricing_version = revision.proposed_pricing_version if revision else None
    else:
        snapshot = db.get(ResearchExecutionSnapshot, step.execution_snapshot_id)
        pricing_version = snapshot.pricing_version if snapshot else None
    charged_input_tokens = max(actual_input_tokens, call.reserved_input_tokens) if status == "outcome_unknown" else actual_input_tokens
    charged_output_tokens = max(actual_output_tokens, call.reserved_output_tokens) if status == "outcome_unknown" else actual_output_tokens
    estimated_cost = estimate_provider_cost(
        provider=call.provider,
        model=call.model,
        pricing_version=pricing_version,
        input_tokens=charged_input_tokens,
        output_tokens=charged_output_tokens,
    )
    # Persist unknown cost as null and propagate unknown through aggregates.
    actual_cost_microunits = estimated_cost
    call.status = status
    call.actual_input_tokens = charged_input_tokens
    call.actual_output_tokens = charged_output_tokens
    call.actual_cost_microunits = actual_cost_microunits
    call.usage_source = usage_source
    call.usage_final = usage_final
    call.error_code = error_code
    call.provider_response_id_hash = provider_response_id_hash
    call.finished_at = now or datetime.now(UTC)
    ledger.reserved_input_tokens -= call.reserved_input_tokens
    ledger.reserved_output_tokens -= call.reserved_output_tokens
    ledger.reserved_cost_microunits = subtract_optional_cost(
        ledger.reserved_cost_microunits,
        call.reserved_cost_microunits,
    )
    ledger.actual_input_tokens += charged_input_tokens
    ledger.actual_output_tokens += charged_output_tokens
    ledger.actual_cost_microunits = add_optional_cost(
        ledger.actual_cost_microunits,
        actual_cost_microunits,
    )
    ledger.usage_final = ledger.usage_final and usage_final
    ledger.state_version += 1
    ledger.updated_at = call.finished_at
    attempt.provider_call_count += 1
    attempt.input_tokens += charged_input_tokens
    attempt.output_tokens += charged_output_tokens
    attempt.cost_microunits = add_optional_cost(attempt.cost_microunits, actual_cost_microunits)
    db.flush()
