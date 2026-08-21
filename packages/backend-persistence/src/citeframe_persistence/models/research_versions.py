from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from citeframe_persistence.base import Base


JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class WorkflowVersion(Base):
    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint("workflow_key", "version_number", name="uq_workflow_versions_key_version"),
        CheckConstraint("version_number > 0", name="ck_workflow_versions_version_positive"),
        CheckConstraint("availability IN ('active', 'retired')", name="ck_workflow_versions_availability"),
        CheckConstraint(
            "(created_by_user_id IS NULL) <> (created_by_release_id IS NULL)",
            name="ck_workflow_versions_single_publisher",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_key: Mapped[str] = mapped_column(String(64))
    version_number: Mapped[int] = mapped_column(Integer)
    availability: Mapped[str] = mapped_column(String(16), default="active")
    manifest_schema_version: Mapped[str] = mapped_column(String(32))
    manifest_json: Mapped[dict[str, object]] = mapped_column(JSON_DOCUMENT)
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_by_release_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("prompt_key", "version_number", name="uq_prompt_versions_key_version"),
        CheckConstraint("version_number > 0", name="ck_prompt_versions_version_positive"),
        CheckConstraint("availability IN ('active', 'retired')", name="ck_prompt_versions_availability"),
        CheckConstraint(
            "(created_by_user_id IS NULL) <> (created_by_release_id IS NULL)",
            name="ck_prompt_versions_single_publisher",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    prompt_key: Mapped[str] = mapped_column(String(96))
    version_number: Mapped[int] = mapped_column(Integer)
    step_kind: Mapped[str] = mapped_column(String(32))
    availability: Mapped[str] = mapped_column(String(16), default="active")
    template_text: Mapped[str] = mapped_column(Text)
    variables_schema_version: Mapped[str] = mapped_column(String(32))
    variables_schema_json: Mapped[dict[str, object]] = mapped_column(JSON_DOCUMENT)
    template_sha256: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_by_release_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowPromptBinding(Base):
    __tablename__ = "workflow_prompt_bindings"

    workflow_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_versions.id"), primary_key=True
    )
    node_key: Mapped[str] = mapped_column(String(96), primary_key=True)
    prompt_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("prompt_versions.id"))
