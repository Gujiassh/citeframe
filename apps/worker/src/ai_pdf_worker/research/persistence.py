"""Worker composition root for neutral Research persistence commands."""
from __future__ import annotations

from ai_pdf_api.services.research.research_auto_progress import auto_start_plan

from citeframe_research_persistence.adaptive_turns import adaptive_turn
from citeframe_research_persistence.conflict_investigation import conflict_turn, investigation_outcome

from types import SimpleNamespace

from ai_pdf_api.db.session import SessionLocal
from ai_pdf_api.services.research.research_prompt_provenance import (
    load_publication_execution_prompt_dtos,
)
from ai_pdf_api.services.research.research_worker_evidence import (
    load_frozen_evidence,
    restore_frozen_evidence,
    search_frozen_evidence,
)
from ai_pdf_api.services.research.research_worker_lease import (
    load_approved_execution,
    load_planning_input,
)
from ai_pdf_api.services.research.research_worker_provider import (
    frozen_provider_config_matches_actual,
)
from ai_pdf_api.services.research.research_worker_state import (
    load_completed_branch,
    load_conflict_resume_state,
    load_execution_state,
    load_step_handler_input,
)
from ai_pdf_api.services.storage import (
    PUBLICATION_ORPHAN_OBSERVATION_SECONDS,
    delete_object_if_exists,
    delete_publication_object_if_exists,
    download_publication_bytes,
    list_publication_object_keys,
    upload_bytes,
    upload_publication_bytes,
)
from citeframe_research_persistence import (
    completion,
    failure,
    lease,
    provider,
    state,
    tools,
)
from citeframe_research_persistence.plan import publish_research_plan
from citeframe_research_persistence.publication import (
    publish_final_report,
    wait_for_conflict_decision,
)
from citeframe_research_persistence.publication_saga import (
    reconcile_one_publication_intent,
)


def _publish_plan(db, **kwargs):
    return publish_research_plan(
        db,
        auto_start=auto_start_plan,
        store_bytes=kwargs.pop("store_bytes", upload_bytes),
        cleanup_bytes=kwargs.pop("cleanup_bytes", delete_object_if_exists),
        **kwargs,
    )


def _complete_branch(db, **kwargs):
    return completion.complete_research_branch(
        db,
        store_bytes=kwargs.pop("store_bytes", upload_bytes),
        cleanup_bytes=kwargs.pop("cleanup_bytes", delete_object_if_exists),
        **kwargs,
    )


def _complete_synthesis(db, **kwargs):
    return completion.complete_research_synthesis(
        db,
        store_bytes=kwargs.pop("store_bytes", upload_bytes),
        cleanup_bytes=kwargs.pop("cleanup_bytes", delete_object_if_exists),
        **kwargs,
    )


def _publish_final(db, **kwargs):
    return publish_final_report(
        db,
        store_bytes=kwargs.pop("store_bytes", upload_publication_bytes),
        load_bytes=kwargs.pop("load_bytes", download_publication_bytes),
        list_keys=kwargs.pop("list_keys", list_publication_object_keys),
        cleanup_bytes=kwargs.pop("cleanup_bytes", delete_publication_object_if_exists),
        committed_session_factory=kwargs.pop("committed_session_factory", SessionLocal),
        observation_seconds=kwargs.pop(
            "observation_seconds", int(PUBLICATION_ORPHAN_OBSERVATION_SECONDS)
        ),
        prompt_loader=load_publication_execution_prompt_dtos,
        **kwargs,
    )


def _reconcile_publication(db, **kwargs):
    return reconcile_one_publication_intent(
        db,
        store_bytes=kwargs.pop("store_bytes", upload_publication_bytes),
        load_bytes=kwargs.pop("load_bytes", download_publication_bytes),
        list_keys=kwargs.pop("list_keys", list_publication_object_keys),
        cleanup_bytes=kwargs.pop("cleanup_bytes", delete_publication_object_if_exists),
        committed_session_factory=kwargs.pop("committed_session_factory", SessionLocal),
        prompt_loader=load_publication_execution_prompt_dtos,
        observation_seconds=kwargs.pop(
            "observation_seconds", int(PUBLICATION_ORPHAN_OBSERVATION_SECONDS)
        ),
        **kwargs,
    )


def _wait_for_conflict(db, **kwargs):
    return wait_for_conflict_decision(
        db,
        store_bytes=kwargs.pop("store_bytes", upload_bytes),
        cleanup_bytes=kwargs.pop("cleanup_bytes", delete_object_if_exists),
        **kwargs,
    )


def _reserve_provider(db, **kwargs):
    return provider.reserve_provider_call(
        db,
        provider_config_matcher=frozen_provider_config_matches_actual,
        **kwargs,
    )


def build_worker_research_service():
    """Compose neutral transitions with API-owned storage/read capability adapters."""

    return SimpleNamespace(
        adaptive_turn=adaptive_turn,
        conflict_turn=conflict_turn,
        investigation_outcome=investigation_outcome,
        begin_tool_call=tools.begin_tool_call,
        cancel_provider_reservation=provider.cancel_provider_reservation,
        claim_next_research_step=lease.claim_next_research_step,
        claim_specific_research_step=lease.claim_specific_research_step,
        complete_control_step=state.complete_control_step,
        complete_research_branch=_complete_branch,
        complete_research_critique=completion.complete_research_critique,
        complete_research_step=lease.complete_research_step,
        complete_research_synthesis=_complete_synthesis,
        complete_research_verification=completion.complete_research_verification,
        complete_tool_call=tools.complete_tool_call,
        fail_research_step=failure.fail_research_step,
        heartbeat_research_step=lease.heartbeat_research_step,
        load_approved_execution=load_approved_execution,
        load_completed_branch=load_completed_branch,
        load_conflict_resume_state=load_conflict_resume_state,
        load_execution_state=load_execution_state,
        load_step_handler_input=load_step_handler_input,
        load_frozen_evidence=load_frozen_evidence,
        load_planning_input=load_planning_input,
        mark_provider_call_sent=provider.mark_provider_call_sent,
        publish_final_report=_publish_final,
        publish_research_plan=_publish_plan,
        reclaim_expired_research_steps=state.reclaim_expired_research_steps,
        reconcile_one_publication_intent=_reconcile_publication,
        reconcile_provider_call=provider.reconcile_provider_call,
        reserve_provider_call=_reserve_provider,
        restore_evidence_handles=tools.restore_evidence_handles,
        restore_frozen_evidence=restore_frozen_evidence,
        search_frozen_evidence=search_frozen_evidence,
        wait_for_conflict_decision=_wait_for_conflict,
    )
