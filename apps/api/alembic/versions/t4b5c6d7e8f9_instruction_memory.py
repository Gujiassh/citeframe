"""Instruction-only private memory foundation, with guarded rollback."""
from alembic import op
import sqlalchemy as sa

revision = "t4b5c6d7e8f9"
down_revision = "s3a4b5c6d7e8"
branch_labels = None
depends_on = None

DDL = (
    r"""CREATE TABLE memory_instructions (
	id VARCHAR(36) NOT NULL,
	workspace_id VARCHAR(36) NOT NULL,
	actor_user_id VARCHAR(36) NOT NULL,
	operation VARCHAR(16) NOT NULL,
	request_id VARCHAR(36) NOT NULL,
	target_memory_id VARCHAR(36),
	expected_version BIGINT,
	content TEXT,
	content_sha256 VARCHAR(64),
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	erased_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	UNIQUE (workspace_id, id),
	UNIQUE (workspace_id, actor_user_id, id),
	UNIQUE (workspace_id, actor_user_id, request_id),
	CONSTRAINT ck_instruction_operation CHECK (operation IN ('remember','correct','deactivate','delete')),
	CONSTRAINT ck_instruction_target CHECK ((operation = 'remember' AND target_memory_id IS NULL AND expected_version IS NULL) OR (operation <> 'remember' AND target_memory_id IS NOT NULL AND expected_version IS NOT NULL AND expected_version >= 1)),
	CONSTRAINT ck_instruction_payload CHECK ((operation IN ('remember','correct') AND ((erased_at IS NULL AND content IS NOT NULL AND length(content) BETWEEN 1 AND 4000 AND content_sha256 IS NOT NULL AND content_sha256 ~ '^[0-9a-f]{64}$' AND content_sha256 = encode(sha256(convert_to(content, 'UTF8')), 'hex')) OR (erased_at IS NOT NULL AND content IS NULL AND content_sha256 IS NULL))) OR (operation IN ('deactivate','delete') AND content IS NULL AND content_sha256 IS NULL)),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT,
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE RESTRICT
)""",
    r"""CREATE TABLE memory_sources (
	id VARCHAR(36) NOT NULL,
	workspace_id VARCHAR(36) NOT NULL,
	kind VARCHAR(32) NOT NULL,
	native_id VARCHAR(36) NOT NULL,
	instruction_id VARCHAR(36) NOT NULL,
	source_version BIGINT NOT NULL,
	native_version JSONB NOT NULL,
	content_sha256 VARCHAR(64),
	actor_user_id VARCHAR(36) NOT NULL,
	audience VARCHAR(16) NOT NULL,
	owner_user_id VARCHAR(36) NOT NULL,
	state VARCHAR(16) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	invalidated_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	UNIQUE (workspace_id, id),
	UNIQUE (workspace_id, owner_user_id, id),
	UNIQUE (workspace_id, kind, native_id, source_version),
	FOREIGN KEY(workspace_id, actor_user_id, instruction_id) REFERENCES memory_instructions (workspace_id, actor_user_id, id),
	CONSTRAINT ck_source_identity CHECK (kind = 'memory_instruction' AND native_id = instruction_id AND source_version >= 1 AND audience = 'private' AND owner_user_id = actor_user_id),
	CONSTRAINT ck_source_state CHECK (state IN ('current','stale','deleted','unavailable') AND ((state <> 'deleted' AND content_sha256 IS NOT NULL AND content_sha256 ~ '^[0-9a-f]{64}$') OR (state = 'deleted' AND content_sha256 IS NULL))),
	CONSTRAINT ck_source_native_version CHECK (jsonb_typeof(native_version) = 'object' AND native_version ?& ARRAY['instructionId','requestId'] AND (native_version - ARRAY['instructionId','requestId']) = '{}'::jsonb AND native_version->>'instructionId' = instruction_id AND jsonb_typeof(native_version->'requestId') = 'string'),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT,
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE RESTRICT,
	FOREIGN KEY(owner_user_id) REFERENCES users (id) ON DELETE RESTRICT
)""",
    r"""CREATE TABLE memory_records (
	id VARCHAR(36) NOT NULL,
	workspace_id VARCHAR(36) NOT NULL,
	owner_user_id VARCHAR(36) NOT NULL,
	scope_kind VARCHAR(16) NOT NULL,
	visibility VARCHAR(16) NOT NULL,
	current_version BIGINT NOT NULL,
	supersedes_id VARCHAR(36),
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (workspace_id, id),
	UNIQUE (workspace_id, owner_user_id, id),
	UNIQUE (supersedes_id),
	FOREIGN KEY(workspace_id, owner_user_id, supersedes_id) REFERENCES memory_records (workspace_id, owner_user_id, id),
	CONSTRAINT ck_memory_record_scope CHECK (scope_kind = 'workspace' AND visibility = 'private' AND current_version >= 1 AND (supersedes_id IS NULL OR supersedes_id <> id)),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT,
	FOREIGN KEY(owner_user_id) REFERENCES users (id) ON DELETE RESTRICT
)""",
    r"""CREATE TABLE memory_revisions (
	workspace_id VARCHAR(36) NOT NULL,
	memory_id VARCHAR(36) NOT NULL,
	version BIGINT NOT NULL,
	revision_id VARCHAR(36) NOT NULL,
	intent VARCHAR(16) NOT NULL,
	validity VARCHAR(16) NOT NULL,
	cause VARCHAR(24) NOT NULL,
	kind VARCHAR(16) NOT NULL,
	content TEXT,
	content_sha256 VARCHAR(64),
	confirmation VARCHAR(24) NOT NULL,
	confirmation_source_id VARCHAR(36) NOT NULL,
	conditions JSONB,
	pinned BOOLEAN NOT NULL,
	valid_until TIMESTAMP WITH TIME ZONE,
	instruction_id VARCHAR(36) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	erased_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (memory_id, version),
	UNIQUE (revision_id),
	UNIQUE (workspace_id, revision_id),
	FOREIGN KEY(workspace_id, memory_id) REFERENCES memory_records (workspace_id, id),
	FOREIGN KEY(workspace_id, confirmation_source_id) REFERENCES memory_sources (workspace_id, id),
	FOREIGN KEY(workspace_id, instruction_id) REFERENCES memory_instructions (workspace_id, id),
	CONSTRAINT ck_memory_revision_enums CHECK (version >= 1 AND intent IN ('active','inactive','superseded','deleted') AND validity IN ('valid','invalidated') AND cause IN ('create','correct','deactivate','invalidate','delete') AND kind IN ('preference','constraint','fact','decision') AND confirmation IN ('explicit_remember','user_confirmed') AND (NOT pinned OR kind IN ('constraint','decision'))),
	CONSTRAINT ck_memory_revision_payload CHECK ((erased_at IS NOT NULL AND content IS NULL AND content_sha256 IS NULL AND conditions IS NULL) OR (erased_at IS NULL AND intent <> 'deleted' AND content IS NOT NULL AND length(content) BETWEEN 1 AND 4000 AND content_sha256 IS NOT NULL AND content_sha256 ~ '^[0-9a-f]{64}$' AND content_sha256 = encode(sha256(convert_to(content, 'UTF8')), 'hex') AND conditions IS NOT NULL AND (jsonb_typeof(conditions) = 'object'
AND conditions ?& ARRAY['subject','applicability','effectiveFrom']
AND (conditions - ARRAY['subject','applicability','effectiveFrom']) = '{}'::jsonb
AND jsonb_typeof(conditions->'subject') = 'string' AND length(conditions->>'subject') BETWEEN 1 AND 256
AND jsonb_typeof(conditions->'applicability') = 'string' AND length(conditions->>'applicability') BETWEEN 1 AND 2000
AND (conditions->'effectiveFrom' = 'null'::jsonb OR
 (jsonb_typeof(conditions->'effectiveFrom') = 'string' AND
 conditions->>'effectiveFrom' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$'))) IS TRUE)),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT
)""",
    r"""CREATE TABLE memory_uses (
	id VARCHAR(36) NOT NULL,
	workspace_id VARCHAR(36) NOT NULL,
	consumer_revision_id VARCHAR(36) NOT NULL,
	source_id VARCHAR(36) NOT NULL,
	use_mode VARCHAR(16) NOT NULL,
	atom_key VARCHAR(128) NOT NULL,
	support_group VARCHAR(128) NOT NULL,
	relation VARCHAR(16) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id, consumer_revision_id) REFERENCES memory_revisions (workspace_id, revision_id),
	FOREIGN KEY(workspace_id, source_id) REFERENCES memory_sources (workspace_id, id),
	UNIQUE (consumer_revision_id, source_id, atom_key, support_group),
	CONSTRAINT ck_memory_use CHECK (use_mode = 'support' AND relation IN ('supports','confirmation') AND length(atom_key) > 0 AND length(support_group) > 0),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT
)""",
    r"""CREATE TABLE memory_operations (
	id VARCHAR(36) NOT NULL,
	workspace_id VARCHAR(36) NOT NULL,
	actor_user_id VARCHAR(36) NOT NULL,
	request_id VARCHAR(36) NOT NULL,
	method VARCHAR(8) NOT NULL,
	path VARCHAR(512) NOT NULL,
	key VARCHAR(128) NOT NULL,
	request_sha256 VARCHAR(64) NOT NULL,
	state VARCHAR(16) NOT NULL,
	resource_id VARCHAR(36),
	result_version BIGINT,
	http_status INTEGER,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	settled_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	UNIQUE (workspace_id, actor_user_id, request_id),
	UNIQUE (workspace_id, actor_user_id, method, path, key),
	FOREIGN KEY(workspace_id, actor_user_id, resource_id) REFERENCES memory_records (workspace_id, owner_user_id, id),
	CONSTRAINT ck_memory_operation CHECK (state IN ('in_progress','committed','failed') AND request_sha256 ~ '^[0-9a-f]{64}$' AND key ~ '^[!-~]{8,128}$' AND method IN ('POST','PATCH','DELETE') AND length(path) BETWEEN 1 AND 512),
	CONSTRAINT ck_memory_operation_result CHECK ((state = 'in_progress' AND settled_at IS NULL AND result_version IS NULL AND http_status IS NULL) OR (state = 'committed' AND settled_at IS NOT NULL AND resource_id IS NOT NULL AND result_version IS NOT NULL AND result_version >= 1 AND http_status BETWEEN 200 AND 299) OR (state = 'failed' AND settled_at IS NOT NULL AND http_status BETWEEN 400 AND 599)),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT,
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE RESTRICT
)""",
    r"""ALTER TABLE memory_instructions ADD CONSTRAINT fk_instruction_target FOREIGN KEY(workspace_id, actor_user_id, target_memory_id) REFERENCES memory_records (workspace_id, owner_user_id, id) DEFERRABLE INITIALLY DEFERRED""",
    r"""CREATE UNIQUE INDEX uq_memory_source_current ON memory_sources (workspace_id, kind, native_id) WHERE state = 'current'""",
    r"""ALTER TABLE memory_records ADD CONSTRAINT fk_memory_current_revision FOREIGN KEY(id, current_version) REFERENCES memory_revisions (memory_id, version) DEFERRABLE INITIALLY DEFERRED""",
    r"""CREATE INDEX ix_memory_use_source ON memory_uses (source_id)""",
)


def upgrade():
    for statement in DDL:
        op.execute(statement)
    op.execute(TRIGGERS)


def downgrade():
    connection = op.get_bind()
    # Retained audit identities require an explicit export/erasure procedure.
    if any(connection.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar()
           for table in TABLES):
        raise RuntimeError("Memory rollback requires empty tables after approved export/erasure")
    op.execute("ALTER TABLE memory_records DROP CONSTRAINT fk_memory_current_revision")
    op.execute("ALTER TABLE memory_instructions DROP CONSTRAINT fk_instruction_target")
    for table in reversed(TABLES):
        op.drop_table(table)
    for function in FUNCTIONS:
        op.execute(f"DROP FUNCTION {function}")


TABLES = ("memory_instructions", "memory_sources", "memory_records", "memory_revisions", "memory_uses", "memory_operations")
FUNCTIONS = ("memory_check_support()", "memory_check_revision_support(varchar)",
             "memory_check_head()", "memory_revision_immutable()", "memory_instruction_immutable()",
             "memory_source_immutable()", "memory_record_immutable()")

TRIGGERS = r'''
CREATE FUNCTION memory_instruction_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW) - ARRAY['content','content_sha256','erased_at']) IS DISTINCT FROM
    (to_jsonb(OLD) - ARRAY['content','content_sha256','erased_at']) OR
    (NEW IS DISTINCT FROM OLD AND NOT (OLD.erased_at IS NULL AND NEW.erased_at IS NOT NULL
     AND NEW.content IS NULL AND NEW.content_sha256 IS NULL)) THEN
   RAISE EXCEPTION 'instruction_erasure_monotonic';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER instruction_erasure_monotonic BEFORE UPDATE ON memory_instructions
 FOR EACH ROW EXECUTE FUNCTION memory_instruction_immutable();

CREATE FUNCTION memory_revision_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'revision_history_retained'; END IF;
 IF (to_jsonb(NEW) - ARRAY['conditions','content','content_sha256','erased_at']) IS DISTINCT FROM
    (to_jsonb(OLD) - ARRAY['conditions','content','content_sha256','erased_at']) OR
    (NEW IS DISTINCT FROM OLD AND NOT (OLD.erased_at IS NULL AND NEW.erased_at IS NOT NULL
     AND NEW.conditions IS NULL AND NEW.content IS NULL AND NEW.content_sha256 IS NULL)) THEN
   RAISE EXCEPTION 'revision_erasure_monotonic';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER revision_erasure_monotonic BEFORE UPDATE OR DELETE ON memory_revisions
 FOR EACH ROW EXECUTE FUNCTION memory_revision_immutable();

CREATE FUNCTION memory_source_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW) - ARRAY['state','content_sha256','invalidated_at']) IS DISTINCT FROM
    (to_jsonb(OLD) - ARRAY['state','content_sha256','invalidated_at']) OR
    (OLD.state <> 'current' AND NEW.state = 'current') OR
    (OLD.state = 'deleted' AND NEW IS DISTINCT FROM OLD) OR
    (NEW.content_sha256 IS DISTINCT FROM OLD.content_sha256 AND
      NOT (NEW.state = 'deleted' AND NEW.content_sha256 IS NULL)) THEN
   RAISE EXCEPTION 'source_identity_immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER memory_source_identity BEFORE UPDATE ON memory_sources
 FOR EACH ROW EXECUTE FUNCTION memory_source_immutable();

CREATE FUNCTION memory_record_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW) - 'current_version') IS DISTINCT FROM (to_jsonb(OLD) - 'current_version') OR
    NEW.current_version NOT IN (OLD.current_version, OLD.current_version + 1) THEN
   RAISE EXCEPTION 'memory_head_cas';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER memory_record_identity BEFORE UPDATE ON memory_records
 FOR EACH ROW EXECUTE FUNCTION memory_record_immutable();

CREATE FUNCTION memory_check_revision_support(rid varchar) RETURNS void LANGUAGE plpgsql AS $$
DECLARE r memory_revisions; owner_id varchar; head_version bigint; head_intent varchar;
BEGIN
 SELECT * INTO r FROM memory_revisions WHERE revision_id = rid;
 IF NOT FOUND THEN RETURN; END IF;
 SELECT owner_user_id, current_version INTO owner_id, head_version FROM memory_records WHERE id = r.memory_id;
 SELECT intent INTO head_intent FROM memory_revisions WHERE memory_id=r.memory_id AND version=head_version;
 IF r.version > head_version OR (r.erased_at IS NOT NULL AND head_intent <> 'deleted') THEN
   RAISE EXCEPTION 'memory_revision_head_required';
 END IF;
 IF NOT EXISTS (
   SELECT 1 FROM memory_uses u JOIN memory_sources s ON s.id = u.source_id
   JOIN memory_instructions i ON i.id = s.instruction_id
   WHERE u.consumer_revision_id = rid AND u.source_id = r.confirmation_source_id
     AND u.relation = 'confirmation' AND s.owner_user_id = owner_id
     AND s.workspace_id = r.workspace_id AND i.operation IN ('remember','correct')
     AND s.native_version->>'requestId' = i.request_id
 ) OR EXISTS (
   SELECT 1 FROM memory_uses u JOIN memory_sources s ON s.id = u.source_id
   WHERE u.consumer_revision_id = rid AND (s.owner_user_id <> owner_id OR s.workspace_id <> r.workspace_id)
 ) OR NOT EXISTS (
   SELECT 1 FROM memory_instructions i WHERE i.id = r.instruction_id
   AND i.actor_user_id = owner_id AND i.workspace_id = r.workspace_id
 ) THEN RAISE EXCEPTION 'memory_revision_support_required'; END IF;
 IF r.erased_at IS NULL AND r.conditions->>'effectiveFrom' IS NOT NULL THEN
   PERFORM (r.conditions->>'effectiveFrom')::timestamptz;
 END IF;
END $$;

CREATE FUNCTION memory_check_support() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME = 'memory_revisions' THEN
   PERFORM memory_check_revision_support(NEW.revision_id);
 ELSE
   IF TG_OP <> 'INSERT' THEN PERFORM memory_check_revision_support(OLD.consumer_revision_id); END IF;
   IF TG_OP <> 'DELETE' THEN PERFORM memory_check_revision_support(NEW.consumer_revision_id); END IF;
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER memory_revision_support_required AFTER INSERT OR UPDATE ON memory_revisions
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION memory_check_support();
CREATE CONSTRAINT TRIGGER memory_use_support_required AFTER INSERT OR UPDATE OR DELETE ON memory_uses
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION memory_check_support();

CREATE FUNCTION memory_check_head() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r memory_records; h memory_revisions; n bigint; predecessor memory_revisions;
        old_intent varchar; new_intent varchar;
BEGIN
 IF TG_OP = 'INSERT' AND NEW.current_version <> 1 THEN
   RAISE EXCEPTION 'memory_initial_version';
 END IF;
 IF TG_OP = 'UPDATE' AND NEW.current_version <> OLD.current_version THEN
   SELECT intent INTO old_intent FROM memory_revisions WHERE memory_id=OLD.id AND version=OLD.current_version;
   SELECT intent INTO new_intent FROM memory_revisions WHERE memory_id=NEW.id AND version=NEW.current_version;
   IF old_intent IS NULL OR new_intent IS NULL OR old_intent = 'deleted' OR
      (old_intent = 'superseded' AND new_intent NOT IN ('superseded','deleted')) OR
      (old_intent = 'inactive' AND new_intent = 'active') THEN
     RAISE EXCEPTION 'memory_terminal_intent';
   END IF;
 END IF;
 SELECT * INTO r FROM memory_records WHERE id = NEW.id;
 SELECT * INTO h FROM memory_revisions WHERE memory_id = r.id AND version = r.current_version;
 SELECT count(*) INTO n FROM memory_revisions WHERE memory_id = r.id;
 IF h.revision_id IS NULL OR n <> r.current_version OR EXISTS
   (SELECT 1 FROM memory_revisions WHERE memory_id=r.id AND version > r.current_version) THEN
   RAISE EXCEPTION 'memory_head_required';
 END IF;
 PERFORM memory_check_revision_support(h.revision_id);
 IF r.supersedes_id IS NOT NULL THEN
   SELECT v.* INTO predecessor FROM memory_records p JOIN memory_revisions v
    ON v.memory_id=p.id AND v.version=p.current_version WHERE p.id=r.supersedes_id;
   IF predecessor.intent NOT IN ('superseded','deleted') THEN RAISE EXCEPTION 'memory_successor_required'; END IF;
 END IF;
 IF h.intent = 'deleted' AND EXISTS
   (SELECT 1 FROM memory_revisions WHERE memory_id=r.id AND erased_at IS NULL) THEN
   RAISE EXCEPTION 'memory_all_revisions_erased';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER memory_head_required AFTER INSERT OR UPDATE ON memory_records
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION memory_check_head();
'''
