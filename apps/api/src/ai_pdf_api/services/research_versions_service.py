from __future__ import annotations

from datetime import datetime

from ai_pdf_api.core.settings import settings
from ai_pdf_api.models import (
    PromptVersion,
    WorkflowPromptBinding,
    WorkflowVersion,
)
from ai_pdf_api.services.research_constants import (
    DATA_BOUNDARY_POLICY,
    PROMPT_VERSION_IDS,
    RELEASE_ID,
    WORKFLOW_KEY,
    WORKFLOW_VERSION_ID,
)
from ai_pdf_api.services.research_idempotency import ResearchError, canonical_sha256
from ai_pdf_api.services.research_prompt_provenance import (
    V2_PROMPT_SPECS,
    load_v2_release,
    v2_workflow_manifest,
)
from sqlalchemy.orm import Session


def _profile_fingerprint() -> str:
    return canonical_sha256(
        {
            "generationProvider": settings.generation_provider,
            "generationModel": settings.generation_model,
            "embeddingProvider": settings.embedding_provider,
            "embeddingModel": settings.embedding_model,
            "embeddingVersion": settings.embedding_version,
            "retrievalStrategy": settings.retrieval_strategy,
            "dataBoundaryPolicyVersion": DATA_BOUNDARY_POLICY,
        }
    )


def _workflow_manifest() -> dict[str, object]:
    return v2_workflow_manifest()


def ensure_research_versions(db: Session, _now: datetime | None = None) -> tuple[WorkflowVersion, PromptVersion]:
    try:
        workflow, prompts = load_v2_release(db)
    except ValueError as error:
        raise ResearchError(
            "research_provider_not_configured",
            "The approved Research workflow release is not installed.",
            503,
        ) from error
    return workflow, prompts["planner"]


def publish_research_versions_for_release(db: Session, now: datetime) -> tuple[WorkflowVersion, PromptVersion]:
    existing = db.get(WorkflowVersion, WORKFLOW_VERSION_ID)
    if existing is not None:
        return ensure_research_versions(db)
    manifest = _workflow_manifest()
    workflow = WorkflowVersion(
        id=WORKFLOW_VERSION_ID,
        workflow_key=WORKFLOW_KEY,
        version_number=2,
        availability="active",
        manifest_schema_version="2",
        manifest_json=manifest,
        manifest_sha256=canonical_sha256(manifest),
        created_by_release_id=RELEASE_ID,
        created_at=now,
    )
    db.add(workflow)
    db.flush()

    prompts: list[PromptVersion] = []
    for node_key, spec in V2_PROMPT_SPECS.items():
        template = spec.template_text
        variable_schema = spec.variables_schema
        prompt = PromptVersion(
            id=PROMPT_VERSION_IDS[node_key],
            prompt_key=spec.prompt_key,
            version_number=2,
            step_kind=spec.step_kind,
            availability="active",
            template_text=template,
            variables_schema_version="2",
            variables_schema_json=variable_schema,
            template_sha256=canonical_sha256({"template": template, "variables": variable_schema}),
            created_by_release_id=RELEASE_ID,
            created_at=now,
        )
        db.add(prompt)
        prompts.append(prompt)
    db.flush()
    for (node_key, _kind), prompt in zip(
        (
            ("planner", "planner"),
            ("researchers", "researcher"),
            ("verifier", "verifier"),
            ("critic", "critic"),
            ("synthesizer", "synthesizer"),
        ),
        prompts,
        strict=True,
    ):
        db.add(
            WorkflowPromptBinding(
                workflow_version_id=workflow.id,
                node_key=node_key,
                prompt_version_id=prompt.id,
            )
        )
    return workflow, prompts[0]
