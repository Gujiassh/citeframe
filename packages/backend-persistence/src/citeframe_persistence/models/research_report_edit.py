from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


class ResearchReportEdit(Base):
    __tablename__ = "research_report_edits"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_research_report_edits_version"),
        CheckConstraint("length(markdown) > 0", name="ck_research_report_edits_markdown"),
    )

    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    actor_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    base_artifact_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_artifacts.id"), nullable=False)
    base_artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
