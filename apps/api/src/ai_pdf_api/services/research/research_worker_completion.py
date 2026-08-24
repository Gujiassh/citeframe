"""API storage composition facade for neutral Research completion commands."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from functools import wraps

from sqlalchemy.orm import Session

from ai_pdf_api.services.storage import delete_object_if_exists, upload_bytes
from citeframe_research_persistence.completion import (
    BranchClaimDraft,
    VerificationResult,
    complete_research_branch as _complete_research_branch,
    complete_research_critique as _complete_research_critique,
    complete_research_synthesis as _complete_research_synthesis,
    complete_research_verification as _complete_research_verification,
)



def _commit_command(db: Session, command, /, **kwargs):
    try:
        result = command(db, **kwargs)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@wraps(_complete_research_verification)
def complete_research_verification(db: Session, **kwargs):
    return _commit_command(db, _complete_research_verification, **kwargs)


@wraps(_complete_research_critique)
def complete_research_critique(db: Session, **kwargs):
    return _commit_command(db, _complete_research_critique, **kwargs)

def complete_research_branch(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    result: object,
    output_sha256: str,
    store_bytes: Callable[[str, bytes, str], None] = upload_bytes,
    cleanup_bytes: Callable[[str], None] = delete_object_if_exists,
    now: datetime | None = None,
) -> None:
    return _commit_command(
        db,
        _complete_research_branch,
        attempt_id=attempt_id,
        lease_token=lease_token,
        result=result,
        output_sha256=output_sha256,
        store_bytes=store_bytes,
        cleanup_bytes=cleanup_bytes,
        now=now,
    )


def complete_research_synthesis(
    db: Session,
    *,
    attempt_id: str,
    lease_token: str,
    fact_claim_ids: Sequence[str],
    unresolved_claim_ids: Sequence[str],
    store_bytes: Callable[[str, bytes, str], None] = upload_bytes,
    cleanup_bytes: Callable[[str], None] = delete_object_if_exists,
    now: datetime | None = None,
) -> None:
    return _commit_command(
        db,
        _complete_research_synthesis,
        attempt_id=attempt_id,
        lease_token=lease_token,
        fact_claim_ids=fact_claim_ids,
        unresolved_claim_ids=unresolved_claim_ids,
        store_bytes=store_bytes,
        cleanup_bytes=cleanup_bytes,
        now=now,
    )



complete_research_branch.__wrapped__ = _complete_research_branch
complete_research_synthesis.__wrapped__ = _complete_research_synthesis

__all__ = [
    "BranchClaimDraft",
    "VerificationResult",
    "complete_research_branch",
    "complete_research_critique",
    "complete_research_synthesis",
    "complete_research_verification",
]
