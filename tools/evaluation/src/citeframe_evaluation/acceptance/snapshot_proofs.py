"""Verify frozen rows against the production approval hash domain."""
from types import SimpleNamespace as NS


def valid_snapshot(facts):
    from ai_pdf_api.models import ResearchExecutionSnapshot, ResearchExecutionAsset, ResearchExecutionPromptVersion
    from citeframe_research_persistence.snapshot_integrity import build_execution_snapshot_hash_payload
    from ai_pdf_api.services.research.research_idempotency import canonical_sha256

    snapshot, proof = facts["snapshot"], facts["snapshotProof"]
    revision, decision = proof["revision"], proof["decision"]
    assets, prompts = proof["assets"], proof["prompts"]
    assert {c.key for c in ResearchExecutionSnapshot.__table__.columns} <= snapshot.keys(), "snapshot_fields_missing"
    assert snapshot["approved_plan_revision_id"] == revision["id"]
    assert snapshot["approval_decision_id"] == decision["id"]
    for raw in (revision, decision):
        assert (raw["run_id"], raw["workspace_id"]) == (snapshot["run_id"], snapshot["workspace_id"])
    assert assets and prompts, "snapshot_children_missing"
    assert len({a["asset_id"] for a in assets}) == len(assets)
    assert sorted(a["asset_order"] for a in assets) == list(range(len(assets)))
    assert len({p["node_key"] for p in prompts}) == len(prompts)
    for model, rows in ((ResearchExecutionAsset, assets), (ResearchExecutionPromptVersion, prompts)):
        for raw in rows:
            assert {c.key for c in model.__table__.columns} <= raw.keys()
            assert raw["execution_snapshot_id"] == snapshot["id"]
    assert all(a["workspace_id"] == snapshot["workspace_id"] for a in assets)
    mapping = {"input_version": "revision_number", "question_text": "question_text", "scope_mode": "scope_mode"}
    proposed = ("workflow_version_id generation_provider generation_model provider_config_fingerprint "
                "pricing_version data_boundary_policy_version embedding_provider embedding_model embedding_version "
                "retrieval_strategy retrieval_top_k max_parallel_researchers max_step_attempts max_provider_calls "
                "max_tool_calls max_input_tokens max_output_tokens max_cost_microunits cost_currency "
                "budget_policy_version retry_policy_version max_run_timeout_seconds max_step_timeout_seconds "
                "max_provider_timeout_seconds").split()
    mapping.update({k: "proposed_" + k for k in proposed})
    mapping.update({k: k for k in ("agent_result_schema_version", "context_policy_version", "compact_policy_version")})
    assert all(snapshot[k] == revision[v] for k, v in mapping.items()), "snapshot_body_revision_mismatch"
    assert snapshot["approved_plan_artifact_id"] == decision["input_artifact_id"]
    assert snapshot["approved_plan_artifact_sha256"] == decision["input_artifact_sha256"]
    bindings = [(NS(node_key=p["node_key"]), NS(id=p["prompt_version_id"]))
                for p in sorted(prompts, key=lambda p: p["node_key"])]
    payload = build_execution_snapshot_hash_payload(NS(**revision), NS(**decision),
        [NS(**a) for a in sorted(assets, key=lambda a: a["asset_order"])], bindings)
    # IDs/created_at/cost ceilings excluded by the production hash remain covered by full row equality.
    return canonical_sha256(payload) == snapshot["execution_snapshot_sha256"]
