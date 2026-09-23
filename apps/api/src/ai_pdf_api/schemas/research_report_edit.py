from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SaveResearchReportEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    originalArtifactId: str = Field(min_length=1, max_length=36)
    originalSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expectedVersion: int = Field(ge=0)
    markdown: str = Field(min_length=1, max_length=200_000)


class ResearchReportEditResponse(BaseModel):
    originalArtifactId: str
    originalSha256: str
    version: int
    markdown: str | None
    actorUserId: str | None
    updatedAt: datetime | None
    verificationStatus: Literal["unverified"] = "unverified"
