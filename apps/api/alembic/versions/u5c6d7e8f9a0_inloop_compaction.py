"""Atomic shared-task compaction and row-local native revision stamps."""
from alembic import op
import sqlalchemy as sa

revision = "u5c6d7e8f9a0"
down_revision = "t4b5c6d7e8f9"
branch_labels = None
depends_on = None

DDL = (
    r"""CREATE SEQUENCE chat_compaction_revision_seq AS bigint NO CYCLE""",
    r"""ALTER TABLE chat_threads ADD COLUMN compaction_revision BIGINT DEFAULT 1 NOT NULL CONSTRAINT ck_chatthread_compaction_revision CHECK (compaction_revision > 0)""",
    r"""UPDATE chat_threads SET compaction_revision=nextval('chat_compaction_revision_seq')""",
    r"""CREATE FUNCTION chat_threads_compaction_stamp() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP = 'INSERT' THEN NEW.compaction_revision := nextval('chat_compaction_revision_seq');
 ELSIF ROW(NEW.id, NEW.workspace_id, NEW.created_by_user_id, NEW.title, NEW.active_message_id, NEW.archived_at, NEW.last_message_at, NEW.created_at, NEW.updated_at) IS DISTINCT FROM ROW(OLD.id, OLD.workspace_id, OLD.created_by_user_id, OLD.title, OLD.active_message_id, OLD.archived_at, OLD.last_message_at, OLD.created_at, OLD.updated_at) THEN NEW.compaction_revision := nextval('chat_compaction_revision_seq');
 ELSE NEW.compaction_revision := OLD.compaction_revision; END IF;
 RETURN NEW;
END $$""",
    r"""CREATE TRIGGER chat_threads_compaction_revision BEFORE INSERT OR UPDATE ON chat_threads FOR EACH ROW EXECUTE FUNCTION chat_threads_compaction_stamp()""",
    r"""ALTER TABLE chat_messages ADD COLUMN compaction_revision BIGINT DEFAULT 1 NOT NULL CONSTRAINT ck_chatmessage_compaction_revision CHECK (compaction_revision > 0)""",
    r"""UPDATE chat_messages SET compaction_revision=nextval('chat_compaction_revision_seq')""",
    r"""CREATE FUNCTION chat_messages_compaction_stamp() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP = 'INSERT' THEN NEW.compaction_revision := nextval('chat_compaction_revision_seq');
 ELSIF ROW(NEW.id, NEW.workspace_id, NEW.thread_id, NEW.parent_message_id, NEW.role, NEW.content, NEW.status, NEW.model_provider, NEW.model_name, NEW.prompt_version_id, NEW.input_tokens, NEW.output_tokens, NEW.created_at) IS DISTINCT FROM ROW(OLD.id, OLD.workspace_id, OLD.thread_id, OLD.parent_message_id, OLD.role, OLD.content, OLD.status, OLD.model_provider, OLD.model_name, OLD.prompt_version_id, OLD.input_tokens, OLD.output_tokens, OLD.created_at) THEN NEW.compaction_revision := nextval('chat_compaction_revision_seq');
 ELSE NEW.compaction_revision := OLD.compaction_revision; END IF;
 RETURN NEW;
END $$""",
    r"""CREATE TRIGGER chat_messages_compaction_revision BEFORE INSERT OR UPDATE ON chat_messages FOR EACH ROW EXECUTE FUNCTION chat_messages_compaction_stamp()""",
    r"""ALTER TABLE memory_sources ALTER COLUMN instruction_id DROP NOT NULL""",
    r"""ALTER TABLE memory_sources ALTER COLUMN actor_user_id DROP NOT NULL""",
    r"""ALTER TABLE memory_sources ALTER COLUMN owner_user_id DROP NOT NULL""",
    r"""ALTER TABLE memory_uses ALTER COLUMN consumer_revision_id DROP NOT NULL""",
    r"""ALTER TABLE memory_uses ALTER COLUMN source_id DROP NOT NULL""",
    r"""ALTER TABLE memory_sources DROP CONSTRAINT ck_source_identity""",
    r"""ALTER TABLE memory_sources ADD CONSTRAINT ck_source_identity CHECK (source_version >= 1 AND ((kind = 'memory_instruction' AND instruction_id IS NOT NULL AND native_id = instruction_id AND actor_user_id IS NOT NULL AND owner_user_id IS NOT NULL AND owner_user_id = actor_user_id AND audience = 'private') OR (kind IN ('chat_message','research_evidence') AND instruction_id IS NULL AND actor_user_id IS NULL AND owner_user_id IS NULL AND audience = 'workspace')))""",
    r"""ALTER TABLE memory_sources DROP CONSTRAINT ck_source_native_version""",
    r"""ALTER TABLE memory_sources ADD CONSTRAINT ck_source_native_version CHECK ((jsonb_typeof(native_version) = 'object' AND (
(kind = 'memory_instruction' AND native_version ?& ARRAY['instructionId','requestId'] AND (native_version - ARRAY['instructionId','requestId']) = '{}'::jsonb AND native_version->>'instructionId' = instruction_id AND jsonb_typeof(native_version->'requestId') = 'string') OR
(kind = 'chat_message' AND native_version ?& ARRAY['messageId','parentMessageId','role','status','contentSha256','compactionRevision'] AND (native_version - ARRAY['messageId','parentMessageId','role','status','contentSha256','compactionRevision']) = '{}'::jsonb AND native_version->>'messageId' = native_id AND (native_version->'parentMessageId' = 'null'::jsonb OR jsonb_typeof(native_version->'parentMessageId') = 'string') AND native_version->>'role' IN ('user','assistant') AND native_version->>'status' IN ('completed','failed') AND native_version->>'contentSha256' = content_sha256 AND jsonb_typeof(native_version->'compactionRevision') = 'number' AND (native_version->>'compactionRevision') ~ '^[1-9][0-9]*$') OR
(kind = 'research_evidence' AND native_version ?& ARRAY['runId','executionSnapshotId','evidenceSnapshotId','evidenceHandleId','sourceFingerprintSha256'] AND (native_version - ARRAY['runId','executionSnapshotId','evidenceSnapshotId','evidenceHandleId','sourceFingerprintSha256']) = '{}'::jsonb AND native_version->>'evidenceHandleId' = native_id AND jsonb_typeof(native_version->'runId') = 'string' AND jsonb_typeof(native_version->'executionSnapshotId') = 'string' AND jsonb_typeof(native_version->'evidenceSnapshotId') = 'string' AND native_version->>'sourceFingerprintSha256' ~ '^[0-9a-f]{64}$')
)) IS TRUE)""",
    r"""ALTER TABLE memory_uses DROP CONSTRAINT ck_memory_use""",
    r"""CREATE TABLE chat_memory_executions (
	id VARCHAR(36) NOT NULL, 
	workspace_id VARCHAR(36) NOT NULL, 
	actor_user_id VARCHAR(36) NOT NULL, 
	thread_id VARCHAR(36) NOT NULL, 
	user_message_id VARCHAR(36) NOT NULL, 
	assistant_message_id VARCHAR(36) NOT NULL, 
	request_id VARCHAR(36) NOT NULL, 
	request_sha256 VARCHAR(64) NOT NULL, 
	retry_of_id VARCHAR(36), 
	attempt_number INTEGER NOT NULL, 
	state VARCHAR(24) NOT NULL, 
	version BIGINT NOT NULL, 
	context_version BIGINT DEFAULT 0 NOT NULL, 
	checkpoint_id VARCHAR(36), 
	anchor_leaf_id VARCHAR(36), 
	policy JSONB NOT NULL, 
	deadline_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	cancel_requested_at TIMESTAMP WITH TIME ZONE, 
	error_code VARCHAR(128), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	lease_token_hash VARCHAR(64), 
	lease_expires_at TIMESTAMP WITH TIME ZONE, 
	worker_id VARCHAR(128), 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, id), 
	UNIQUE (assistant_message_id), 
	UNIQUE (workspace_id, actor_user_id, request_id), 
	UNIQUE (retry_of_id), 
	CONSTRAINT ck_chat_memory_versions CHECK (version >= 1 AND context_version >= 0 AND attempt_number >= 1), 
	CONSTRAINT ck_chat_memory_state CHECK (state IN ('prepared','running','waiting_context','succeeded','failed','cancel_requested','cancelled','outcome_unknown')), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT, 
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE RESTRICT, 
	FOREIGN KEY(thread_id) REFERENCES chat_threads (id) ON DELETE RESTRICT, 
	FOREIGN KEY(user_message_id) REFERENCES chat_messages (id) ON DELETE RESTRICT, 
	FOREIGN KEY(assistant_message_id) REFERENCES chat_messages (id) ON DELETE RESTRICT, 
	FOREIGN KEY(retry_of_id) REFERENCES chat_memory_executions (id) ON DELETE RESTRICT, 
	FOREIGN KEY(anchor_leaf_id) REFERENCES chat_messages (id) ON DELETE RESTRICT
)""",
    r"""CREATE TABLE memory_calls (
	id VARCHAR(36) NOT NULL, 
	workspace_id VARCHAR(36) NOT NULL, 
	actor_user_id VARCHAR(36) NOT NULL, 
	chat_execution_id VARCHAR(36), 
	research_attempt_id VARCHAR(36), 
	purpose VARCHAR(24) NOT NULL, 
	logical_key VARCHAR(160) NOT NULL, 
	ordinal INTEGER NOT NULL, 
	parent_call_id VARCHAR(36), 
	native_provider_call_id VARCHAR(36), 
	native_tool_call_id VARCHAR(36), 
	research_budget_ledger_id VARCHAR(36), 
	provider_tool_call_id VARCHAR(255), 
	state VARCHAR(24) NOT NULL, 
	context_version BIGINT NOT NULL, 
	checkpoint_id VARCHAR(36), 
	input_manifest JSONB NOT NULL, 
	request_object_key VARCHAR(1024), 
	request_sha256 VARCHAR(64) NOT NULL, 
	result_object_key VARCHAR(1024), 
	result_sha256 VARCHAR(64), 
	result_state VARCHAR(16) NOT NULL, 
	result_manifest JSONB, 
	result_tokens BIGINT, 
	policy_fingerprint VARCHAR(64) NOT NULL, 
	reserved_input BIGINT NOT NULL, 
	reserved_output BIGINT NOT NULL, 
	actual_input BIGINT, 
	actual_output BIGINT, 
	usage_source VARCHAR(16) NOT NULL, 
	cost_microunits BIGINT, 
	reservation_state VARCHAR(16) NOT NULL, 
	no_progress_boundary_sha256 VARCHAR(64), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	sent_at TIMESTAMP WITH TIME ZONE, 
	settled_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, id), 
	UNIQUE (native_provider_call_id), 
	FOREIGN KEY(workspace_id, chat_execution_id) REFERENCES chat_memory_executions (workspace_id, id), 
	FOREIGN KEY(workspace_id, parent_call_id) REFERENCES memory_calls (workspace_id, id), 
	CONSTRAINT ck_memory_call_owner CHECK ((chat_execution_id IS NULL) <> (research_attempt_id IS NULL)), 
	CONSTRAINT ck_memory_call_purpose CHECK (purpose IN ('main','compact_chunk','compact_merge','tool_group','read_source')), 
	CONSTRAINT ck_memory_call_state CHECK (state IN ('reserved','sent','succeeded','failed','cancelled','outcome_unknown') AND result_state IN ('absent','valid','invalidated','erased') AND reservation_state IN ('reserved','settled') AND usage_source IN ('reported','estimated','unknown')), 
	CONSTRAINT ck_memory_call_counts CHECK (ordinal >= 0 AND context_version >= 0 AND reserved_input >= 0 AND reserved_output >= 0 AND actual_input >= 0 AND actual_output >= 0 AND result_tokens >= 0), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT, 
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE RESTRICT, 
	FOREIGN KEY(research_attempt_id) REFERENCES research_step_attempts (id) ON DELETE RESTRICT, 
	FOREIGN KEY(native_provider_call_id) REFERENCES research_provider_calls (id) ON DELETE RESTRICT, 
	FOREIGN KEY(native_tool_call_id) REFERENCES research_tool_calls (id) ON DELETE RESTRICT, 
	FOREIGN KEY(research_budget_ledger_id) REFERENCES research_budget_ledgers (id) ON DELETE RESTRICT
)""",
    r"""CREATE UNIQUE INDEX uq_memory_call_chat_execution_id ON memory_calls (chat_execution_id, logical_key) WHERE chat_execution_id IS NOT NULL""",
    r"""CREATE UNIQUE INDEX uq_memory_call_research_attempt_id ON memory_calls (research_attempt_id, logical_key) WHERE research_attempt_id IS NOT NULL""",
    r"""CREATE TABLE task_memory_snapshots (
	id VARCHAR(36) NOT NULL, 
	workspace_id VARCHAR(36) NOT NULL, 
	owner_user_id VARCHAR(36) NOT NULL, 
	audience VARCHAR(16) NOT NULL, 
	thread_id VARCHAR(36), 
	run_id VARCHAR(36), 
	step_id VARCHAR(36), 
	attempt_id VARCHAR(36), 
	branch_key VARCHAR(128), 
	anchor_leaf_id VARCHAR(36), 
	parent_snapshot_id VARCHAR(36), 
	version BIGINT NOT NULL, 
	context_version BIGINT NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	summary JSONB, 
	schema_version VARCHAR(32) NOT NULL, 
	policy_snapshot JSONB NOT NULL, 
	provider_fingerprint VARCHAR(64) NOT NULL, 
	counter_version VARCHAR(64) NOT NULL, 
	input_sha256 VARCHAR(64) NOT NULL, 
	manifest_sha256 VARCHAR(64) NOT NULL, 
	operation_key VARCHAR(64) NOT NULL, 
	before_tokens BIGINT NOT NULL, 
	after_tokens BIGINT NOT NULL, 
	count_source VARCHAR(16) NOT NULL, 
	generation_call_id VARCHAR(36), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	invalidated_at TIMESTAMP WITH TIME ZONE, 
	erased_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, id), 
	UNIQUE (operation_key), 
	FOREIGN KEY(workspace_id, parent_snapshot_id) REFERENCES task_memory_snapshots (workspace_id, id), 
	FOREIGN KEY(workspace_id, generation_call_id) REFERENCES memory_calls (workspace_id, id), 
	CONSTRAINT ck_task_snapshot_values CHECK (audience = 'workspace' AND version >= 1 AND context_version >= 1 AND before_tokens >= 0 AND after_tokens >= 0 AND count_source IN ('exact','estimated')), 
	CONSTRAINT ck_task_snapshot_owner CHECK ((thread_id IS NOT NULL AND run_id IS NULL AND step_id IS NULL AND attempt_id IS NULL AND branch_key IS NULL) OR (thread_id IS NULL AND anchor_leaf_id IS NULL AND run_id IS NOT NULL AND step_id IS NOT NULL AND attempt_id IS NOT NULL)), 
	CONSTRAINT ck_task_snapshot_payload CHECK ((status = 'committed' AND summary IS NOT NULL AND erased_at IS NULL) OR (status = 'invalidated' AND erased_at IS NULL) OR (status = 'erased' AND summary IS NULL AND erased_at IS NOT NULL)), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT, 
	FOREIGN KEY(owner_user_id) REFERENCES users (id) ON DELETE RESTRICT, 
	FOREIGN KEY(thread_id) REFERENCES chat_threads (id) ON DELETE RESTRICT, 
	FOREIGN KEY(run_id) REFERENCES research_runs (id) ON DELETE RESTRICT, 
	FOREIGN KEY(step_id) REFERENCES research_steps (id) ON DELETE RESTRICT, 
	FOREIGN KEY(attempt_id) REFERENCES research_step_attempts (id) ON DELETE RESTRICT, 
	FOREIGN KEY(anchor_leaf_id) REFERENCES chat_messages (id) ON DELETE RESTRICT
)""",
    r"""CREATE TABLE task_memory_coverage (
	snapshot_id VARCHAR(36) NOT NULL, 
	ordinal INTEGER NOT NULL, 
	unit_key VARCHAR(160) NOT NULL, 
	source_id VARCHAR(36), 
	tool_group_id VARCHAR(36), 
	source_version BIGINT, 
	parent_message_id VARCHAR(36), 
	PRIMARY KEY (snapshot_id, ordinal), 
	UNIQUE (snapshot_id, unit_key), 
	CONSTRAINT ck_task_coverage_unit CHECK (ordinal >= 0 AND ((source_id IS NOT NULL AND source_version IS NOT NULL AND source_version >= 1 AND tool_group_id IS NULL) OR (source_id IS NULL AND source_version IS NULL AND tool_group_id IS NOT NULL))), 
	FOREIGN KEY(snapshot_id) REFERENCES task_memory_snapshots (id) ON DELETE RESTRICT, 
	FOREIGN KEY(source_id) REFERENCES memory_sources (id) ON DELETE RESTRICT, 
	FOREIGN KEY(tool_group_id) REFERENCES memory_calls (id) ON DELETE RESTRICT
)""",
    r"""ALTER TABLE memory_uses ADD COLUMN consumer_snapshot_id VARCHAR(36)""",
    r"""ALTER TABLE memory_uses ADD COLUMN consumer_call_id VARCHAR(36)""",
    r"""ALTER TABLE memory_uses ADD COLUMN consumer_call_part VARCHAR(8)""",
    r"""ALTER TABLE memory_uses ADD COLUMN used_snapshot_id VARCHAR(36)""",
    r"""ALTER TABLE memory_uses ADD COLUMN used_tool_call_id VARCHAR(36)""",
    r"""ALTER TABLE memory_uses ADD CONSTRAINT ck_memory_use CHECK (((consumer_call_id IS NULL AND consumer_call_part IS NULL) OR (consumer_call_id IS NOT NULL AND consumer_call_part IN ('input','result'))) AND ((consumer_revision_id IS NOT NULL AND source_id IS NOT NULL AND use_mode = 'support' AND relation IN ('supports','confirmation')) OR (consumer_revision_id IS NULL AND use_mode IN ('support','context') AND relation IN ('supports','confirmation','context','contradicts'))) AND length(atom_key) > 0 AND length(support_group) > 0)""",
    r"""ALTER TABLE memory_uses ADD CONSTRAINT ck_memory_use_targets CHECK ((CASE WHEN consumer_revision_id IS NULL THEN 0 ELSE 1 END + CASE WHEN consumer_snapshot_id IS NULL THEN 0 ELSE 1 END + CASE WHEN consumer_call_id IS NULL THEN 0 ELSE 1 END) = 1 AND (CASE WHEN source_id IS NULL THEN 0 ELSE 1 END + CASE WHEN used_snapshot_id IS NULL THEN 0 ELSE 1 END + CASE WHEN used_tool_call_id IS NULL THEN 0 ELSE 1 END) = 1)""",
    r"""ALTER TABLE memory_uses ADD FOREIGN KEY(workspace_id, consumer_call_id) REFERENCES memory_calls (workspace_id, id)""",
    r"""ALTER TABLE memory_uses ADD FOREIGN KEY(workspace_id, consumer_snapshot_id) REFERENCES task_memory_snapshots (workspace_id, id)""",
    r"""ALTER TABLE memory_uses ADD FOREIGN KEY(workspace_id, used_snapshot_id) REFERENCES task_memory_snapshots (workspace_id, id)""",
    r"""ALTER TABLE memory_uses ADD FOREIGN KEY(workspace_id, used_tool_call_id) REFERENCES memory_calls (workspace_id, id)""",
    r"""CREATE INDEX ix_memory_use_consumer_call_id ON memory_uses (consumer_call_id)""",
    r"""CREATE INDEX ix_memory_use_consumer_snapshot_id ON memory_uses (consumer_snapshot_id)""",
    r"""CREATE INDEX ix_memory_use_used_snapshot_id ON memory_uses (used_snapshot_id)""",
    r"""CREATE INDEX ix_memory_use_used_tool_call_id ON memory_uses (used_tool_call_id)""",
    r"""CREATE UNIQUE INDEX uq_use_call_id_source_id ON memory_uses (consumer_call_id, source_id, atom_key, support_group, consumer_call_part) WHERE consumer_call_id IS NOT NULL AND source_id IS NOT NULL""",
    r"""CREATE UNIQUE INDEX uq_use_call_id_used_snapshot_id ON memory_uses (consumer_call_id, used_snapshot_id, atom_key, support_group, consumer_call_part) WHERE consumer_call_id IS NOT NULL AND used_snapshot_id IS NOT NULL""",
    r"""CREATE UNIQUE INDEX uq_use_call_id_used_tool_call_id ON memory_uses (consumer_call_id, used_tool_call_id, atom_key, support_group, consumer_call_part) WHERE consumer_call_id IS NOT NULL AND used_tool_call_id IS NOT NULL""",
    r"""CREATE UNIQUE INDEX uq_use_snapshot_id_source_id ON memory_uses (consumer_snapshot_id, source_id, atom_key, support_group) WHERE consumer_snapshot_id IS NOT NULL AND source_id IS NOT NULL""",
    r"""CREATE UNIQUE INDEX uq_use_snapshot_id_used_snapshot_id ON memory_uses (consumer_snapshot_id, used_snapshot_id, atom_key, support_group) WHERE consumer_snapshot_id IS NOT NULL AND used_snapshot_id IS NOT NULL""",
    r"""CREATE UNIQUE INDEX uq_use_snapshot_id_used_tool_call_id ON memory_uses (consumer_snapshot_id, used_tool_call_id, atom_key, support_group) WHERE consumer_snapshot_id IS NOT NULL AND used_tool_call_id IS NOT NULL""",
    r"""ALTER TABLE chat_memory_executions ADD CONSTRAINT fk_chat_memory_checkpoint FOREIGN KEY(workspace_id, checkpoint_id) REFERENCES task_memory_snapshots (workspace_id, id)""",
    r"""ALTER TABLE memory_calls ADD CONSTRAINT fk_memory_call_checkpoint FOREIGN KEY(workspace_id, checkpoint_id) REFERENCES task_memory_snapshots (workspace_id, id)""",
    r"""ALTER TABLE research_step_attempts ADD COLUMN memory_context_version BIGINT DEFAULT 0 NOT NULL CONSTRAINT ck_research_attempt_memory_version CHECK (memory_context_version >= 0)""",
    r"""ALTER TABLE research_step_attempts ADD COLUMN memory_checkpoint_id VARCHAR(36)""",
    r"""ALTER TABLE research_step_attempts ADD CONSTRAINT fk_research_attempt_memory_checkpoint FOREIGN KEY(memory_checkpoint_id) REFERENCES task_memory_snapshots (id)""",
    r"""CREATE OR REPLACE FUNCTION memory_check_revision_support(rid varchar) RETURNS void LANGUAGE plpgsql AS $$
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
   WHERE u.consumer_revision_id = rid AND (s.owner_user_id IS DISTINCT FROM owner_id OR s.workspace_id IS DISTINCT FROM r.workspace_id OR s.kind <> 'memory_instruction' OR s.audience <> 'private')
 ) OR NOT EXISTS (
   SELECT 1 FROM memory_instructions i WHERE i.id = r.instruction_id
   AND i.actor_user_id = owner_id AND i.workspace_id = r.workspace_id
 ) THEN RAISE EXCEPTION 'memory_revision_support_required'; END IF;
 IF r.erased_at IS NULL AND r.conditions->>'effectiveFrom' IS NOT NULL THEN
   PERFORM (r.conditions->>'effectiveFrom')::timestamptz;
 END IF;
END $$;""",
)

ORIGINAL_CHECKS = {'ck_source_identity': "CONSTRAINT ck_source_identity CHECK (kind = 'memory_instruction' AND native_id = instruction_id AND source_version >= 1 AND audience = 'private' AND owner_user_id = actor_user_id)", 'ck_source_native_version': "CONSTRAINT ck_source_native_version CHECK (jsonb_typeof(native_version) = 'object' AND native_version ?& ARRAY['instructionId','requestId'] AND (native_version - ARRAY['instructionId','requestId']) = '{}'::jsonb AND native_version->>'instructionId' = instruction_id AND jsonb_typeof(native_version->'requestId') = 'string')", 'ck_memory_use': "CONSTRAINT ck_memory_use CHECK (use_mode = 'support' AND relation IN ('supports','confirmation') AND length(atom_key) > 0 AND length(support_group) > 0)"}


CONSISTENCY = r"""
CREATE FUNCTION compaction_chat_ancestry(eid varchar, actor varchar, wid varchar) RETURNS varchar[] LANGUAGE plpgsql STABLE AS $$
DECLARE e chat_memory_executions; t chat_threads; u record; assistant record; valid_chain boolean; chain_ids varchar[];
BEGIN
 SELECT * INTO e FROM chat_memory_executions WHERE id=eid;
 IF NOT FOUND OR e.workspace_id IS DISTINCT FROM wid OR e.actor_user_id IS DISTINCT FROM actor OR e.state NOT IN ('prepared','running','waiting_context') OR e.cancel_requested_at IS NOT NULL THEN RETURN NULL; END IF;
 SELECT * INTO t FROM chat_threads WHERE id=e.thread_id;
 IF NOT FOUND OR t.workspace_id IS DISTINCT FROM e.workspace_id OR t.archived_at IS NOT NULL OR t.active_message_id IS DISTINCT FROM e.anchor_leaf_id THEN RETURN NULL; END IF;
 SELECT id,workspace_id,thread_id,role,status,parent_message_id INTO u FROM chat_messages WHERE id=e.user_message_id;
 SELECT id,workspace_id,thread_id,role,status,parent_message_id INTO assistant FROM chat_messages WHERE id=e.assistant_message_id;
 IF u.id IS NULL OR assistant.id IS NULL OR u.workspace_id IS DISTINCT FROM e.workspace_id OR assistant.workspace_id IS DISTINCT FROM e.workspace_id OR u.thread_id IS DISTINCT FROM e.thread_id OR assistant.thread_id IS DISTINCT FROM e.thread_id OR u.role IS DISTINCT FROM 'user' OR u.status IS DISTINCT FROM 'completed' OR assistant.role IS DISTINCT FROM 'assistant' OR assistant.status IS DISTINCT FROM 'streaming' OR assistant.parent_message_id IS DISTINCT FROM u.id THEN RETURN NULL; END IF;
 WITH RECURSIVE ancestry AS (
 SELECT m.id,m.workspace_id,m.thread_id,m.role,m.status,m.parent_message_id,ARRAY[m.id]::varchar[] AS visited,1 AS depth,false AS cycle
 FROM chat_messages m WHERE m.id=u.id
 UNION ALL
 SELECT m.id,m.workspace_id,m.thread_id,m.role,m.status,m.parent_message_id,a.visited||m.id,a.depth+1,m.id=ANY(a.visited)
 FROM ancestry a LEFT JOIN chat_messages m ON m.id=a.parent_message_id
 WHERE a.parent_message_id IS NOT NULL AND NOT a.cycle AND a.depth<1025
 )
 SELECT COALESCE(bool_and(id IS NOT NULL AND workspace_id=e.workspace_id AND thread_id=e.thread_id AND role IN ('user','assistant') AND status IN ('completed','failed') AND NOT cycle AND depth<=1024),false)
 AND COALESCE(bool_or(parent_message_id IS NULL AND id IS NOT NULL),false),array_agg(id ORDER BY depth)
 INTO valid_chain,chain_ids FROM ancestry;
 IF valid_chain THEN RETURN chain_ids; END IF;
 RETURN NULL;
END $$;
CREATE FUNCTION compaction_source_scope(x memory_sources, eid varchar, aid varchar) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
DECLARE e chat_memory_executions; chain_ids varchar[];
BEGIN
 IF (eid IS NULL)=(aid IS NULL) OR x.audience IS DISTINCT FROM 'workspace' OR x.state IS DISTINCT FROM 'current' OR x.content_sha256 IS NULL THEN RETURN false; END IF;
 IF aid IS NOT NULL THEN
 RETURN x.kind='research_evidence' AND EXISTS(SELECT 1 FROM research_evidence_handles h JOIN research_step_attempts a ON a.step_id=h.owner_step_id JOIN research_steps st ON st.id=a.step_id WHERE a.id=aid AND h.id=x.native_id AND h.workspace_id=x.workspace_id AND a.workspace_id=x.workspace_id AND h.run_id=st.run_id AND h.execution_snapshot_id=st.execution_snapshot_id);
 END IF;
 SELECT * INTO e FROM chat_memory_executions WHERE id=eid;
 IF NOT FOUND OR x.workspace_id IS DISTINCT FROM e.workspace_id OR x.kind IS DISTINCT FROM 'chat_message' THEN RETURN false; END IF;
 chain_ids:=compaction_chat_ancestry(eid,e.actor_user_id,e.workspace_id);
 RETURN chain_ids IS NOT NULL AND x.native_id=ANY(chain_ids) AND EXISTS(SELECT 1 FROM chat_messages m WHERE m.id=x.native_id AND x.workspace_id=m.workspace_id AND x.source_version=m.compaction_revision
 AND x.native_version->>'messageId'=m.id
 AND (x.native_version->>'parentMessageId') IS NOT DISTINCT FROM m.parent_message_id
 AND x.native_version->>'role'=m.role AND x.native_version->>'status'=m.status
 AND x.native_version->>'compactionRevision'=m.compaction_revision::text
 AND x.native_version->>'contentSha256'=x.content_sha256);
END $$;
CREATE FUNCTION compaction_chat_live(eid varchar, actor varchar, wid varchar) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT compaction_chat_ancestry(eid,actor,wid) IS NOT NULL
$$;
CREATE FUNCTION compaction_tool_scope(c memory_calls, eid varchar, aid varchar, actor varchar) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
DECLARE raw jsonb; x memory_sources;
BEGIN
 IF (eid IS NULL)=(aid IS NULL) OR c.actor_user_id IS DISTINCT FROM actor OR c.purpose IS DISTINCT FROM 'tool_group' OR c.state IS DISTINCT FROM 'succeeded' OR c.result_state IS DISTINCT FROM 'valid' THEN RETURN false; END IF;
 IF eid IS NOT NULL THEN
 IF compaction_chat_live(eid,actor,c.workspace_id) IS NOT TRUE OR c.chat_execution_id IS DISTINCT FROM eid OR c.research_attempt_id IS NOT NULL OR NOT EXISTS(SELECT 1 FROM chat_memory_executions e WHERE e.id=eid AND e.actor_user_id=actor AND e.workspace_id=c.workspace_id) THEN RETURN false; END IF;
 ELSE IF c.research_attempt_id IS DISTINCT FROM aid OR c.chat_execution_id IS NOT NULL OR NOT EXISTS(SELECT 1 FROM research_step_attempts a WHERE a.id=aid AND a.workspace_id=c.workspace_id) THEN RETURN false; END IF; END IF;
 IF jsonb_typeof(c.result_manifest->'sources') IS DISTINCT FROM 'array' OR jsonb_array_length(c.result_manifest->'sources')>2048 OR c.result_manifest->'complete' IS DISTINCT FROM 'true'::jsonb THEN RETURN false; END IF;
 FOR raw IN SELECT value FROM jsonb_array_elements(c.result_manifest->'sources') LOOP
 IF jsonb_typeof(raw) IS DISTINCT FROM 'object' OR NOT (raw ?& ARRAY['source_id','version','sha256']) OR (raw-ARRAY['source_id','version','sha256'])<>'{}'::jsonb THEN RETURN false; END IF;
 SELECT * INTO x FROM memory_sources WHERE id=raw->>'source_id';
 IF NOT FOUND OR compaction_source_scope(x,eid,aid) IS NOT TRUE OR x.source_version::text IS DISTINCT FROM raw->>'version' OR x.content_sha256 IS DISTINCT FROM raw->>'sha256' THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
END $$;
CREATE FUNCTION compaction_snapshot_chat_owner(sid varchar) RETURNS varchar LANGUAGE sql STABLE AS $$
 SELECT c.chat_execution_id FROM task_memory_snapshots s JOIN memory_calls c ON c.id=s.generation_call_id JOIN chat_memory_executions e ON e.id=c.chat_execution_id
 WHERE s.id=sid AND s.thread_id IS NOT NULL AND s.attempt_id IS NULL AND c.research_attempt_id IS NULL AND c.purpose IN ('compact_chunk','compact_merge') AND c.workspace_id=s.workspace_id AND c.actor_user_id=s.owner_user_id AND e.workspace_id=s.workspace_id AND e.actor_user_id=s.owner_user_id AND e.thread_id=s.thread_id
$$;
CREATE FUNCTION compaction_snapshot_live(sid varchar, eid varchar, aid varchar) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
DECLARE s task_memory_snapshots; c memory_calls; chain_ids varchar[];
BEGIN
 IF (eid IS NULL)=(aid IS NULL) THEN RETURN false; END IF;
 SELECT * INTO s FROM task_memory_snapshots WHERE id=sid;
 IF NOT FOUND OR s.status<>'committed' THEN RETURN false; END IF;
 IF eid IS NOT NULL THEN
 IF compaction_snapshot_chat_owner(sid) IS DISTINCT FROM eid OR s.attempt_id IS NOT NULL THEN RETURN false; END IF;
 chain_ids:=compaction_chat_ancestry(eid,s.owner_user_id,s.workspace_id);
 IF chain_ids IS NULL THEN RETURN false; END IF;
 SELECT * INTO c FROM memory_calls WHERE id=s.generation_call_id;
 IF c.state IS DISTINCT FROM 'succeeded' OR c.result_state IS DISTINCT FROM 'valid' THEN RETURN false; END IF;
 ELSE IF s.attempt_id IS DISTINCT FROM aid OR s.thread_id IS NOT NULL THEN RETURN false; END IF; END IF;
 IF (SELECT count(*) FROM task_memory_coverage WHERE snapshot_id=sid) NOT BETWEEN 1 AND 2048 THEN RETURN false; END IF;
 RETURN NOT EXISTS(SELECT 1 FROM task_memory_coverage cv LEFT JOIN memory_sources x ON x.id=cv.source_id LEFT JOIN chat_messages m ON eid IS NOT NULL AND m.id=x.native_id LEFT JOIN memory_calls g ON g.id=cv.tool_group_id WHERE cv.snapshot_id=sid AND
 (cv.source_id IS NOT NULL AND (CASE WHEN eid IS NOT NULL THEN (x.kind='chat_message' AND x.audience='workspace' AND x.state='current' AND x.content_sha256 IS NOT NULL AND x.native_id=ANY(chain_ids) AND x.workspace_id=m.workspace_id AND x.source_version=m.compaction_revision
 AND x.native_version->>'messageId'=m.id
 AND (x.native_version->>'parentMessageId') IS NOT DISTINCT FROM m.parent_message_id
 AND x.native_version->>'role'=m.role AND x.native_version->>'status'=m.status
 AND x.native_version->>'compactionRevision'=m.compaction_revision::text
 AND x.native_version->>'contentSha256'=x.content_sha256 AND cv.parent_message_id IS NOT DISTINCT FROM m.parent_message_id) ELSE compaction_source_scope(x,NULL,aid) END IS NOT TRUE OR x.workspace_id IS DISTINCT FROM s.workspace_id OR x.source_version IS DISTINCT FROM cv.source_version)
 OR cv.tool_group_id IS NOT NULL AND (compaction_tool_scope(g,eid,aid,s.owner_user_id) IS NOT TRUE OR g.workspace_id IS DISTINCT FROM s.workspace_id)));
END $$;
CREATE FUNCTION compaction_snapshot_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW) - ARRAY['status','summary','invalidated_at','erased_at']) IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','summary','invalidated_at','erased_at'])
 OR (NEW.summary IS DISTINCT FROM OLD.summary AND NOT (NEW.status='erased' AND NEW.summary IS NULL AND NEW.erased_at IS NOT NULL))
 OR (OLD.status='erased' AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD))
 OR (OLD.status='invalidated' AND NEW.status='committed') THEN RAISE EXCEPTION 'immutable_compaction_snapshot'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER compaction_snapshot_immutable BEFORE UPDATE ON task_memory_snapshots FOR EACH ROW EXECUTE FUNCTION compaction_snapshot_immutable();
CREATE FUNCTION compaction_coverage_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE sid varchar;
BEGIN
 sid:=CASE WHEN TG_OP='DELETE' THEN OLD.snapshot_id ELSE NEW.snapshot_id END;
 IF TG_OP<>'INSERT' AND EXISTS(SELECT 1 FROM task_memory_snapshots WHERE id=sid) THEN RAISE EXCEPTION 'immutable_compaction_coverage'; END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE TRIGGER compaction_coverage_immutable BEFORE INSERT OR UPDATE OR DELETE ON task_memory_coverage FOR EACH ROW EXECUTE FUNCTION compaction_coverage_immutable();
CREATE FUNCTION compaction_snapshot_complete() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE sid varchar; s task_memory_snapshots; n bigint; hi bigint; lo bigint; p task_memory_snapshots; manifest text; eid varchar; gc memory_calls;
BEGIN
 IF TG_TABLE_NAME='task_memory_snapshots' THEN sid:=NEW.id; ELSE sid:=COALESCE(NEW.snapshot_id,OLD.snapshot_id); END IF;
 SELECT * INTO s FROM task_memory_snapshots WHERE id=sid;
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT count(*),min(ordinal),max(ordinal) INTO n,lo,hi FROM task_memory_coverage WHERE snapshot_id=sid;
 IF n=0 OR lo<>0 OR hi<>n-1 THEN RAISE EXCEPTION 'compaction_coverage_incomplete'; END IF;
 eid:=compaction_snapshot_chat_owner(sid);
 IF s.thread_id IS NOT NULL THEN
 IF eid IS NULL THEN RAISE EXCEPTION 'compaction_generation_owner_required'; END IF;
 SELECT * INTO gc FROM memory_calls WHERE id=s.generation_call_id;
 IF gc.state IS DISTINCT FROM 'succeeded' OR gc.result_state IS DISTINCT FROM 'valid' OR gc.context_version+1<>s.context_version OR gc.input_manifest->'capture'->'owner'->>'kind' IS DISTINCT FROM 'chat' OR gc.input_manifest->'capture'->'owner'->>'owner_id' IS DISTINCT FROM eid OR gc.input_manifest->'capture'->>'context_version' IS DISTINCT FROM gc.context_version::text OR gc.input_manifest->'capture'->'owner'->>'workspace_id' IS DISTINCT FROM s.workspace_id OR gc.input_manifest->'capture'->'owner'->>'actor_user_id' IS DISTINCT FROM s.owner_user_id OR NOT EXISTS(SELECT 1 FROM chat_memory_executions e WHERE e.id=eid AND e.anchor_leaf_id IS NOT DISTINCT FROM s.anchor_leaf_id) THEN RAISE EXCEPTION 'compaction_generation_owner_required'; END IF;
 END IF;
 IF compaction_snapshot_live(sid,eid,s.attempt_id) IS NOT TRUE THEN RAISE EXCEPTION 'compaction_coverage_scope'; END IF;
 SELECT '['||COALESCE(string_agg(
   '{"key":'||to_json(c.unit_key)::text||
   ',"parent_message_id":'||COALESCE(to_json(c.parent_message_id)::text,'null')||
   ',"source":'||CASE WHEN c.source_id IS NULL THEN 'null' ELSE
     '{"sha256":'||to_json(x.content_sha256)::text||',"source_id":'||to_json(c.source_id)::text||',"version":'||c.source_version::text||'}' END||
   ',"tool_group_id":'||COALESCE(to_json(c.tool_group_id)::text,'null')||'}',',' ORDER BY c.ordinal),'')||']'
 INTO manifest FROM task_memory_coverage c LEFT JOIN memory_sources x ON x.id=c.source_id WHERE c.snapshot_id=sid;
 IF encode(sha256(convert_to(manifest,'UTF8')),'hex')<>s.manifest_sha256 THEN RAISE EXCEPTION 'compaction_manifest_mismatch'; END IF;
 IF s.parent_snapshot_id IS NOT NULL THEN
 SELECT * INTO p FROM task_memory_snapshots WHERE id=s.parent_snapshot_id;
 IF p.workspace_id<>s.workspace_id OR p.owner_user_id<>s.owner_user_id OR p.thread_id IS DISTINCT FROM s.thread_id OR p.attempt_id IS DISTINCT FROM s.attempt_id OR p.version+1<>s.version THEN RAISE EXCEPTION 'compaction_parent_invalid'; END IF;
 IF s.thread_id IS NOT NULL AND compaction_snapshot_chat_owner(p.id) IS DISTINCT FROM eid THEN RAISE EXCEPTION 'compaction_parent_invalid'; END IF;
 IF EXISTS(SELECT 1 FROM task_memory_coverage prior_c LEFT JOIN task_memory_coverage next_c ON next_c.snapshot_id=s.id AND next_c.ordinal=prior_c.ordinal WHERE prior_c.snapshot_id=p.id AND (next_c.snapshot_id IS NULL OR ROW(next_c.unit_key,next_c.source_id,next_c.source_version,next_c.tool_group_id,next_c.parent_message_id) IS DISTINCT FROM ROW(prior_c.unit_key,prior_c.source_id,prior_c.source_version,prior_c.tool_group_id,prior_c.parent_message_id)))
 OR n<=(SELECT count(*) FROM task_memory_coverage WHERE snapshot_id=p.id) THEN RAISE EXCEPTION 'compaction_coverage_regression'; END IF;
 END IF;
 IF TG_TABLE_NAME='task_memory_snapshots' AND TG_OP='INSERT' THEN
 IF s.thread_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM chat_memory_executions e WHERE e.id=eid AND e.checkpoint_id=s.id AND e.workspace_id=s.workspace_id AND e.actor_user_id=s.owner_user_id AND e.thread_id=s.thread_id AND e.context_version=s.context_version)
 OR s.attempt_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM research_step_attempts a JOIN research_steps st ON st.id=a.step_id JOIN research_runs r ON r.id=st.run_id WHERE a.id=s.attempt_id AND a.memory_checkpoint_id=s.id AND a.memory_context_version=s.context_version AND a.workspace_id=s.workspace_id AND st.id=s.step_id AND r.id=s.run_id AND r.created_by_user_id=s.owner_user_id) THEN RAISE EXCEPTION 'compaction_native_pointer_required'; END IF;
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER compaction_snapshot_complete AFTER INSERT ON task_memory_snapshots DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION compaction_snapshot_complete();
CREATE CONSTRAINT TRIGGER compaction_coverage_complete AFTER INSERT OR UPDATE OR DELETE ON task_memory_coverage DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION compaction_snapshot_complete();
CREATE FUNCTION compaction_owner_pointer() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE sid varchar; v bigint; s task_memory_snapshots;
BEGIN
 IF TG_TABLE_NAME='chat_memory_executions' THEN sid:=NEW.checkpoint_id; v:=NEW.context_version;
 ELSE sid:=NEW.memory_checkpoint_id; v:=NEW.memory_context_version; END IF;
 IF TG_OP='UPDATE' THEN
 IF TG_TABLE_NAME='chat_memory_executions' THEN
 IF NEW.context_version<OLD.context_version THEN RAISE EXCEPTION 'compaction_context_regression'; END IF;
 ELSE IF NEW.memory_context_version<OLD.memory_context_version THEN RAISE EXCEPTION 'compaction_context_regression'; END IF; END IF;
 END IF;
 IF sid IS NULL THEN IF v<>0 THEN RAISE EXCEPTION 'compaction_pointer_missing'; END IF; RETURN NULL; END IF;
 SELECT * INTO s FROM task_memory_snapshots WHERE id=sid;
 IF NOT FOUND OR s.workspace_id<>NEW.workspace_id OR s.context_version>v THEN RAISE EXCEPTION 'compaction_pointer_invalid'; END IF;
 IF TG_TABLE_NAME='chat_memory_executions' THEN
 IF compaction_snapshot_chat_owner(s.id) IS DISTINCT FROM NEW.id OR s.thread_id IS DISTINCT FROM NEW.thread_id OR s.owner_user_id<>NEW.actor_user_id THEN RAISE EXCEPTION 'compaction_pointer_scope'; END IF;
 ELSE IF s.attempt_id IS DISTINCT FROM NEW.id OR s.step_id IS DISTINCT FROM NEW.step_id THEN RAISE EXCEPTION 'compaction_pointer_scope'; END IF; END IF;
 IF TG_TABLE_NAME='chat_memory_executions' THEN
 IF TG_OP='INSERT' OR NEW.checkpoint_id IS DISTINCT FROM OLD.checkpoint_id THEN
 IF compaction_snapshot_live(s.id,NEW.id,NULL) IS NOT TRUE THEN RAISE EXCEPTION 'compaction_pointer_scope'; END IF;
 END IF;
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER compaction_chat_pointer AFTER INSERT OR UPDATE ON chat_memory_executions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION compaction_owner_pointer();
CREATE CONSTRAINT TRIGGER compaction_research_pointer AFTER INSERT OR UPDATE ON research_step_attempts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION compaction_owner_pointer();
CREATE FUNCTION compaction_use_scope() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE wid varchar; aid varchar; eid varchar; actor varchar; s task_memory_snapshots; c memory_calls; x memory_sources;
BEGIN
 IF NEW.consumer_revision_id IS NOT NULL THEN RETURN NULL; END IF;
 IF NEW.consumer_snapshot_id IS NOT NULL THEN
 SELECT * INTO s FROM task_memory_snapshots WHERE id=NEW.consumer_snapshot_id; actor:=s.owner_user_id; aid:=s.attempt_id; eid:=compaction_snapshot_chat_owner(s.id); wid:=s.workspace_id;
 ELSE
 SELECT * INTO c FROM memory_calls WHERE id=NEW.consumer_call_id; actor:=c.actor_user_id; aid:=c.research_attempt_id; eid:=c.chat_execution_id; wid:=c.workspace_id;
 END IF;
 IF wid IS NULL OR wid IS DISTINCT FROM NEW.workspace_id OR (eid IS NULL)=(aid IS NULL) THEN RAISE EXCEPTION 'compaction_dependency_owner_mismatch'; END IF;
 IF eid IS NOT NULL THEN
 IF compaction_chat_live(eid,actor,wid) IS NOT TRUE THEN RAISE EXCEPTION 'compaction_dependency_owner_mismatch'; END IF;
 ELSE
 IF NOT EXISTS(SELECT 1 FROM research_step_attempts a JOIN research_steps st ON st.id=a.step_id JOIN research_runs r ON r.id=st.run_id WHERE a.id=aid AND a.workspace_id=wid AND r.created_by_user_id=actor) THEN RAISE EXCEPTION 'compaction_dependency_owner_mismatch'; END IF;
 END IF;
 IF NEW.source_id IS NOT NULL THEN
 SELECT * INTO x FROM memory_sources WHERE id=NEW.source_id;
 IF x.workspace_id IS DISTINCT FROM wid OR compaction_source_scope(x,eid,aid) IS NOT TRUE THEN RAISE EXCEPTION 'compaction_private_dependency_forbidden'; END IF;
 END IF;
 IF NEW.used_snapshot_id IS NOT NULL THEN
 SELECT * INTO s FROM task_memory_snapshots WHERE id=NEW.used_snapshot_id;
 IF s.workspace_id IS DISTINCT FROM wid OR s.owner_user_id IS DISTINCT FROM actor OR compaction_snapshot_live(s.id,eid,aid) IS NOT TRUE THEN RAISE EXCEPTION 'compaction_dependency_owner_mismatch'; END IF;
 END IF;
 IF NEW.used_tool_call_id IS NOT NULL THEN
 SELECT * INTO c FROM memory_calls WHERE id=NEW.used_tool_call_id;
 IF c.workspace_id IS DISTINCT FROM wid OR compaction_tool_scope(c,eid,aid,actor) IS NOT TRUE THEN RAISE EXCEPTION 'compaction_dependency_owner_mismatch'; END IF;
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER compaction_use_scope AFTER INSERT OR UPDATE ON memory_uses DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION compaction_use_scope();
CREATE FUNCTION compaction_call_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF ROW(NEW.id,NEW.workspace_id,NEW.actor_user_id,NEW.chat_execution_id,NEW.research_attempt_id,NEW.purpose,NEW.logical_key,NEW.ordinal,NEW.parent_call_id,NEW.native_provider_call_id,NEW.native_tool_call_id,NEW.research_budget_ledger_id,NEW.provider_tool_call_id,NEW.context_version,NEW.checkpoint_id,NEW.input_manifest,NEW.request_sha256,NEW.policy_fingerprint,NEW.reserved_input,NEW.reserved_output,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.workspace_id,OLD.actor_user_id,OLD.chat_execution_id,OLD.research_attempt_id,OLD.purpose,OLD.logical_key,OLD.ordinal,OLD.parent_call_id,OLD.native_provider_call_id,OLD.native_tool_call_id,OLD.research_budget_ledger_id,OLD.provider_tool_call_id,OLD.context_version,OLD.checkpoint_id,OLD.input_manifest,OLD.request_sha256,OLD.policy_fingerprint,OLD.reserved_input,OLD.reserved_output,OLD.created_at)
 OR (OLD.request_object_key IS NOT NULL AND NEW.request_object_key IS DISTINCT FROM OLD.request_object_key)
 OR (OLD.result_state='valid' AND (NEW.result_manifest IS DISTINCT FROM OLD.result_manifest OR NEW.result_sha256 IS DISTINCT FROM OLD.result_sha256) AND NEW.result_state<>'erased')
 OR (OLD.reservation_state='settled' AND (NEW.reservation_state<>'settled' OR ROW(NEW.actual_input,NEW.actual_output,NEW.state) IS DISTINCT FROM ROW(OLD.actual_input,OLD.actual_output,OLD.state))) THEN RAISE EXCEPTION 'compaction_call_immutable'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER compaction_call_identity BEFORE UPDATE ON memory_calls FOR EACH ROW EXECUTE FUNCTION compaction_call_identity();

"""

def upgrade():
    for statement in DDL:
        op.execute(statement)
    op.execute(CONSISTENCY)


def downgrade():
    conn = op.get_bind()
    for table in ("task_memory_snapshots", "memory_calls", "chat_memory_executions"):
        if conn.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM " + table + ")")):
            raise RuntimeError("compaction_data_present")
    if conn.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM memory_sources WHERE kind <> 'memory_instruction')")):
        raise RuntimeError("compaction_data_present")
    for trigger, table in (("compaction_coverage_immutable","task_memory_coverage"),("compaction_use_scope","memory_uses"),("compaction_call_identity","memory_calls"),("compaction_chat_pointer","chat_memory_executions"),("compaction_research_pointer","research_step_attempts"),("compaction_coverage_complete","task_memory_coverage"),("compaction_snapshot_complete","task_memory_snapshots"),("compaction_snapshot_immutable","task_memory_snapshots")):
        op.execute("DROP TRIGGER " + trigger + " ON " + table)
    for function in ("compaction_coverage_immutable","compaction_use_scope","compaction_call_identity","compaction_owner_pointer", "compaction_snapshot_complete", "compaction_snapshot_immutable"):
        op.execute("DROP FUNCTION " + function + "()")
    op.drop_constraint("fk_research_attempt_memory_checkpoint", "research_step_attempts", type_="foreignkey")
    op.drop_column("research_step_attempts", "memory_checkpoint_id")
    op.drop_column("research_step_attempts", "memory_context_version")
    op.drop_constraint("fk_chat_memory_checkpoint", "chat_memory_executions", type_="foreignkey")
    op.drop_constraint("fk_memory_call_checkpoint", "memory_calls", type_="foreignkey")
    op.drop_constraint("ck_memory_use_targets", "memory_uses", type_="check")
    op.drop_constraint("ck_memory_use", "memory_uses", type_="check")
    for name in ("consumer_snapshot_id", "consumer_call_id", "consumer_call_part", "used_snapshot_id", "used_tool_call_id"):
        op.drop_column("memory_uses", name)
    op.execute("DROP FUNCTION compaction_snapshot_live(varchar, varchar, varchar)")
    op.execute("DROP FUNCTION compaction_snapshot_chat_owner(varchar)")
    op.execute("DROP FUNCTION compaction_chat_live(varchar, varchar, varchar)")
    op.execute("DROP FUNCTION compaction_source_scope(memory_sources, varchar, varchar)")
    op.execute("DROP FUNCTION compaction_chat_ancestry(varchar, varchar, varchar)")
    op.execute("DROP FUNCTION compaction_tool_scope(memory_calls, varchar, varchar, varchar)")
    for table in ("task_memory_coverage", "task_memory_snapshots", "memory_calls", "chat_memory_executions"):
        op.drop_table(table)
    for name in ("instruction_id", "actor_user_id", "owner_user_id"):
        op.execute("ALTER TABLE memory_sources ALTER COLUMN " + name + " SET NOT NULL")
    for name in ("consumer_revision_id", "source_id"):
        op.execute("ALTER TABLE memory_uses ALTER COLUMN " + name + " SET NOT NULL")
    for name, clause in ORIGINAL_CHECKS.items():
        table = "memory_sources" if name.startswith("ck_source_") else "memory_uses"
        if name != "ck_memory_use":
            op.drop_constraint(name, table, type_="check")
        op.execute("ALTER TABLE " + table + " ADD " + clause)
    for table in ("chat_messages", "chat_threads"):
        op.execute("DROP TRIGGER " + table + "_compaction_revision ON " + table)
        op.execute("DROP FUNCTION " + table + "_compaction_stamp()")
        op.drop_column(table, "compaction_revision")
    op.execute("DROP SEQUENCE chat_compaction_revision_seq")
