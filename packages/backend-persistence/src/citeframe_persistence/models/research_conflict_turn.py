from __future__ import annotations
from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from citeframe_persistence.base import Base
from .research_versions import JSON_DOCUMENT


class ResearchConflictTurn(Base):
    __tablename__ = "research_conflict_turns"
    __table_args__ = (
        CheckConstraint("operation_number >= 0 AND operation_number < 13", name="ck_conflict_operation_bound"),
        CheckConstraint("status IN ('started','succeeded')", name="ck_conflict_operation_status"),
        CheckConstraint("phase IN ('inspect','search','verify','critic','finish')", name="ck_conflict_operation_phase"),
    )
    step_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_steps.id"), primary_key=True)
    operation_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_snapshot_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_execution_snapshots.id"))
    created_by_attempt_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_step_attempts.id"))
    phase: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    request_sha256: Mapped[str] = mapped_column(String(64))
    request_json: Mapped[dict[str, object]] = mapped_column(JSON_DOCUMENT)
    result_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_json: Mapped[dict[str, object] | None] = mapped_column(JSON_DOCUMENT, nullable=True)
