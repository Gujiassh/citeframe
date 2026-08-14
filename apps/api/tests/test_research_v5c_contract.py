from __future__ import annotations

from datetime import timedelta
from dataclasses import replace

from copy import deepcopy

import pytest
from research_worker_test_support import lease_default_step, sha256
from sqlalchemy import select

from ai_pdf_api.models import ResearchProviderCall
from ai_pdf_api.services.research.research_agent_io_registry import (
    AGENT_RESULT_SCHEMA_VERSION,
    AGENT_RESULT_SCHEMA_VERSION_LEGACY,
    COMPACT_POLICY_VERSION,
    COMPACT_POLICY_VERSION_LEGACY,
    CONTEXT_POLICY_VERSION,
    CONTEXT_POLICY_VERSION_LEGACY,
    AgentIoRegistryEntry,
    current_production_versions,
    require_current_production_registry,
    resolve_role_contract,
    resolve_registry,
)
from ai_pdf_api.services.research.research_context_policy import (
    ResearchContextLimitExceeded,
    ResearchProviderOutputIncomplete,
    _compact_payload,
    decode_compact_payload,
    estimate_text_tokens,
    assert_provider_output_complete,
    pack_provider_messages,
)
from ai_pdf_api.services.research.research_idempotency import ResearchError
from ai_pdf_api.services.research.research_worker import (
    mark_provider_call_sent,
    reconcile_provider_call,
    reserve_provider_call,
)
from ai_pdf_api.services.research.research_worker_policy import estimate_provider_cost, normalize_failure_code


def test_production_registry_is_strict_and_versioned() -> None:
    entry = require_current_production_registry()
    assert entry.agent_result_schema_version == AGENT_RESULT_SCHEMA_VERSION
    assert entry.context_policy_version == CONTEXT_POLICY_VERSION
    assert entry.compact_policy_version == COMPACT_POLICY_VERSION
    assert set(entry.roles) == {"planner", "researcher", "verifier", "critic", "synthesizer"}
    assert current_production_versions() == {
        "agentResultSchemaVersion": AGENT_RESULT_SCHEMA_VERSION,
        "contextPolicyVersion": CONTEXT_POLICY_VERSION,
        "compactPolicyVersion": COMPACT_POLICY_VERSION,
    }
    assert all(
        role.validator_key == "research-agent-validator.v1"
        and role.runtime_adapter_key == "research-runtime-adapter.v1"
        for role in entry.roles.values()
    )
    assert {
        node_key: role.api_projection_key
        for node_key, role in entry.roles.items()
    } == {
        "planner": "research-plan-dto.v1",
        "researcher": "research-claim-dto.v1",
        "verifier": "research-claim-dto.v1",
        "critic": "research-conflict-dto.v1",
        "synthesizer": "research-artifact-dto.v1",
    }


def test_legacy_registry_reader_and_new_run_rejection() -> None:
    legacy = resolve_registry(
        agent_result_schema_version=None,
        context_policy_version=None,
        compact_policy_version=None,
        for_new_run=False,
    )
    assert legacy.agent_result_schema_version == AGENT_RESULT_SCHEMA_VERSION_LEGACY
    assert legacy.context_policy_version == CONTEXT_POLICY_VERSION_LEGACY
    assert legacy.compact_policy_version == COMPACT_POLICY_VERSION_LEGACY
    assert legacy.approved_for_new_runs is False
    assert all(
        role.validator_key == "research-agent-validator.legacy-v0"
        and role.runtime_adapter_key == "research-runtime-adapter.legacy-v0"
        and role.schema_version == AGENT_RESULT_SCHEMA_VERSION_LEGACY
        for role in legacy.roles.values()
    )

    with pytest.raises(ValueError, match="research_agent_io_version_unavailable"):
        resolve_registry(
            agent_result_schema_version=AGENT_RESULT_SCHEMA_VERSION_LEGACY,
            context_policy_version=CONTEXT_POLICY_VERSION_LEGACY,
            compact_policy_version=COMPACT_POLICY_VERSION_LEGACY,
            for_new_run=True,
        )
    with pytest.raises(ValueError, match="research_agent_io_version_unavailable"):
        resolve_registry(
            agent_result_schema_version="unknown",
            context_policy_version=CONTEXT_POLICY_VERSION,
            compact_policy_version=COMPACT_POLICY_VERSION,
            for_new_run=True,
        )




def test_f1_registry_role_metadata_freeze() -> None:
    """Freeze production/legacy RoleContract metadata for frozen v1.

    This is the registry metadata freeze only. Concrete Worker schema, validator,
    prompt, and adapter binding is covered by
    apps/worker/tests/test_research_v5c_agent_io.py::test_f1_executable_registry_runtime_bindings.
    api_projection_key remains registry metadata; API projections are owned by
    research_views and are not resolved through this key.
    """

    production = require_current_production_registry()
    assert production.approved_for_new_runs is True
    assert current_production_versions() == {
        "agentResultSchemaVersion": AGENT_RESULT_SCHEMA_VERSION,
        "contextPolicyVersion": CONTEXT_POLICY_VERSION,
        "compactPolicyVersion": COMPACT_POLICY_VERSION,
    }

    expected_bindings = {
        "planner": (
            "research.planner.v1",
            "research-agent-validator.v1",
            "research-runtime-adapter.v1",
            "research-plan-dto.v1",
            "research.planner",
            "planner",
        ),
        "researcher": (
            "research.researcher.v1",
            "research-agent-validator.v1",
            "research-runtime-adapter.v1",
            "research-claim-dto.v1",
            "research.researcher",
            "researchers",
        ),
        "verifier": (
            "research.verifier.v1",
            "research-agent-validator.v1",
            "research-runtime-adapter.v1",
            "research-claim-dto.v1",
            "research.verifier",
            "verifier",
        ),
        "critic": (
            "research.critic.v1",
            "research-agent-validator.v1",
            "research-runtime-adapter.v1",
            "research-conflict-dto.v1",
            "research.critic",
            "critic",
        ),
        "synthesizer": (
            "research.synthesizer.v1",
            "research-agent-validator.v1",
            "research-runtime-adapter.v1",
            "research-artifact-dto.v1",
            "research.synthesizer",
            "synthesizer",
        ),
    }
    for node_key, expected in expected_bindings.items():
        role = resolve_role_contract(production, node_key)
        assert (
            role.result_schema_id,
            role.validator_key,
            role.runtime_adapter_key,
            role.api_projection_key,
            role.prompt_key,
            role.prompt_node_key,
        ) == expected
        assert role.schema_version == AGENT_RESULT_SCHEMA_VERSION

    legacy = resolve_registry(
        agent_result_schema_version=AGENT_RESULT_SCHEMA_VERSION_LEGACY,
        context_policy_version=CONTEXT_POLICY_VERSION_LEGACY,
        compact_policy_version=COMPACT_POLICY_VERSION_LEGACY,
        for_new_run=False,
    )
    assert legacy.approved_for_new_runs is False
    for node_key, expected in expected_bindings.items():
        role = resolve_role_contract(legacy, node_key)
        schema_id, _validator, _adapter, projection, prompt, prompt_node = expected
        assert role.result_schema_id == schema_id.replace(".v1", ".legacy-v0")
        assert role.validator_key == "research-agent-validator.legacy-v0"
        assert role.runtime_adapter_key == "research-runtime-adapter.legacy-v0"
        assert role.api_projection_key == projection
        assert role.prompt_key == prompt
        assert role.prompt_node_key == prompt_node
        assert role.schema_version == AGENT_RESULT_SCHEMA_VERSION_LEGACY


def test_registry_rejects_role_binding_drift_before_runtime_resolution() -> None:
    entry = require_current_production_registry()
    roles = dict(entry.roles)
    roles["planner"] = replace(roles["planner"], result_schema_id="research.planner.unregistered")
    tampered = AgentIoRegistryEntry(
        agent_result_schema_version=entry.agent_result_schema_version,
        context_policy_version=entry.context_policy_version,
        compact_policy_version=entry.compact_policy_version,
        soft_compact_ratio=entry.soft_compact_ratio,
        mandatory_field_order=entry.mandatory_field_order,
        roles=roles,
        approved_for_new_runs=entry.approved_for_new_runs,
    )
    with pytest.raises(ValueError, match="research_agent_role_version_unavailable"):
        resolve_role_contract(tampered, "planner")

def test_estimate_provider_cost_unknown_is_null() -> None:
    assert (
        estimate_provider_cost(
            provider="openai",
            model="gpt-5.5",
            pricing_version=None,
            input_tokens=100,
            output_tokens=50,
        )
        is None
    )
    assert (
        estimate_provider_cost(
            provider="openai",
            model="gpt-5.5",
            pricing_version="missing-book",
            input_tokens=100,
            output_tokens=50,
        )
        is None
    )
    assert (
        estimate_provider_cost(
            provider="openai",
            model="gpt-5.5",
            pricing_version="research-pricing-v1",
            input_tokens=1_000_000,
            output_tokens=0,
        )
        == 2_500_000
    )


def test_context_pack_fails_closed_before_send_on_mandatory_overflow() -> None:
    huge = {
        "claims": [
            {
                "id": f"claim-{index}",
                "text": "x" * 4000,
                "evidenceHandleIds": [f"handle-{index}"],
            }
            for index in range(40)
        ]
    }
    with pytest.raises(ResearchContextLimitExceeded):
        pack_provider_messages(
            system_text="system",
            user_payload=huge,
            max_input_tokens=50,
            max_output_tokens=100,
        )


def test_context_pack_applies_deterministic_compact_under_soft_threshold() -> None:
    payload = {
        "claims": [
            {"id": "c1", "text": "alpha", "evidenceHandleIds": ["h1"]},
            {"id": "c2", "text": "beta", "evidenceHandleIds": ["h2"]},
        ],
        "branchScope": {"branchKey": "b1"},
    }
    packed = pack_provider_messages(
        system_text="system",
        user_payload=payload,
        max_input_tokens=10_000,
        max_output_tokens=1_000,
    )
    assert packed.request_tokens <= packed.max_input_tokens
    assert packed.compact.preserved_claim_ids == ("c1", "c2")
    assert packed.compact.preserved_evidence_handle_ids == ("h1", "h2")


def test_typed_compact_round_trips_nested_tool_contract_evidence() -> None:
    payload = {
        "subproblem": {"question": "nested", "assetIds": ["asset-1"]},
        "toolContracts": {
            "allowedTools": ["evidence.search.v1"],
            "evidence": [
                {
                    "evidenceHandle": f"h{index}",
                    "content": {"text": f"content-{index}", "parts": [{"kind": "text"}]},
                    "assetId": "asset-1",
                }
                for index in range(17)
            ],
        },
        "claims": [
            {"id": f"c{index}", "evidenceHandleIds": [f"h{index}"]}
            for index in range(17)
        ],
    }
    compacted = _compact_payload(payload)
    assert decode_compact_payload(compacted) == payload


def test_typed_compact_rejects_malformed_nested_batch() -> None:
    payload = _compact_payload(
        {
            "toolContracts": {
                "evidence": [
                    {"evidenceHandle": f"h{index}"}
                    for index in range(9)
                ]
            }
        }
    )
    payload["typedBatches"][0]["rows"] = ["not-a-row"]
    with pytest.raises(ValueError, match="compact batch rows malformed"):
        decode_compact_payload(payload)


def _compact_claim_payload() -> dict[str, object]:
    return _compact_payload(
        {
            "claims": [
                {"id": f"c{index}", "text": f"claim-{index}"}
                for index in range(17)
            ]
        }
    )


@pytest.mark.parametrize(
    ("mutation", "error_pattern"),
    [
        (lambda value: value["typedBatches"][1].update(batchIndex=0), "batch index sequence"),
        (lambda value: value["typedBatches"][1].update(batchIndex=3), "batch index sequence"),
        (
            lambda value: (
                value["typedBatches"].__setitem__(0, {**value["typedBatches"][0], "batchIndex": 1}),
                value["typedBatches"].__setitem__(1, {**value["typedBatches"][1], "batchIndex": 0}),
            ),
            "start sequence",
        ),
        (lambda value: value["orderedPayload"]["claims"].update(batchCount=4), "batch count"),
        (
            lambda value: value["orderedPayload"]["claims"].update(columns=["text", "id"]),
            "column sets",
        ),
        (lambda value: value["typedBatches"][0].update(field="wrong"), "batch path"),
        (lambda value: value["typedBatches"][0].update(startIndex=1), "start sequence"),
        (lambda value: value["typedBatches"][0]["rows"][0].append("extra"), "row width"),
    ],
)
def test_typed_compact_decoder_rejects_mutated_batch_metadata(
    mutation, error_pattern: str,
) -> None:
    compacted = _compact_claim_payload()
    mutation(compacted)
    with pytest.raises(ValueError, match=error_pattern):
        decode_compact_payload(compacted)


def test_typed_compact_decoder_rejects_missing_batch() -> None:
    compacted = _compact_claim_payload()
    compacted["typedBatches"].pop(1)
    with pytest.raises(ValueError, match="batch count"):
        decode_compact_payload(compacted)


def test_typed_compact_decoder_allows_physical_batch_reordering() -> None:
    compacted = _compact_claim_payload()
    compacted["typedBatches"] = list(reversed(compacted["typedBatches"]))
    assert decode_compact_payload(compacted) == {
        "claims": [
            {"id": f"c{index}", "text": f"claim-{index}"}
            for index in range(17)
        ]
    }


def test_typed_compact_batches_preserve_every_ordered_claim_and_evidence_handle() -> None:
    payload = {
        "claims": [
            {"id": f"c{index}", "text": f"claim-{index}", "evidenceHandleIds": [f"h{index}"]}
            for index in range(17)
        ],
        "evidence": [
            {"evidenceHandle": f"h{index}", "sourceFingerprintSha256": f"{index:064x}"}
            for index in range(17)
        ],
        "branchScope": {"branchKey": "branch-1", "assetIds": ["asset-1"]},
    }

    compacted = _compact_payload(payload)
    claim_meta = compacted["orderedPayload"]["claims"]
    evidence_meta = compacted["orderedPayload"]["evidence"]
    claim_batches = [batch for batch in compacted["typedBatches"] if batch["field"] == "claims"]
    evidence_batches = [batch for batch in compacted["typedBatches"] if batch["field"] == "evidence"]

    assert [row[claim_meta["columns"].index("id")] for batch in claim_batches for row in batch["rows"]] == [
        f"c{index}" for index in range(17)
    ]
    assert [row[evidence_meta["columns"].index("evidenceHandle")] for batch in evidence_batches for row in batch["rows"]] == [
        f"h{index}" for index in range(17)
    ]
    evidence_rows = [
        row
        for batch in evidence_batches
        for row in batch["rows"]
    ]
    assert [row[evidence_meta["columns"].index("sourceFingerprintSha256")] for row in evidence_rows] == [
        f"{index:064x}" for index in range(17)
    ]
    assert compacted["branchScope"] == payload["branchScope"]


def test_packed_compact_payload_is_smaller_and_complete() -> None:
    payload = {
        "claims": [
            {"id": f"c{index}", "text": f"claim-{index}", "evidenceHandleIds": [f"h{index}"]}
            for index in range(17)
        ],
        "evidence": [
            {"evidenceHandle": f"h{index}", "sourceFingerprintSha256": f"{index:064x}"}
            for index in range(17)
        ],
        "branchScope": {"branchKey": "branch-1"},
    }
    packed = pack_provider_messages(
        system_text="system",
        user_payload=payload,
        max_input_tokens=700,
        max_output_tokens=100,
    )
    assert packed.compact.applied is True
    assert packed.compact.mode == "typed_compact"
    assert packed.request_tokens == (
        estimate_text_tokens(str(packed.messages[0]["content"]))
        + estimate_text_tokens(str(packed.messages[1]["content"]))
    )
    packed_payload = __import__("json").loads(str(packed.messages[1]["content"]))
    assert packed_payload["format"] == "research-typed-batches-v1"
    assert packed.request_tokens <= 700
    claim_meta = packed_payload["orderedPayload"]["claims"]
    claim_rows = [
        row
        for batch in packed_payload["typedBatches"]
        if batch["field"] == "claims"
        for row in batch["rows"]
    ]
    assert [row[claim_meta["columns"].index("id")] for row in claim_rows] == [f"c{index}" for index in range(17)]
    assert packed.compact.preserved_claim_ids == tuple(f"c{index}" for index in range(17))
    assert packed.compact.preserved_evidence_handle_ids == tuple(f"h{index}" for index in range(17))


def test_nested_researcher_evidence_compact_round_trips_losslessly() -> None:
    payload = {
        "subproblem": {"question": "Q", "assetIds": ["asset-1"]},
        "toolContracts": {
            "allowedTools": ["evidence.search.v1"],
            "evidence": [
                {
                    "evidenceHandle": f"h{index}",
                    "content": f"excerpt-{index}",
                    "assetId": "asset-1",
                }
                for index in range(17)
            ],
        },
        "resultSchema": {"type": "object"},
    }
    compacted = _compact_payload(payload)
    assert any(
        batch.get("fieldPath") == ["toolContracts", "evidence"]
        for batch in compacted["typedBatches"]
    )
    assert decode_compact_payload(compacted) == payload


def test_compact_does_not_expand_a_context_that_already_fits() -> None:
    payload = {"claims": [{"id": "c1", "text": "x", "evidenceHandleIds": ["h1"]}]}
    packed = pack_provider_messages(
        system_text="",
        user_payload=payload,
        max_input_tokens=18,
        max_output_tokens=10,
    )
    assert packed.compact.applied is False
    assert packed.request_tokens <= packed.max_input_tokens
    assert __import__("json").loads(str(packed.messages[1]["content"])) == payload


def test_incomplete_provider_output_fails_closed() -> None:
    with pytest.raises(ResearchProviderOutputIncomplete):
        assert_provider_output_complete("ok", max_output_tokens=1, finish_reason="length")
    with pytest.raises(ResearchProviderOutputIncomplete):
        assert_provider_output_complete("x" * 400, max_output_tokens=1)


def test_failure_code_map_includes_v5c_codes() -> None:
    assert normalize_failure_code("research_context_limit_exceeded") == "research_context_limit_exceeded"
    assert (
        normalize_failure_code("research_provider_output_incomplete")
        == "research_provider_output_incomplete"
    )


def test_reserve_rejects_single_call_over_per_call_limits(research_worker_db) -> None:
    fixture = research_worker_db
    fixture.snapshot.max_input_tokens = 20
    fixture.snapshot.max_output_tokens = 20
    fixture.db.commit()
    lease = lease_default_step(fixture)
    with pytest.raises(ResearchError) as error:
        reserve_provider_call(
            fixture.db,
            attempt_id=lease.attempt_id,
            logical_call_key="over-context",
            request_sha256=sha256("over-context"),
            provider=fixture.snapshot.generation_provider,
            model=fixture.snapshot.generation_model,
            provider_config_fingerprint=fixture.snapshot.provider_config_fingerprint,
            reserved_input_tokens=50,
            reserved_output_tokens=10,
            now=fixture.now + timedelta(seconds=1),
        )
    assert error.value.code == "research_context_limit_exceeded"
    fixture.db.rollback()
    assert fixture.db.scalar(select(ResearchProviderCall)) is None


def test_unknown_pricing_start_and_null_actual_cost(research_worker_db) -> None:
    fixture = research_worker_db
    fixture.snapshot.pricing_version = None
    fixture.db.commit()
    lease = lease_default_step(fixture)
    reservation = reserve_provider_call(
        fixture.db,
        attempt_id=lease.attempt_id,
        logical_call_key="no-pricing",
        request_sha256=sha256("no-pricing"),
        provider=fixture.snapshot.generation_provider,
        model=fixture.snapshot.generation_model,
        provider_config_fingerprint=fixture.snapshot.provider_config_fingerprint,
        reserved_input_tokens=12,
        reserved_output_tokens=8,
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
        status="succeeded",
        actual_input_tokens=12,
        actual_output_tokens=8,
        usage_source="actual",
        usage_final=True,
        now=fixture.now + timedelta(seconds=3),
    )
    call = fixture.db.get(ResearchProviderCall, reservation.provider_call_id)
    assert call is not None
    assert call.actual_cost_microunits is None
