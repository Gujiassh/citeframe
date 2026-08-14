from datetime import datetime

from sqlalchemy.orm import Session

from ai_pdf_api.modalities.evidence_targets import (
    EvidenceTargetError,
    EvidenceTargetResolverRegistry,
    ImageBytesLoader,
    ResolvedEvidenceTarget,
)
from ai_pdf_api.modalities.image_evidence_targets import ImageRegionEvidenceTargetResolver
from ai_pdf_api.modalities.pdf_evidence_targets import PdfRegionEvidenceTargetResolver
from ai_pdf_api.schemas.chat import EvidenceTargetRequest
from ai_pdf_api.services.storage import download_bytes


PRODUCTION_EVIDENCE_TARGET_RESOLVERS = EvidenceTargetResolverRegistry(
    (ImageRegionEvidenceTargetResolver(), PdfRegionEvidenceTargetResolver())
)


def resolve_evidence_targets(
    db: Session,
    *,
    workspace_id: str,
    targets: list[EvidenceTargetRequest],
    created_at: datetime,
    image_bytes_loader: ImageBytesLoader | None = None,
    include_image_payloads: bool = True,
) -> list[ResolvedEvidenceTarget]:
    return PRODUCTION_EVIDENCE_TARGET_RESOLVERS.resolve(
        db,
        workspace_id=workspace_id,
        targets=targets,
        created_at=created_at,
        image_bytes_loader=image_bytes_loader or download_bytes,
        include_image_payloads=include_image_payloads,
    )


__all__ = [
    "EvidenceTargetError",
    "ImageBytesLoader",
    "ResolvedEvidenceTarget",
    "resolve_evidence_targets",
]
