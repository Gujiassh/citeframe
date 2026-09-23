from __future__ import annotations

from datetime import datetime

from ai_pdf_api.core.settings import settings
from ai_pdf_api.models import (
    PromptVersion,
    WorkflowPromptBinding,
    WorkflowVersion,
)
from ai_pdf_api.services.research.research_constants import (
    DATA_BOUNDARY_POLICY,
    PROMPT_VERSION_IDS,
    RELEASE_ID,
    WORKFLOW_KEY,
    WORKFLOW_VERSION_ID,
)
from ai_pdf_api.services.research.research_idempotency import ResearchError, canonical_sha256
from ai_pdf_api.services.research.research_prompt_provenance import (
    V3_PROMPT_SPECS,
    load_v2_release,
    v3_workflow_manifest,
)
from sqlalchemy.orm import Session


def _profile_fingerprint(*, retrieval_top_k: int | None = None) -> str:
    from ai_pdf_api.services.capabilities import current_execution_profile_fingerprint

    # New revisions always write the v2 capability execution fingerprint.
    # Historical frozen fingerprints are dual-read at approval/reservation time.
    return current_execution_profile_fingerprint(retrieval_top_k=retrieval_top_k)


def _legacy_profile_fingerprint() -> str:
    from ai_pdf_api.services.capabilities import legacy_execution_profile_fingerprint

    return legacy_execution_profile_fingerprint()


def _matches_frozen_profile_fingerprint(
    frozen_fingerprint: str,
    *,
    retrieval_top_k: int | None = None,
) -> bool:
    from ai_pdf_api.services.capabilities import matches_frozen_execution_fingerprint

    return matches_frozen_execution_fingerprint(
        frozen_fingerprint,
        retrieval_top_k=retrieval_top_k,
    )


def _workflow_manifest() -> dict[str, object]:
    return v3_workflow_manifest()


def ensure_research_versions(db: Session, _now: datetime | None = None, *, workflow_id: str = WORKFLOW_VERSION_ID) -> tuple[WorkflowVersion, PromptVersion]:
    try:
        workflow, prompts = load_v2_release(db, workflow_id=workflow_id)
    except ValueError as error:
        raise ResearchError(
            "research_provider_not_configured",
            "The approved Research workflow release is not installed.",
            503,
        ) from error
    return workflow, prompts["planner"]


def publish_research_versions_for_release(db: Session, now: datetime, *, workflow_id: str = WORKFLOW_VERSION_ID) -> tuple[WorkflowVersion, PromptVersion]:
    from .research_prompt_provenance import release_definition
    version, release_id, ids, specs, manifest = release_definition(workflow_id)
    if db.get(WorkflowVersion, workflow_id) is not None:
        return ensure_research_versions(db, workflow_id=workflow_id)
    workflow = WorkflowVersion(id=workflow_id, workflow_key=WORKFLOW_KEY, version_number=version,
        availability="active", manifest_schema_version="2", manifest_json=manifest,
        manifest_sha256=canonical_sha256(manifest), created_by_release_id=release_id, created_at=now)
    db.add(workflow)
    db.flush()
    prompts = {}
    for node, spec in specs.items():
        prompt = PromptVersion(id=ids[node], prompt_key=spec.prompt_key, version_number=version,
            step_kind=spec.step_kind, availability="active", template_text=spec.template_text,
            variables_schema_version="2", variables_schema_json=spec.variables_schema,
            template_sha256=spec.template_sha256, created_by_release_id=release_id, created_at=now)
        db.add(prompt)
        prompts[node] = prompt
    db.flush()
    for node, prompt in prompts.items():
        db.add(WorkflowPromptBinding(workflow_version_id=workflow.id, node_key=node, prompt_version_id=prompt.id))
    return workflow, prompts["planner"]
