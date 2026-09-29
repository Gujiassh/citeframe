"""One PostgreSQL transaction owns snapshot, exact coverage, uses and native pointer CAS."""
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from citeframe_contracts.compaction import (
    CapturedContext, CheckpointReceipt, ContextOwner, CoverageUnit, SourceReference,
)
from citeframe_persistence.models import (
    ChatMemoryExecution, ChatMessage, ChatThread, MemoryCall, MemorySource, MemoryUse,
    ResearchStepAttempt, TaskMemoryCoverage, TaskMemorySnapshot, User,
)
from .guards import GuardLimits, NativeGuard, body_hash, canonical, digest, lock_one
from .policy import CompactionError
from .sources import native_source, read_registered


def validate_runtime_policy(policy):
    required = {"schemaVersion", "maxCalls", "maxInputTokens", "maxOutputTokens", "maxSummaryCalls",
                "maxEpisodes", "deadlineAt"}
    if (not isinstance(policy, dict) or set(policy) != required or policy["schemaVersion"] != "compaction-policy-v1"
            or any(type(policy[k]) is not int or policy[k] <= 0 for k in required - {"schemaVersion", "deadlineAt"})):
        raise CompactionError("invalid_runtime_policy")
    try:
        deadline = datetime.fromisoformat(policy["deadlineAt"])
        if deadline.utcoffset() is None:
            raise ValueError()
    except (TypeError, ValueError):
        raise CompactionError("invalid_runtime_policy") from None
    return deadline


class CompactionRepository:
    def __init__(self, session_factory, *, clock=None, limits=GuardLimits(), fault=None):
        self.sessions, self.clock, self.limits = session_factory, clock or (lambda: datetime.now(UTC)), limits
        self.fault = fault or (lambda stage: None)

    def transact(self, function):
        for attempt in range(2):
            try:
                with self.sessions() as db:
                    with db.begin():
                        if db.bind.dialect.name != "postgresql" or db.connection().get_isolation_level() != "READ COMMITTED":
                            raise CompactionError("postgresql_read_committed_required")
                        for setting,value in (("transaction_timeout",self.limits.transaction_timeout_ms),
                                              ("statement_timeout",self.limits.statement_timeout_ms),
                                              ("lock_timeout",self.limits.lock_timeout_ms)):
                            db.execute(text("SET LOCAL "+setting+" = "+str(value)))
                        result = function(db)
                    self.fault("after_commit")
                    return result
            except DBAPIError as error:
                code = getattr(error.orig, "sqlstate", None)
                if code not in ("55P03", "57014", "25P04"):
                    raise
                if attempt:
                    raise CompactionError("context_busy") from None
        raise AssertionError("unreachable")

    def guard(self, db, owner, native_provider_call_id=None):
        return NativeGuard(db, owner, self.limits, self.clock(),native_provider_call_id)

    def create_chat(self, owner, *, thread_id, user_message_id, assistant_message_id, request_id,
                    request_sha256, policy, deadline_at, lease_expires_at):
        if owner.kind != "chat" or validate_runtime_policy(policy) != deadline_at:
            raise CompactionError("invalid_chat_owner")
        def create(db):
            # NativeGuard can only operate after owner registration; establish the same initial roots.
            from citeframe_persistence.models import Workspace, WorkspaceMembership
            workspace = lock_one(db, Workspace, owner.workspace_id)
            member = db.scalar(select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == owner.workspace_id,
                WorkspaceMembership.user_id == owner.actor_user_id).with_for_update(nowait=True))
            thread = lock_one(db, ChatThread, thread_id)
            if (workspace is None or workspace.archived_at or member is None or member.role not in ("owner", "member")
                    or thread is None or thread.workspace_id != owner.workspace_id or thread.archived_at):
                raise CompactionError("context_access_denied")
            if lock_one(db, User, owner.actor_user_id) is None:
                raise CompactionError("context_access_denied")
            for id_, role in ((user_message_id, "user"), (assistant_message_id, "assistant")):
                row = db.execute(select(ChatMessage.id,ChatMessage.thread_id,ChatMessage.workspace_id,
                    ChatMessage.role,ChatMessage.status,ChatMessage.parent_message_id).where(ChatMessage.id==id_).with_for_update(nowait=True)).first()
                if (row is None or row.thread_id != thread_id or row.workspace_id != owner.workspace_id or row.role != role
                        or row.status != ("completed" if role=="user" else "streaming")
                        or (role=="assistant" and row.parent_message_id!=user_message_id)):
                    raise CompactionError("invalid_native_message")
            if thread.active_message_id is not None:
                anchor = db.execute(select(ChatMessage.id, ChatMessage.thread_id, ChatMessage.workspace_id)
                    .where(ChatMessage.id == thread.active_message_id).with_for_update(nowait=True)).first()
                if anchor is None or anchor.thread_id != thread.id or anchor.workspace_id != owner.workspace_id:
                    raise CompactionError("invalid_native_anchor")
            existing = lock_one(db, ChatMemoryExecution, owner.owner_id)
            if existing:
                if (existing.actor_user_id != owner.actor_user_id or existing.request_id != request_id
                        or existing.request_sha256 != request_sha256 or existing.policy != policy):
                    raise CompactionError("idempotency_conflict")
                return owner.owner_id
            db.add(ChatMemoryExecution(id=owner.owner_id, workspace_id=owner.workspace_id,
                actor_user_id=owner.actor_user_id, thread_id=thread_id, user_message_id=user_message_id,
                assistant_message_id=assistant_message_id, request_id=request_id, request_sha256=request_sha256,
                retry_of_id=None, attempt_number=1, state="running", version=1, context_version=0,
                checkpoint_id=None, anchor_leaf_id=thread.active_message_id, policy=policy,
                deadline_at=deadline_at, cancel_requested_at=None, error_code=None, created_at=self.clock(),
                finished_at=None, lease_token_hash=owner.lease_token_hash, lease_expires_at=lease_expires_at,
                worker_id="neutral"))
            db.flush()
            return owner.owner_id
        return self.transact(create)

    def register_source(self, owner, kind, native_id):
        def register(db):
            guard = self.guard(db, owner)
            body, version, revision = native_source(guard, kind, native_id)
            if len(body.encode()) > self.limits.max_body_bytes:
                raise CompactionError("context_too_large")
            rows = list(db.scalars(select(MemorySource).where(MemorySource.workspace_id == owner.workspace_id,
                MemorySource.kind == kind, MemorySource.native_id == native_id).order_by(MemorySource.id)
                .with_for_update(nowait=True)))
            for source in rows:
                if source.source_version == revision:
                    if source.state != "current" or source.native_version != version or source.content_sha256 != body_hash(body):
                        raise CompactionError("source_version_changed")
                    return SourceReference(source.id, revision, source.content_sha256)
                if source.state == "current":
                    source.state, source.invalidated_at = "stale", self.clock()
            db.flush()
            id_ = str(uuid4())
            db.add(MemorySource(id=id_, workspace_id=owner.workspace_id, kind=kind, native_id=native_id,
                instruction_id=None, source_version=revision, native_version=version, content_sha256=body_hash(body),
                actor_user_id=None, audience="workspace", owner_user_id=None, state="current",
                created_at=self.clock(), invalidated_at=None))
            db.flush()
            return SourceReference(id_, revision, body_hash(body))
        return self.transact(register)

    def read_source(self, owner, reference, *, start=0, end=None):
        def read(db):
            body, _ = read_registered(self.guard(db, owner), reference)
            stop = len(body) if end is None else end
            if type(start) is not int or type(stop) is not int or not 0 <= start <= stop <= len(body):
                raise CompactionError("invalid_source_range")
            result=body[start:stop]
            if len(result.encode())>self.limits.max_body_bytes:
                raise CompactionError("source_range_too_large")
            return result
        return self.transact(read)

    def _validate_units(self, guard, units):
        if len(units) > 2048 or len({u.key for u in units}) != len(units):
            raise CompactionError("invalid_coverage")
        if len(canonical([asdict(u) for u in units]).encode()) > 131072:
            raise CompactionError("context_too_large")
        owner_column=MemoryCall.chat_execution_id if guard.owner.kind=="chat" else MemoryCall.research_attempt_id
        complete_groups=list(guard.db.scalars(select(MemoryCall.id).where(owner_column==guard.owner.owner_id,
            MemoryCall.purpose=="tool_group",MemoryCall.state=="succeeded",MemoryCall.result_state=="valid")
            .order_by(MemoryCall.ordinal,MemoryCall.id)))
        if [u.tool_group_id for u in units if u.tool_group_id] != complete_groups:
            raise CompactionError("tool_group_coverage_incomplete")
        if len({u.source.source_id for u in units if u.source}) != sum(u.source is not None for u in units):
            raise CompactionError("duplicate_source_coverage")
        bodies, previous, total = [], None, 0
        for unit in units:
            if unit.source:
                body, source = read_registered(guard, unit.source)
                total += len(body.encode())
                if source.kind == "chat_message":
                    parent = source.native_version["parentMessageId"]
                    if parent != unit.parent_message_id or (previous is not None and parent != previous):
                        raise CompactionError("coverage_hole_or_order")
                    if previous is None and parent is not None:
                        raise CompactionError("coverage_must_start_at_root")
                    previous = source.native_id
                bodies.append((source.id, source.source_version, source.content_sha256))
            else:
                call = lock_one(guard.db, MemoryCall, unit.tool_group_id)
                owner_id = call.chat_execution_id or call.research_attempt_id if call else None
                if (call is None or call.workspace_id != guard.owner.workspace_id or owner_id != guard.owner.owner_id
                        or call.purpose != "tool_group" or call.state != "succeeded" or call.result_state != "valid"):
                    raise CompactionError("tool_group_unavailable")
                manifest = call.result_manifest
                if not isinstance(manifest, dict) or not manifest.get("complete"):
                    raise CompactionError("incomplete_tool_batch")
                for ref in manifest.get("sources", []):
                    read_registered(guard, SourceReference(**ref))
                bodies.append((call.id, call.result_sha256))
        if total > self.limits.max_body_bytes or len(canonical([asdict(u) for u in units]).encode()) > 131072:
            raise CompactionError("context_too_large")
        return bodies

    def _capture(self, guard, units, policy):
        validate_runtime_policy(policy)
        if validate_runtime_policy(policy) <= self.clock() or (guard.policy is not None and guard.policy != policy):
            raise CompactionError("context_policy_changed")
        sources = self._validate_units(guard, units)
        guard.snapshot=lock_one(guard.db,TaskMemorySnapshot,guard.checkpoint_id) if guard.checkpoint_id else None
        if guard.checkpoint_id and (guard.snapshot is None or guard.snapshot.workspace_id!=guard.owner.workspace_id
                or guard.snapshot.owner_user_id!=guard.owner.actor_user_id or guard.snapshot.status!="committed"):
            raise CompactionError("checkpoint_unavailable")
        if guard.snapshot:
            if guard.snapshot.policy_snapshot!=policy: raise CompactionError("context_policy_changed")
            old = list(guard.db.scalars(select(TaskMemoryCoverage).where(
                TaskMemoryCoverage.snapshot_id == guard.snapshot.id).order_by(TaskMemoryCoverage.ordinal)
                .with_for_update(nowait=True)))
            if len(old) > len(units) or any(row.unit_key != unit.key or row.source_id != (unit.source.source_id if unit.source else None)
                    or row.source_version != (unit.source.version if unit.source else None) or row.tool_group_id != unit.tool_group_id
                    for row, unit in zip(old, units)):
                raise CompactionError("checkpoint_coverage_changed")
        return CapturedContext(guard.owner, guard.context_version, guard.checkpoint_id,
            guard.snapshot.version if guard.snapshot else 0, digest([guard.native_state, sources]), tuple(units), digest(policy),canonical(guard.native_state))

    def main_question_key(self, captured, policy):
        if captured.owner.kind != "chat":
            return None
        def validate(db):
            guard = self.guard(db, captured.owner)
            if self._capture(guard, captured.units, policy) != captured:
                raise CompactionError("context_changed")
            current = []
            for index, unit in enumerate(captured.units):
                if unit.source:
                    source = db.get(MemorySource, unit.source.source_id)
                    if source.native_id == guard.native.user_message_id:
                        current.append((index, unit.key))
            if len(current) != 1:
                raise CompactionError("designated_question_required")
            index, key = current[0]
            if any(unit.tool_group_id for unit in captured.units[:index]):
                raise CompactionError("designated_question_order")
            return key
        return self.transact(validate)

    def capture(self, owner, units, policy):
        return self.transact(lambda db: self._capture(self.guard(db, owner), units, policy))

    def adopt(self, captured, *, covered_count, summary, policy, operation_key, input_sha256,
              before_tokens, after_tokens, count_source, provider_fingerprint, counter_version,
              generation_call_id=None,dispatch_profile=None,compaction_plan=None,summary_input=None,generation_request_sha256=None):
        from .summary import validate_summary
        if captured.owner.kind=="chat" and generation_call_id is None:raise CompactionError("generation_result_required")
        validate_summary(summary, captured.units[:covered_count])
        if not 0 < covered_count <= len(captured.units) or not 0 <= after_tokens < before_tokens:
            raise CompactionError("invalid_adoption")
        def commit(db):
            guard = self.guard(db, captured.owner)
            current = self._capture(guard, captured.units, policy)
            existing = db.scalar(select(TaskMemorySnapshot).where(TaskMemorySnapshot.operation_key == operation_key)
                                 .with_for_update(nowait=True))
            if existing:
                if existing.input_sha256 != input_sha256 or guard.checkpoint_id != existing.id:
                    raise CompactionError("operation_conflict")
                return CheckpointReceipt(existing.id, existing.context_version, existing.version, operation_key)
            if current != captured:
                raise CompactionError("context_changed")
            if guard.snapshot:
                previous_count = db.scalar(select(func.count()).select_from(TaskMemoryCoverage)
                    .where(TaskMemoryCoverage.snapshot_id == guard.snapshot.id))
                if covered_count <= previous_count:
                    raise CompactionError("no_new_coverage")
            if generation_call_id:
                call = lock_one(db, MemoryCall, generation_call_id)
                if (call is None or call.workspace_id != captured.owner.workspace_id or call.state != "succeeded"
                        or call.result_state != "valid" or (call.chat_execution_id or call.research_attempt_id) != captured.owner.owner_id
                        or call.purpose not in ("compact_chunk","compact_merge")
                        or canonical(call.input_manifest.get("capture")) != canonical(asdict(captured))
                        or call.result_sha256 != digest(summary)
                        or (call.result_manifest or {}).get("summary") != summary):
                    raise CompactionError("generation_result_unavailable")
                from .rendering import match_input,validate_result
                match_input(call,captured,policy,dispatch_profile,compaction_plan,summary_input)
                result=validate_result(db,call,summary,saved=True)
                if provider_fingerprint!=dispatch_profile["configFingerprint"] or counter_version!=dispatch_profile["counter"]["counter_version"]:raise CompactionError("dispatch_binding_changed")
                if not result["finalEligible"] or covered_count!=compaction_plan["intervalEnd"] or call.request_sha256!=generation_request_sha256:
                    raise CompactionError("summary_not_final")
                from .rendering import load_intervals,advance_intervals
                intervals,protected,frontier=load_intervals(db,captured,policy,proposed=(call.input_manifest,result))
                advance_intervals(intervals,protected,frontier,compaction_plan,summary,asdict(captured)["units"])
            expected_progress = {"stepId":guard.step.id if guard.step else None,
                "stateVersion":guard.step.state_version if guard.step else guard.native.version,
                "status":guard.step.status if guard.step else guard.native.state,"artifactIds":[guard.native.checkpoint_artifact_id] if guard.step and guard.native.checkpoint_artifact_id else []}
            if summary["progress"] != expected_progress:
                raise CompactionError("summary_native_progress_changed")
            id_, version = str(uuid4()), captured.checkpoint_version + 1
            snapshot = TaskMemorySnapshot(id=id_, workspace_id=captured.owner.workspace_id,
                owner_user_id=captured.owner.actor_user_id, audience="workspace",
                thread_id=guard.thread.id if guard.thread else None, run_id=guard.run.id if guard.run else None,
                step_id=guard.step.id if guard.step else None, attempt_id=guard.native.id if guard.step else None,
                branch_key=guard.step.branch_key if guard.step else None,
                anchor_leaf_id=guard.thread.active_message_id if guard.thread else None,
                parent_snapshot_id=captured.checkpoint_id, version=version, context_version=captured.context_version+1,
                status="committed", summary=summary, schema_version="task-memory-v2", policy_snapshot=policy,
                provider_fingerprint=provider_fingerprint, counter_version=counter_version, input_sha256=input_sha256,
                manifest_sha256=digest([asdict(u) for u in captured.units[:covered_count]]), operation_key=operation_key,
                before_tokens=before_tokens, after_tokens=after_tokens, count_source=count_source,
                generation_call_id=generation_call_id, created_at=self.clock(), invalidated_at=None, erased_at=None)
            db.add(snapshot); db.flush(); self.fault("snapshot")
            for ordinal, unit in enumerate(captured.units[:covered_count]):
                db.add(TaskMemoryCoverage(snapshot_id=id_, ordinal=ordinal, unit_key=unit.key,
                    source_id=unit.source.source_id if unit.source else None, tool_group_id=unit.tool_group_id,
                    source_version=unit.source.version if unit.source else None, parent_message_id=unit.parent_message_id))
            db.flush(); self.fault("coverage")
            dependencies = [(u.source.source_id if u.source else None, None, u.tool_group_id) for u in captured.units[:covered_count]]
            for unit in captured.units[:covered_count]:
                if unit.tool_group_id:
                    group = db.get(MemoryCall,unit.tool_group_id)
                    for raw in group.result_manifest.get("sources",[]):
                        reference=SourceReference(**raw)
                        read_registered(guard,reference)
                        leaf=(reference.source_id,None,None)
                        if leaf not in dependencies: dependencies.append(leaf)
            if captured.checkpoint_id: dependencies.append((None, captured.checkpoint_id, None))
            for source_id, used_snapshot_id, used_tool_call_id in dependencies:
                db.add(MemoryUse(id=str(uuid4()), workspace_id=captured.owner.workspace_id,
                    consumer_revision_id=None, consumer_snapshot_id=id_, consumer_call_id=None, consumer_call_part=None,
                    source_id=source_id, used_snapshot_id=used_snapshot_id, used_tool_call_id=used_tool_call_id,
                    use_mode="context", atom_key="coverage", support_group="original", relation="context"))
            db.flush(); self.fault("uses")
            native = ChatMemoryExecution if captured.owner.kind == "chat" else ResearchStepAttempt
            version_column = native.context_version if captured.owner.kind == "chat" else native.memory_context_version
            values = ({"context_version":captured.context_version+1,"checkpoint_id":id_} if captured.owner.kind == "chat"
                      else {"memory_context_version":captured.context_version+1,"memory_checkpoint_id":id_})
            result = db.execute(update(native).where(native.id == captured.owner.owner_id,
                version_column == captured.context_version).values(**values))
            if result.rowcount != 1: raise CompactionError("context_changed")
            db.flush(); self.fault("pointer"); self.fault("before_commit")
            return CheckpointReceipt(id_, captured.context_version+1, version, operation_key)
        return self.transact(commit)

    def reconcile(self, owner, operation_key):
        def read(db):
            guard = self.guard(db, owner)
            row = db.scalar(select(TaskMemorySnapshot).where(TaskMemorySnapshot.operation_key == operation_key,
                TaskMemorySnapshot.workspace_id == owner.workspace_id, TaskMemorySnapshot.owner_user_id == owner.actor_user_id))
            if row is None: return None
            if row.id != guard.checkpoint_id or row.status != "committed":
                raise CompactionError("checkpoint_unavailable")
            return CheckpointReceipt(row.id, row.context_version, row.version, row.operation_key)
        return self.transact(read)

    def progress(self, captured, policy):
        def read(db):
            guard=self.guard(db,captured.owner)
            if self._capture(guard,captured.units,policy)!=captured: raise CompactionError("context_changed")
            return {"stepId":guard.step.id if guard.step else None,
                    "stateVersion":guard.step.state_version if guard.step else guard.native.version,
                    "status":guard.step.status if guard.step else guard.native.state,"artifactIds":[guard.native.checkpoint_artifact_id] if guard.step and guard.native.checkpoint_artifact_id else []}
        return self.transact(read)

    def checkpoint_summary(self, captured, policy):
        def read(db):
            guard=self.guard(db,captured.owner)
            if self._capture(guard,captured.units,policy)!=captured: raise CompactionError("context_changed")
            if guard.snapshot is None: return None, 0
            size=db.scalar(select(func.count()).select_from(TaskMemoryCoverage).where(TaskMemoryCoverage.snapshot_id==guard.snapshot.id))
            return guard.snapshot.summary,size
        return self.transact(read)

    def checkpoint_intervals(self,captured,policy):
        from .rendering import load_intervals
        def read(db):
            guard=self.guard(db,captured.owner)
            if self._capture(guard,captured.units,policy)!=captured:raise CompactionError("context_changed")
            return load_intervals(db,captured,policy)
        return self.transact(read)

    def summary_child(self,call_id):
        def read(db):
            row=lock_one(db,MemoryCall,call_id)
            if row is None:raise CompactionError("summary_call_unavailable")
            return {"callId":row.id,"resultSha256":row.result_sha256,"inputManifestSha256":digest(row.input_manifest)}
        return self.transact(read)
