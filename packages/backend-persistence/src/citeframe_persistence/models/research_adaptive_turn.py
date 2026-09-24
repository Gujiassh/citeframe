from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from citeframe_persistence.base import Base
from citeframe_persistence.models.research_versions import JSON_DOCUMENT


class ResearchAdaptiveTurn(Base):
    __tablename__ = "research_adaptive_turns"
    __table_args__ = (CheckConstraint("turn_number >= 0 AND turn_number <= 2", name="ck_research_adaptive_turn_bound"),)

    step_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_steps.id"), primary_key=True)
    turn_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_snapshot_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_execution_snapshots.id"))
    created_by_attempt_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_step_attempts.id"))
    query: Mapped[str] = mapped_column(String(4000))
    request_sha256: Mapped[str] = mapped_column(String(64))
    result_sha256: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[dict[str, object]] = mapped_column(JSON_DOCUMENT)
