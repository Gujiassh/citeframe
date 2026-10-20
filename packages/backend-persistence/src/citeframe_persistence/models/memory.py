"""Instruction-only owner-private memory tables; no native task activation."""
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, JSON,
    ForeignKeyConstraint, Index, Integer, String, Table, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from citeframe_persistence.base import Base


def col(name, typ, *, nullable=False, primary_key=False):
    return Column(name, typ, nullable=nullable, primary_key=primary_key)


def identity():
    return col("id", String(36), primary_key=True)


def workspace():
    return Column("workspace_id", String(36), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)


def user(name):
    return Column(name, String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


def timestamp(name="created_at", nullable=False):
    return col(name, DateTime(timezone=True), nullable=nullable)


instructions = Table(
    "memory_instructions", Base.metadata, identity(), workspace(), user("actor_user_id"),
    col("operation", String(16)), col("request_id", String(36)),
    col("target_memory_id", String(36), nullable=True), col("expected_version", BigInteger, nullable=True),
    col("content", Text, nullable=True), col("content_sha256", String(64), nullable=True),
    timestamp(), timestamp("erased_at", True),
    UniqueConstraint("workspace_id", "id"),
    UniqueConstraint("workspace_id", "actor_user_id", "id"),
    UniqueConstraint("workspace_id", "actor_user_id", "request_id"),
    ForeignKeyConstraint(["workspace_id", "actor_user_id", "target_memory_id"],
                         ["memory_records.workspace_id", "memory_records.owner_user_id", "memory_records.id"],
                         name="fk_instruction_target", use_alter=True, deferrable=True, initially="DEFERRED"),
    CheckConstraint("operation IN ('remember','correct','deactivate','delete')", name="ck_instruction_operation"),
    CheckConstraint("(operation = 'remember' AND target_memory_id IS NULL AND expected_version IS NULL) OR "
                    "(operation <> 'remember' AND target_memory_id IS NOT NULL AND expected_version IS NOT NULL AND expected_version >= 1)", name="ck_instruction_target"),
    CheckConstraint("(operation IN ('remember','correct') AND ((erased_at IS NULL AND content IS NOT NULL "
                    "AND length(content) BETWEEN 1 AND 4000 AND content_sha256 IS NOT NULL "
                    "AND content_sha256 ~ '^[0-9a-f]{64}$' AND content_sha256 = encode(sha256(convert_to(content, 'UTF8')), 'hex')) OR (erased_at IS NOT NULL AND content IS NULL AND content_sha256 IS NULL))) "
                    "OR (operation IN ('deactivate','delete') AND content IS NULL AND content_sha256 IS NULL)", name="ck_instruction_payload").ddl_if(dialect="postgresql"),
)

sources = Table(
    "memory_sources", Base.metadata, identity(), workspace(),
    col("kind", String(32)), col("native_id", String(36)), col("instruction_id", String(36)),
    col("source_version", BigInteger), col("native_version", JSONB().with_variant(JSON(), "sqlite")),
    col("content_sha256", String(64), nullable=True), user("actor_user_id"),
    col("audience", String(16)), user("owner_user_id"), col("state", String(16)),
    timestamp(), timestamp("invalidated_at", True),
    UniqueConstraint("workspace_id", "id"),
    UniqueConstraint("workspace_id", "owner_user_id", "id"),
    UniqueConstraint("workspace_id", "kind", "native_id", "source_version"),
    ForeignKeyConstraint(["workspace_id", "actor_user_id", "instruction_id"],
                         ["memory_instructions.workspace_id", "memory_instructions.actor_user_id", "memory_instructions.id"]),
    CheckConstraint("kind = 'memory_instruction' AND native_id = instruction_id AND source_version >= 1 "
                    "AND audience = 'private' AND owner_user_id = actor_user_id", name="ck_source_identity"),
    CheckConstraint("state IN ('current','stale','deleted','unavailable') AND "
                    "((state <> 'deleted' AND content_sha256 IS NOT NULL AND content_sha256 ~ '^[0-9a-f]{64}$') "
                    "OR (state = 'deleted' AND content_sha256 IS NULL))", name="ck_source_state").ddl_if(dialect="postgresql"),
    CheckConstraint("jsonb_typeof(native_version) = 'object' AND native_version ?& ARRAY['instructionId','requestId'] "
                    "AND (native_version - ARRAY['instructionId','requestId']) = '{}'::jsonb "
                    "AND native_version->>'instructionId' = instruction_id "
                    "AND jsonb_typeof(native_version->'requestId') = 'string'", name="ck_source_native_version").ddl_if(dialect="postgresql"),
)
Index("uq_memory_source_current", sources.c.workspace_id, sources.c.kind, sources.c.native_id,
      unique=True, postgresql_where=text("state = 'current'"))

records = Table(
    "memory_records", Base.metadata, identity(), workspace(), user("owner_user_id"),
    col("scope_kind", String(16)), col("visibility", String(16)), col("current_version", BigInteger),
    col("supersedes_id", String(36), nullable=True), timestamp(),
    UniqueConstraint("workspace_id", "id"), UniqueConstraint("workspace_id", "owner_user_id", "id"),
    UniqueConstraint("supersedes_id"),
    ForeignKeyConstraint(["workspace_id", "owner_user_id", "supersedes_id"],
                         ["memory_records.workspace_id", "memory_records.owner_user_id", "memory_records.id"]),
    ForeignKeyConstraint(["id", "current_version"], ["memory_revisions.memory_id", "memory_revisions.version"],
                         name="fk_memory_current_revision", use_alter=True, deferrable=True, initially="DEFERRED"),
    CheckConstraint("scope_kind = 'workspace' AND visibility = 'private' AND current_version >= 1 "
                    "AND (supersedes_id IS NULL OR supersedes_id <> id)", name="ck_memory_record_scope"),
)

CONDITIONS_CHECK = r"""jsonb_typeof(conditions) = 'object'
AND conditions ?& ARRAY['subject','applicability','effectiveFrom']
AND (conditions - ARRAY['subject','applicability','effectiveFrom']) = '{}'::jsonb
AND jsonb_typeof(conditions->'subject') = 'string' AND length(conditions->>'subject') BETWEEN 1 AND 256
AND jsonb_typeof(conditions->'applicability') = 'string' AND length(conditions->>'applicability') BETWEEN 1 AND 2000
AND (conditions->'effectiveFrom' = 'null'::jsonb OR
 (jsonb_typeof(conditions->'effectiveFrom') = 'string' AND
 conditions->>'effectiveFrom' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$'))"""

revisions = Table(
    "memory_revisions", Base.metadata, workspace(),
    col("memory_id", String(36), primary_key=True), col("version", BigInteger, primary_key=True),
    col("revision_id", String(36)), col("intent", String(16)), col("validity", String(16)),
    col("cause", String(24)), col("kind", String(16)), col("content", Text, nullable=True),
    col("content_sha256", String(64), nullable=True), col("confirmation", String(24)),
    col("confirmation_source_id", String(36)), col("conditions", JSONB(none_as_null=True).with_variant(JSON(none_as_null=True), "sqlite"), nullable=True),
    col("pinned", Boolean), timestamp("valid_until", True), col("instruction_id", String(36)),
    timestamp(), timestamp("erased_at", True),
    UniqueConstraint("revision_id"), UniqueConstraint("workspace_id", "revision_id"),
    ForeignKeyConstraint(["workspace_id", "memory_id"], ["memory_records.workspace_id", "memory_records.id"]),
    ForeignKeyConstraint(["workspace_id", "confirmation_source_id"], ["memory_sources.workspace_id", "memory_sources.id"]),
    ForeignKeyConstraint(["workspace_id", "instruction_id"], ["memory_instructions.workspace_id", "memory_instructions.id"]),
    CheckConstraint("version >= 1 AND intent IN ('active','inactive','superseded','deleted') "
                    "AND validity IN ('valid','invalidated') AND cause IN ('create','correct','deactivate','invalidate','delete') "
                    "AND kind IN ('preference','constraint','fact','decision') "
                    "AND confirmation IN ('explicit_remember','user_confirmed') "
                    "AND (NOT pinned OR kind IN ('constraint','decision'))", name="ck_memory_revision_enums"),
    CheckConstraint("(erased_at IS NOT NULL AND content IS NULL AND content_sha256 IS NULL AND conditions IS NULL) OR "
                    "(erased_at IS NULL AND intent <> 'deleted' AND content IS NOT NULL AND length(content) BETWEEN 1 AND 4000 "
                    "AND content_sha256 IS NOT NULL AND content_sha256 ~ '^[0-9a-f]{64}$' "
                    "AND content_sha256 = encode(sha256(convert_to(content, 'UTF8')), 'hex') "
                    "AND conditions IS NOT NULL AND (" + CONDITIONS_CHECK + ") IS TRUE)", name="ck_memory_revision_payload").ddl_if(dialect="postgresql"),
)

uses = Table(
    "memory_uses", Base.metadata, identity(), workspace(),
    col("consumer_revision_id", String(36)), col("source_id", String(36)),
    col("use_mode", String(16)), col("atom_key", String(128)), col("support_group", String(128)),
    col("relation", String(16)),
    ForeignKeyConstraint(["workspace_id", "consumer_revision_id"], ["memory_revisions.workspace_id", "memory_revisions.revision_id"]),
    ForeignKeyConstraint(["workspace_id", "source_id"], ["memory_sources.workspace_id", "memory_sources.id"]),
    UniqueConstraint("consumer_revision_id", "source_id", "atom_key", "support_group"),
    CheckConstraint("use_mode = 'support' AND relation IN ('supports','confirmation') "
                    "AND length(atom_key) > 0 AND length(support_group) > 0", name="ck_memory_use"),
)
Index("ix_memory_use_source", uses.c.source_id)

operations = Table(
    "memory_operations", Base.metadata, identity(), workspace(), user("actor_user_id"),
    col("request_id", String(36)), col("method", String(8)), col("path", String(512)), col("key", String(128)),
    col("request_sha256", String(64)), col("state", String(16)), col("resource_id", String(36), nullable=True),
    col("result_version", BigInteger, nullable=True), col("http_status", Integer, nullable=True),
    timestamp(), timestamp("settled_at", True),
    UniqueConstraint("workspace_id", "actor_user_id", "request_id"),
    UniqueConstraint("workspace_id", "actor_user_id", "method", "path", "key"),
    ForeignKeyConstraint(["workspace_id", "actor_user_id", "resource_id"],
                         ["memory_records.workspace_id", "memory_records.owner_user_id", "memory_records.id"]),
    CheckConstraint("state IN ('in_progress','committed','failed') AND request_sha256 ~ '^[0-9a-f]{64}$' "
                    "AND key ~ '^[!-~]{8,128}$' AND method IN ('POST','PATCH','DELETE') "
                    "AND length(path) BETWEEN 1 AND 512", name="ck_memory_operation").ddl_if(dialect="postgresql"),
    CheckConstraint("(state = 'in_progress' AND settled_at IS NULL AND result_version IS NULL AND http_status IS NULL) "
                    "OR (state = 'committed' AND settled_at IS NOT NULL AND resource_id IS NOT NULL "
                    "AND result_version IS NOT NULL AND result_version >= 1 AND http_status BETWEEN 200 AND 299) "
                    "OR (state = 'failed' AND settled_at IS NOT NULL AND http_status BETWEEN 400 AND 599)", name="ck_memory_operation_result"),
)


class MemoryInstruction(Base):
    __table__ = instructions


class MemorySource(Base):
    __table__ = sources


class MemoryRecord(Base):
    __table__ = records


class MemoryRevision(Base):
    __table__ = revisions


class MemoryUse(Base):
    __table__ = uses


class MemoryOperation(Base):
    __table__ = operations
