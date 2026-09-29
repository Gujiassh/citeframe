"""Neutral shared-task compaction identities; no application or ORM imports."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class ContextOwner:
    workspace_id: str
    actor_user_id: str
    kind: Literal["chat", "research"]
    owner_id: str
    lease_token_hash: str

    def __post_init__(self):
        if self.kind not in ("chat", "research") or not all(isinstance(x, str) and x for x in
                (self.workspace_id, self.actor_user_id, self.owner_id, self.lease_token_hash)):
            raise ValueError("invalid_context_owner")


@dataclass(frozen=True)
class SourceReference:
    source_id: str
    version: int
    sha256: str


@dataclass(frozen=True)
class CoverageUnit:
    key: str
    source: SourceReference | None = None
    tool_group_id: str | None = None
    parent_message_id: str | None = None

    def __post_init__(self):
        if (self.source is None) == (self.tool_group_id is None):
            raise ValueError("coverage_target_required")


@dataclass(frozen=True)
class CapturedContext:
    owner: ContextOwner
    context_version: int
    checkpoint_id: str | None
    checkpoint_version: int
    native_fingerprint: str
    units: tuple[CoverageUnit, ...]
    policy_fingerprint: str
    native_manifest_json: str


@dataclass(frozen=True)
class CheckpointReceipt:
    snapshot_id: str
    context_version: int
    version: int
    operation_key: str


@dataclass(frozen=True)
class AccountingReceipt:
    call_id: str
    workspace_id: str
    owner_id: str
    request_sha256: str
    native_provider_call_id: str | None
    native_ledger_id: str | None


@dataclass(frozen=True)
class UsageSettlement:
    state: Literal["succeeded", "failed", "outcome_unknown"]
    input_tokens: int
    output_tokens: int
    source: Literal["reported", "estimated", "unknown"]

    def __post_init__(self):
        if (self.state not in ("succeeded", "failed", "outcome_unknown")
                or self.source not in ("reported", "estimated", "unknown")
                or any(type(n) is not int or n < 0 for n in (self.input_tokens, self.output_tokens))):
            raise ValueError("invalid_usage_settlement")
