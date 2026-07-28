"""Shared R800 acceptance constants, IDs, relation lists, and canonical hashing."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

SCHEMA_VERSION = "citeframe-r800-research-acceptance-v1"
SNAPSHOT_VERSION = "citeframe-r800-research-snapshot-v1"
NOW = datetime(2026, 7, 27, 20, 0, tzinfo=UTC)
API_BASE_URL = os.environ.get("R800_API_BASE_URL", "http://api:8000").rstrip("/")
PROVIDER_BASE_URL = os.environ.get(
    "R800_PROVIDER_BASE_URL", "http://provider-stub:18082"
).rstrip("/")
ID_NAMESPACE = f"{NAMESPACE_URL}citeframe/r800/"
IDS = {
    name: str(uuid5(NAMESPACE_URL, f"{ID_NAMESPACE}{name}"))
    for name in (
        "owner",
        "creator",
        "member",
        "workspace",
        "owner-membership",
        "creator-membership",
        "member-membership",
        "asset",
        "representation",
        "page",
        "locator",
        "unit",
        "embedding",
    )
}
SOURCE_TEXT = (
    "R800 supported evidence states that the bounded research fixture preserves "
    "workspace isolation, immutable provenance, conflict review, and restore identity."
)
RESEARCH_RELATIONS = (
    "workflow_versions",
    "prompt_versions",
    "workflow_prompt_bindings",
    "research_runs",
    "research_plan_revisions",
    "research_plan_revision_assets",
    "research_execution_snapshots",
    "research_execution_assets",
    "research_execution_prompt_versions",
    "research_steps",
    "research_step_dependencies",
    "research_step_attempts",
    "research_step_retry_requests",
    "research_events",
    "research_artifacts",
    "research_artifact_prompt_versions",
    "research_claims",
    "research_evidence_snapshots",
    "research_claim_evidence",
    "research_artifact_claims",
    "human_decisions",
    "human_decision_claims",
    "research_tool_calls",
    "research_evidence_handles",
    "research_tool_call_input_handles",
    "research_budget_ledgers",
    "research_provider_calls",
    "research_idempotency_records",
    "research_evaluation_suites",
    "research_evaluation_runs",
    "research_evaluation_case_results",
    "research_evaluation_claim_results",
)
FIXTURE_RELATIONS = (
    "users",
    "workspaces",
    "workspace_memberships",
    "assets",
    "asset_representations",
    "pdf_pages",
    "evidence_locators",
    "pdf_locator_details",
    "content_units",
    "content_unit_embeddings",
)


def _id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{ID_NAMESPACE}{name}"))


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _semantic_sha256(value: object) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _fixture_facts() -> dict[str, object]:
    return {
        "workspaceId": IDS["workspace"],
        "ownerUserId": IDS["owner"],
        "creatorUserId": IDS["creator"],
        "memberUserId": IDS["member"],
        "assetId": IDS["asset"],
        "representationId": IDS["representation"],
        "evidenceLocatorId": IDS["locator"],
        "contentUnitId": IDS["unit"],
        "embeddingId": IDS["embedding"],
    }
