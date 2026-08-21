from __future__ import annotations
import hashlib
import json
from citeframe_persistence.models import ResearchEvidenceSnapshot
MAX_FROZEN_EVIDENCE_EXCERPT_CHARS = 2000

def evidence_source_fingerprint(evidence: ResearchEvidenceSnapshot, *, locator_kind: str) -> str:
    payload = {"assetId": evidence.asset_id, "locatorId": evidence.evidence_locator_id, "locatorKind": locator_kind, "processingGeneration": evidence.processing_generation_snapshot, "indexVersion": evidence.index_version_snapshot, "representationId": evidence.representation_id_snapshot, "parserVersion": evidence.parser_version_snapshot, "excerpt": evidence.excerpt_snapshot}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

def validate_evidence_source_fingerprint(evidence: ResearchEvidenceSnapshot, *, locator_kind: str) -> None:
    if not 1 <= len(evidence.excerpt_snapshot) <= MAX_FROZEN_EVIDENCE_EXCERPT_CHARS or evidence.source_fingerprint_sha256 != evidence_source_fingerprint(evidence, locator_kind=locator_kind):
        raise ValueError("research_evidence_source_fingerprint_invalid")
