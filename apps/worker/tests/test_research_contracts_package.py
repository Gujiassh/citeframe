from dataclasses import asdict

import citeframe_contracts as new_contracts
from ai_pdf_worker import research_executor_contracts as old_contracts
from ai_pdf_worker.research_executor_tools import EvidenceToolRegistry


def test_legacy_contract_exports_are_the_same_objects() -> None:
    assert set(old_contracts.__all__) == set(new_contracts.__all__)
    for name in new_contracts.__all__:
        assert getattr(old_contracts, name) is getattr(new_contracts, name), name


def test_representative_contract_defaults_and_dataclass_serialization_match() -> None:
    old_draft = old_contracts.PlanSubproblemDraft("question")
    new_draft = new_contracts.PlanSubproblemDraft("question")
    assert old_draft == new_draft
    assert asdict(old_draft) == {"question": "question", "asset_ids": (), "expected_evidence": ()}

    old_claim = old_contracts.VerifiedClaim("claim-1", "fact", ("evidence-1",), "supported")
    new_claim = new_contracts.VerifiedClaim("claim-1", "fact", ("evidence-1",), "supported")
    assert old_claim == new_claim
    assert old_claim.conflict_status == new_claim.conflict_status == "none"
    assert asdict(old_claim) == asdict(new_claim)


def test_concrete_registry_matches_neutral_structural_protocol() -> None:
    if issubclass(EvidenceToolRegistry, new_contracts.EvidenceToolRegistryProtocol):
        return

    class MinimalEvidenceToolPort:
        def restore_handles(self, context):
            return ()

        def search(self, context, *, tool_call_key, query, asset_ids, top_k):
            return ()

        def load(self, context, *, tool_call_key, handle_ids):
            return ()

    context = new_contracts.ToolExecutionContext(
        workspace_id="workspace-1",
        run_id="run-1",
        execution_snapshot_id="snapshot-1",
        execution_snapshot_sha256="a" * 64,
        step_id="step-1",
        attempt_id="attempt-1",
        branch_key="branch-1",
        frozen_assets=(),
    )
    registry = EvidenceToolRegistry(MinimalEvidenceToolPort(), context)
    assert isinstance(registry, new_contracts.EvidenceToolRegistryProtocol)


def test_worker_default_service_exposes_neutral_research_commands() -> None:
    import citeframe_research_persistence as research
    from ai_pdf_worker.research_runtime_processor import build_default_research_service

    service = build_default_research_service()
    for name in (
        "claim_next_research_step",
        "claim_specific_research_step",
        "complete_control_step",
        "complete_research_critique",
        "complete_research_step",
        "complete_research_verification",
        "fail_research_step",
        "heartbeat_research_step",
        "reclaim_expired_research_steps",
    ):
        assert getattr(service, name) is getattr(research, name), name
