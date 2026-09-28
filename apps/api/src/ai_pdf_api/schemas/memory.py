"""Strict HTTP contracts for manual owner-private memory management."""
from __future__ import annotations

from typing import Annotated, Literal
from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StringConstraints, field_serializer, field_validator, model_validator

Identifier = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
Version = Annotated[int, Field(strict=True, ge=1)]
Kind = Literal["preference", "constraint", "fact", "decision"]
Intent = Literal["active", "inactive", "superseded", "deleted"]
Validity = Literal["valid", "invalidated"]
DisplayStatus = Literal["active", "inactive", "superseded", "deleted", "invalidated", "expired"]
Hash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    @field_validator("effectiveFrom", "validUntil", "createdAt", "updatedAt", "occurredAt",
                     mode="before", check_fields=False)
    @classmethod
    def timestamp_input(cls, value):
        if value is not None and not isinstance(value, datetime):
            if not isinstance(value, str) or "T" not in value:
                raise ValueError("iso8601_timestamp_required")
        return value

    @field_serializer("*", when_used="json")
    def utc_dates(self, value):
        return value.astimezone(UTC) if isinstance(value, datetime) else value


class Conditions(StrictModel):
    subject: str = Field(min_length=1, max_length=256)
    applicability: str = Field(min_length=1, max_length=2000)
    effectiveFrom: AwareDatetime | None = None


class WorkspaceScope(StrictModel):
    kind: Literal["workspace"]


class Statement(StrictModel):
    kind: Kind
    content: str = Field(min_length=1, max_length=4000)
    conditions: Conditions
    pinned: StrictBool = False
    validUntil: AwareDatetime | None = None

    @model_validator(mode="after")
    def pinned_kind(self):
        if self.pinned and self.kind not in ("constraint", "decision"):
            raise ValueError("invalid_pinned")
        return self


class CreateRequest(Statement):
    requestId: Identifier
    scope: WorkspaceScope
    sourceRefs: list = Field(default_factory=list, max_length=0)


class CorrectionRequest(Statement):
    requestId: Identifier
    expectedVersion: Version


class DeactivateRequest(StrictModel):
    requestId: Identifier
    expectedVersion: Version
    intent: Literal["inactive"]


class DeleteRequest(StrictModel):
    requestId: Identifier
    expectedVersion: Version


class SourceRef(StrictModel):
    sourceId: Identifier
    sourceVersion: Version
    contentSha256: Hash
    span: None


class SourceReadRequest(StrictModel):
    sourceRef: SourceRef


class ScopeDto(WorkspaceScope):
    threadId: None = None
    runId: None = None


class AvailableMemory(Statement):
    id: Identifier
    workspaceId: Identifier
    ownerUserId: Identifier
    visibility: Literal["private"]
    scope: ScopeDto
    version: Version
    revisionId: Identifier
    intent: Intent
    validity: Validity
    displayStatus: DisplayStatus
    confirmation: Literal["explicit_remember", "user_confirmed"]
    supersedesId: Identifier | None
    createdAt: AwareDatetime
    updatedAt: AwareDatetime
    contentAvailable: Literal[True]
    sourceRefs: list[SourceRef]


class UnavailableMemory(StrictModel):
    id: Identifier
    version: Version
    intent: Intent
    validity: Validity
    displayStatus: DisplayStatus
    contentAvailable: Literal[False]
    reason: Literal["erased", "source_unavailable"]


MemoryDto = Annotated[AvailableMemory | UnavailableMemory, Field(discriminator="contentAvailable")]


class MemoryResponse(StrictModel):
    memory: MemoryDto


class MemoryPage(StrictModel):
    items: list[MemoryDto]
    nextCursor: str | None


class MutationReceipt(MemoryResponse):
    requestId: Identifier
    operationId: Identifier
    resultVersion: Version
    indexState: Literal["not_enabled"]


class CorrectionReceipt(MutationReceipt):
    supersededMemoryId: Identifier


class DeleteReceipt(StrictModel):
    requestId: Identifier
    operationId: Identifier
    resultVersion: Version
    id: Identifier
    intent: Literal["deleted"]
    version: Version
    cleanupState: Literal["completed"]


class OperationDto(StrictModel):
    requestId: Identifier
    accepted: Literal[True]
    operationId: Identifier
    state: Literal["committed"]
    resourceId: Identifier
    resultVersion: Version
    currentVersion: Version
    intent: Intent
    contentAvailable: StrictBool
    cleanupState: Literal["not_required", "completed"]


class Provenance(StrictModel):
    role: Literal["user"]
    actorUserId: Identifier
    actorAttribution: Literal["authenticated"]
    threadId: None = None
    runId: None = None
    parentMessageId: None = None
    confirmation: Literal["explicit_remember"]


class InstructionSourceDto(StrictModel):
    sourceRef: SourceRef
    content: str
    contentKind: Literal["explicit_instruction"]
    occurredAt: AwareDatetime
    sourceState: Literal["current"]
    provenance: Provenance
    branchRelation: Literal["other_task"]
    truncated: Literal[False]
    nextCursor: None = None


class MemoryErrorDetail(StrictModel):
    code: str
    message: str
    retryable: StrictBool
    requestId: Identifier | None
    currentVersion: Version | None = None


class MemoryErrorResponse(StrictModel):
    detail: MemoryErrorDetail
