"""Exact persisted chat-owner predicates and historical/live separation on shipped PG."""
from dataclasses import asdict, replace
from datetime import datetime, UTC
import re
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from citeframe_contracts.compaction import CoverageUnit
from citeframe_contracts.memory import GenerationMessage, ToolCall
from citeframe_memory.compaction.archive import ToolArchive
from citeframe_memory.compaction.guards import digest
from citeframe_memory.compaction.policy import CompactionError
from citeframe_memory.compaction.units import ContextUnit
from citeframe_persistence import Base
from test_compaction_fixture import insert_message, pg43
from test_compaction_gate import Files
from test_compaction_native_lifecycle import native_chat, prepare_scenario, execution
from test_compaction_repository import adopt, prepared


def sibling(engine, scope, repo, owner, policy):
    user, assistant = str(uuid4()), str(uuid4())
    with engine.begin() as db:
        insert_message(db, scope, user, content="SIBLING source; never authorized to original execution")
        insert_message(db, scope, assistant, parent_id=user, content="")
        db.execute(text("UPDATE chat_messages SET role='assistant',status='streaming' WHERE id=:id"), {"id": assistant})
    other = replace(owner, owner_id=str(uuid4()))
    deadline = datetime.fromisoformat(policy["deadlineAt"])
    repo.create_chat(other, thread_id=scope.thread_id, user_message_id=user, assistant_message_id=assistant,
        request_id=str(uuid4()), request_sha256="c"*64, policy=policy, deadline_at=deadline, lease_expires_at=deadline)
    return other, (CoverageUnit("sibling", repo.register_source(other, "chat_message", user)),)


def committed_pair(engine):
    scope, repo, owner, policy, units = prepared(engine)
    other, foreign = sibling(engine, scope, repo, owner, policy)
    receipt = adopt(repo, repo.capture(owner, units, policy), policy)
    return scope, repo, owner, policy, units, receipt, other, foreign


def persisted_state(engine, owner):
    with engine.connect() as db:
        pointer = db.execute(text("SELECT context_version,checkpoint_id FROM chat_memory_executions WHERE id=:id"), {"id": owner.owner_id}).one()
        rows = tuple(db.execute(text("SELECT to_jsonb(t) FROM " + table + " t ORDER BY " + order)).scalars().all()
            for table, order in (("task_memory_snapshots", "id"), ("task_memory_coverage", "snapshot_id,ordinal"), ("memory_uses", "id")))
    return pointer, rows


def clone_candidate(engine, receipt, units, **changes):
    table = Base.metadata.tables["task_memory_snapshots"]
    with engine.connect() as db:
        row = dict(db.execute(select(table).where(table.c.id == receipt.snapshot_id)).mappings().one())
    row.update(id=str(uuid4()), operation_key=digest(str(uuid4())), manifest_sha256=digest([asdict(unit) for unit in units]))
    row.update(changes)
    return row


def insert_candidate(db, snapshot, units, owner, *, direct_uses=True):
    db.execute(Base.metadata.tables["task_memory_snapshots"].insert().values(**snapshot))
    for ordinal, unit in enumerate(units):
        db.execute(Base.metadata.tables["task_memory_coverage"].insert().values(snapshot_id=snapshot["id"], ordinal=ordinal,
            unit_key=unit.key, source_id=unit.source.source_id if unit.source else None,
            source_version=unit.source.version if unit.source else None, tool_group_id=unit.tool_group_id,
            parent_message_id=unit.parent_message_id))
        if direct_uses:
            insert_use(db, snapshot["workspace_id"], consumer_snapshot_id=snapshot["id"],
                **({"source_id": unit.source.source_id} if unit.source else {"used_tool_call_id": unit.tool_group_id}))
    db.execute(text("UPDATE chat_memory_executions SET checkpoint_id=:snapshot,context_version=:version WHERE id=:id"),
        {"snapshot": snapshot["id"], "version": snapshot["context_version"], "id": owner.owner_id})


def insert_use(db, workspace, **fields):
    db.execute(Base.metadata.tables["memory_uses"].insert().values(id=str(uuid4()), workspace_id=workspace,
        use_mode="context", atom_key="probe", support_group="original", relation="context", **fields))


def group_archive(repo, owner, units, policy, path, *, empty_sources=False):
    group = ContextUnit("scope-batch", "tool_group", (GenerationMessage("assistant", "", (ToolCall("scope-read", "read_source", "{}"),)),
        GenerationMessage("tool", "exact original result", tool_call_id="scope-read")), ("succeeded",))
    call = ToolArchive(repo, Files(path)).persist(repo.capture(owner, units, policy), policy, group, (units[0].source,))
    if empty_sources:
        calls = Base.metadata.tables["memory_calls"]
        with repo.sessions() as db, db.begin():
            row = dict(db.execute(select(calls).where(calls.c.id == call)).mappings().one())
            call = str(uuid4())
            row.update(id=call, logical_key="sql-empty-raw-group")
            row["result_manifest"] = dict(row["result_manifest"], sources=[])
            db.execute(calls.insert().values(**row))
    return call


@pytest.mark.parametrize("immediate", [False, True])
def test_same_thread_sibling_source_valid_hash_cannot_adopt(pg43, immediate):
    scope, repo, owner, policy, units, receipt, other, foreign = committed_pair(pg43)
    with pytest.raises(CompactionError, match="source_branch_mismatch"):
        repo.read_source(owner, foreign[0].source)
    snapshot = clone_candidate(pg43, receipt, foreign)
    assert snapshot["manifest_sha256"] == digest([asdict(unit) for unit in foreign])
    before = persisted_state(pg43, owner)
    with pytest.raises(DBAPIError) as failure:
        with pg43.begin() as db:
            insert_candidate(db, snapshot, foreign, owner)
            if immediate: db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert "manifest_mismatch" not in str(failure.value)
    assert "scope" in str(failure.value)
    assert persisted_state(pg43, owner) == before


@pytest.mark.parametrize("boundary", ["coverage", "snapshot_use", "call_use"])
def test_same_actor_thread_foreign_execution_group_rejected(pg43, tmp_path, boundary):
    scope, repo, owner, policy, units, receipt, other, foreign = committed_pair(pg43)
    group = group_archive(repo, other, foreign, policy, tmp_path)
    coverage = (CoverageUnit("foreign-group", tool_group_id=group),)
    snapshot = clone_candidate(pg43, receipt, coverage)
    with pg43.connect() as db:
        own_call = db.scalar(text("SELECT generation_call_id FROM task_memory_snapshots WHERE id=:id"), {"id": receipt.snapshot_id})
        assert db.scalar(text("SELECT compaction_tool_scope(c,:owner,NULL,:actor) FROM memory_calls c WHERE id=:id"),
            {"owner": other.owner_id, "actor": owner.actor_user_id, "id": group}) is True
    before = persisted_state(pg43, owner)
    with pytest.raises(DBAPIError) as failure:
        with pg43.begin() as db:
            if boundary == "coverage": insert_candidate(db, snapshot, coverage, owner, direct_uses=False)
            elif boundary == "snapshot_use": insert_use(db, scope.workspace_id, consumer_snapshot_id=receipt.snapshot_id, used_tool_call_id=group)
            else: insert_use(db, scope.workspace_id, consumer_call_id=own_call, consumer_call_part="result", used_tool_call_id=group)
            db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert "scope" in str(failure.value) and "manifest_mismatch" not in str(failure.value)
    assert persisted_state(pg43, owner) == before


@pytest.mark.parametrize("boundary", ["parent", "used_snapshot", "pointer", "call_source", "call_used_snapshot"])
def test_foreign_execution_snapshot_parent_dependency_and_pointer_rejected(pg43, boundary):
    scope, repo, owner, policy, units, receipt, other, foreign = committed_pair(pg43)
    foreign_receipt = adopt(repo, repo.capture(other, foreign, policy), policy)
    before = persisted_state(pg43, owner)
    with pg43.connect() as db:
        own_call = db.scalar(text("SELECT generation_call_id FROM task_memory_snapshots WHERE id=:id"), {"id": receipt.snapshot_id})
    with pytest.raises(DBAPIError) as failure:
        with pg43.begin() as db:
            if boundary == "pointer":
                db.execute(text("UPDATE chat_memory_executions SET checkpoint_id=:snapshot WHERE id=:id"),
                    {"snapshot": foreign_receipt.snapshot_id, "id": owner.owner_id})
            elif boundary == "used_snapshot":
                insert_use(db, scope.workspace_id, consumer_snapshot_id=receipt.snapshot_id, used_snapshot_id=foreign_receipt.snapshot_id)
            elif boundary == "call_source":
                insert_use(db, scope.workspace_id, consumer_call_id=own_call, consumer_call_part="result", source_id=foreign[0].source.source_id)
            elif boundary == "call_used_snapshot":
                insert_use(db, scope.workspace_id, consumer_call_id=own_call, consumer_call_part="result", used_snapshot_id=foreign_receipt.snapshot_id)
            else:
                candidate = clone_candidate(pg43, receipt, units, parent_snapshot_id=foreign_receipt.snapshot_id, version=2)
                insert_candidate(db, candidate, units, owner, direct_uses=False)
            db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert "manifest_mismatch" not in str(failure.value)
    assert re.search(r"compaction_.*(owner|parent|pointer|scope)", str(failure.value))
    assert persisted_state(pg43, owner) == before


@pytest.mark.parametrize("binding", ["null", "missing", "foreign", "wrong_kind"])
def test_new_chat_snapshot_requires_exact_persisted_generation_owner(pg43, tmp_path, binding):
    scope, repo, owner, policy, units, receipt, other, foreign = committed_pair(pg43)
    if binding == "foreign":
        foreign_receipt = adopt(repo, repo.capture(other, foreign, policy), policy)
        with pg43.connect() as db:
            call = db.scalar(text("SELECT generation_call_id FROM task_memory_snapshots WHERE id=:id"), {"id": foreign_receipt.snapshot_id})
    elif binding == "wrong_kind": call = group_archive(repo, owner, units, policy, tmp_path)
    else: call = None if binding == "null" else str(uuid4())
    candidate = clone_candidate(pg43, receipt, units[:1], generation_call_id=call)
    before = persisted_state(pg43, owner)
    with pytest.raises(DBAPIError):
        with pg43.begin() as db:
            insert_candidate(db, candidate, units[:1], owner)
            db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert persisted_state(pg43, owner) == before


@pytest.mark.parametrize("owners", ["neither", "both", "missing", "wrong_kind", "thread_id"])
def test_source_predicate_null_and_ambiguous_owner_fail_false(pg43, owners):
    scope, repo, owner, policy, units = prepared(pg43)
    eid = None if owners in ("neither", "wrong_kind") else owner.owner_id
    aid = owner.owner_id if owners in ("both", "wrong_kind") else None
    if owners == "missing": eid = str(uuid4())
    if owners == "thread_id": eid = scope.thread_id
    with pg43.connect() as db:
        assert db.scalar(text("SELECT compaction_source_scope(s,:eid,:aid) FROM memory_sources s WHERE id=:id"),
            {"eid": eid, "aid": aid, "id": units[0].source.source_id}) is False
        assert db.scalar(text("SELECT compaction_source_scope(s,:eid,NULL) FROM memory_sources s WHERE id=:id"),
            {"eid": owner.owner_id, "id": units[0].source.source_id}) is True


@pytest.mark.parametrize("mutation", ["cycle", "foreign_thread", "foreign_workspace", "streaming_tail", "invalid_role"])
def test_source_scope_checks_entire_tail_after_finding_designated_user(pg43, mutation):
    scope, repo, owner, policy, units = prepared(pg43)
    with pg43.connect() as db:
        current = db.scalar(text("SELECT user_message_id FROM chat_memory_executions WHERE id=:id"), {"id": owner.owner_id})
    reference = repo.register_source(owner, "chat_message", current)
    changes = {
        "cycle": ("parent_message_id=:value", current),
        "foreign_thread": ("thread_id=:value", scope.other_thread_id),
        "foreign_workspace": ("workspace_id=:value", scope.other_workspace_id),
        "streaming_tail": ("status=:value", "streaming"),
        "invalid_role": ("role=:value", "tool"),
    }
    assignment, value = changes[mutation]
    with pg43.begin() as db:
        db.execute(text(f"UPDATE chat_messages SET {assignment} WHERE id=:id"), {"value": value, "id": scope.parent_id})
    with pg43.connect() as db:
        assert db.scalar(text("SELECT compaction_source_scope(s,:owner,NULL) FROM memory_sources s WHERE id=:id"),
            {"owner": owner.owner_id, "id": reference.source_id}) is False


@pytest.mark.parametrize("terminal", ["finalize", "fail"])
@pytest.mark.parametrize("lifecycle", ["invalidated", "erased"])
def test_historical_owner_survives_two_checkpoints_native_terminal_and_erasure(pg43, native_chat, terminal, lifecycle):
    prepared_chat, history, anchor = prepare_scenario(native_chat, "later")
    repo, owner, policy, units = execution(pg43, native_chat, prepared_chat, history)
    first = adopt(repo, repo.capture(owner, units, policy), policy, count=1)
    second = adopt(repo, repo.capture(owner, units, policy), policy, count=2)
    if terminal == "finalize": native_chat.chat.finalize_chat(native_chat.db, prepared_chat, "Native final result")
    else: native_chat.chat.fail_chat(native_chat.db, prepared_chat, "fixture_failure", "Native failure")
    with pg43.begin() as db:
        db.execute(text("UPDATE memory_sources SET state='stale',invalidated_at=now() WHERE id=:id"), {"id": units[0].source.source_id})
        db.execute(text("DELETE FROM chat_messages WHERE id=:id"), {"id": history[0]})
        db.execute(text("UPDATE memory_calls SET result_state=:state" + (",result_manifest=NULL" if lifecycle == "erased" else "") + " WHERE id IN (SELECT generation_call_id FROM task_memory_snapshots)"), {"state": lifecycle})
        if lifecycle == "erased":
            db.execute(text("UPDATE task_memory_snapshots SET status='erased',summary=NULL,erased_at=now()"))
        else:
            db.execute(text("UPDATE task_memory_snapshots SET status='invalidated',invalidated_at=now()"))
        db.execute(text("UPDATE chat_memory_executions SET state='succeeded',context_version=3,lease_expires_at=lease_expires_at+interval '1 minute' WHERE id=:id"), {"id": owner.owner_id})
        db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pg43.connect() as db:
        assert [db.scalar(text("SELECT compaction_snapshot_chat_owner(:id)"), {"id": receipt.snapshot_id}) for receipt in (first, second)] == [owner.owner_id, owner.owner_id]
        assert db.execute(text("SELECT anchor_leaf_id,checkpoint_id,context_version FROM chat_memory_executions WHERE id=:id"), {"id": owner.owner_id}).one() == (anchor, second.snapshot_id, 3)
    before = persisted_state(pg43, owner)
    with pytest.raises(DBAPIError):
        with pg43.begin() as db:
            insert_use(db, owner.workspace_id, consumer_snapshot_id=second.snapshot_id, used_snapshot_id=first.snapshot_id)
            db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pytest.raises(DBAPIError):
        with pg43.begin() as db:
            db.execute(text("UPDATE chat_memory_executions SET checkpoint_id=:snapshot WHERE id=:id"), {"snapshot": first.snapshot_id, "id": owner.owner_id})
            db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pytest.raises(CompactionError): repo.capture(owner, units, policy)
    assert persisted_state(pg43, owner) == before


def test_scope_functions_have_no_explicit_native_lock_or_write(pg43):
    with pg43.connect() as db:
        functions = db.execute(text("""SELECT p.proname,p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname=current_schema() AND p.proname IN
            ('compaction_source_scope','compaction_tool_scope','compaction_snapshot_chat_owner','compaction_chat_live','compaction_snapshot_live','compaction_chat_ancestry')""")).all()
    assert len(functions) == 6
    for name, source in functions:
        assert not re.search(r"FOR\s+(UPDATE|SHARE)|pg_advisory|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM", source, re.I), name
        assert not re.search(r"\b\w+\.content\b", source, re.I), name
        assert not re.search(r"SELECT\s+\*\s+INTO\s+\w+\s+FROM\s+chat_messages", source, re.I), name


@pytest.mark.parametrize("depth", [1024, 1025])
def test_sql_selected_chain_exact_depth_boundary(pg43, depth):
    scope, repo, owner, policy, units = prepared(pg43)
    with pg43.connect() as db:
        current = db.scalar(text("SELECT user_message_id FROM chat_memory_executions WHERE id=:id"), {"id": owner.owner_id})
    reference = repo.register_source(owner, "chat_message", current)
    ids = [str(uuid4()) for _ in range(depth-1)]
    with pg43.begin() as db:
        db.execute(Base.metadata.tables["chat_messages"].insert(), [dict(id=id_, workspace_id=scope.workspace_id,
            thread_id=scope.thread_id, parent_message_id=ids[index-1] if index else None,
            role="user", status="completed", content="metadata-only tail", created_at=datetime.now(UTC))
            for index, id_ in enumerate(ids)])
        db.execute(text("UPDATE chat_messages SET parent_message_id=:parent WHERE id=:id"), {"parent": ids[-1], "id": current})
        sources = Base.metadata.tables["memory_sources"]
        row = dict(db.execute(select(sources).where(sources.c.id == reference.source_id)).mappings().one())
        revision = db.scalar(text("SELECT compaction_revision FROM chat_messages WHERE id=:id"), {"id": current})
        db.execute(text("UPDATE memory_sources SET state='stale',invalidated_at=now() WHERE id=:id"), {"id": reference.source_id})
        row.update(id=str(uuid4()), source_version=revision,
            native_version=dict(row["native_version"], parentMessageId=ids[-1], compactionRevision=revision))
        db.execute(sources.insert().values(**row))
        reference = replace(reference, source_id=row["id"], version=revision)
    with pg43.connect() as db:
        assert db.scalar(text("SELECT compaction_source_scope(s,:owner,NULL) FROM memory_sources s WHERE id=:id"),
            {"owner": owner.owner_id, "id": reference.source_id}) is (depth == 1024)
    # This isolates the SQL ancestry bound; full capture still applies its smaller total-row envelope.
    with pytest.raises(CompactionError, match="context_too_large"):
        repo.capture(owner, (), policy)


@pytest.mark.parametrize("owners", ["neither", "both", "missing", "wrong_kind", "thread_id", "wrong_actor"])
def test_tool_predicate_null_and_ambiguous_owner_fail_false(pg43, tmp_path, owners):
    scope, repo, owner, policy, units = prepared(pg43)
    call = group_archive(repo, owner, units, policy, tmp_path)
    eid = None if owners in ("neither", "wrong_kind") else owner.owner_id
    aid = owner.owner_id if owners in ("both", "wrong_kind") else None
    actor = scope.other_user_id if owners == "wrong_actor" else owner.actor_user_id
    if owners == "missing": eid = str(uuid4())
    if owners == "thread_id": eid = scope.thread_id
    with pg43.connect() as db:
        assert db.scalar(text("SELECT compaction_tool_scope(c,:eid,:aid,:actor) FROM memory_calls c WHERE id=:id"),
            {"eid": eid, "aid": aid, "actor": actor, "id": call}) is False
        assert db.scalar(text("SELECT compaction_tool_scope(c,:eid,NULL,:actor) FROM memory_calls c WHERE id=:id"),
            {"eid": owner.owner_id, "actor": owner.actor_user_id, "id": call}) is True



def test_group_raw_dependency_cannot_add_sibling_source_outside_direct_coverage(pg43, tmp_path):
    scope, repo, owner, policy, units, receipt, other, foreign = committed_pair(pg43)
    call = group_archive(repo, owner, units, policy, tmp_path)
    calls = Base.metadata.tables["memory_calls"]
    with pg43.begin() as db:
        row = dict(db.execute(select(calls).where(calls.c.id == call)).mappings().one())
        call = str(uuid4())
        row.update(id=call, logical_key="forged-raw-dependency")
        row["result_manifest"] = dict(row["result_manifest"], sources=[asdict(foreign[0].source)])
        db.execute(calls.insert().values(**row))
    with pg43.connect() as db:
        assert db.scalar(text("SELECT compaction_tool_scope(c,:owner,NULL,:actor) FROM memory_calls c WHERE id=:id"),
            {"owner": owner.owner_id, "actor": owner.actor_user_id, "id": call}) is False
    before = persisted_state(pg43, owner)
    with pytest.raises(DBAPIError, match="scope"):
        with pg43.begin() as db:
            insert_use(db, scope.workspace_id, consumer_snapshot_id=receipt.snapshot_id, used_tool_call_id=call)
            db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert persisted_state(pg43, owner) == before



@pytest.mark.parametrize("terminal", ["finalize", "cancel"])
@pytest.mark.parametrize("boundary", ["predicate", "use", "snapshot_pointer"])
def test_empty_raw_tool_group_still_requires_live_native_owner(pg43, tmp_path, native_chat, terminal, boundary):
    prepared_chat, history, anchor = prepare_scenario(native_chat, "later")
    repo, owner, policy, units = execution(pg43, native_chat, prepared_chat, history)
    receipt = adopt(repo, repo.capture(owner, units, policy), policy)
    call = group_archive(repo, owner, units, policy, tmp_path, empty_sources=True)
    coverage = (CoverageUnit("empty-raw-group", tool_group_id=call),)
    candidate = clone_candidate(pg43, receipt, coverage)
    with pg43.connect() as db:
        assert db.scalar(text("SELECT compaction_tool_scope(c,:owner,NULL,:actor) FROM memory_calls c WHERE id=:id"),
            {"owner": owner.owner_id, "actor": owner.actor_user_id, "id": call}) is True
    if terminal == "finalize": native_chat.chat.finalize_chat(native_chat.db, prepared_chat, "Native terminal answer")
    else:
        with pg43.begin() as db:
            db.execute(text("UPDATE chat_memory_executions SET cancel_requested_at=now() WHERE id=:id"), {"id": owner.owner_id})
    before = persisted_state(pg43, owner)
    if boundary == "predicate":
        with pg43.connect() as db:
            assert db.scalar(text("SELECT compaction_tool_scope(c,:owner,NULL,:actor) FROM memory_calls c WHERE id=:id"),
                {"owner": owner.owner_id, "actor": owner.actor_user_id, "id": call}) is False
    else:
        with pytest.raises(DBAPIError, match="scope"):
            with pg43.begin() as db:
                if boundary == "use": insert_use(db, owner.workspace_id, consumer_snapshot_id=receipt.snapshot_id, used_tool_call_id=call)
                else: insert_candidate(db, candidate, coverage, owner, direct_uses=False)
                db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert persisted_state(pg43, owner) == before


def test_forged_call_actor_cannot_consume_same_workspace_source(pg43):
    scope, repo, owner, policy, units, receipt, other, foreign = committed_pair(pg43)
    calls = Base.metadata.tables["memory_calls"]
    with pg43.begin() as db:
        call = db.scalar(text("SELECT generation_call_id FROM task_memory_snapshots WHERE id=:id"), {"id": receipt.snapshot_id})
        row = dict(db.execute(select(calls).where(calls.c.id == call)).mappings().one())
        row.update(id=str(uuid4()), logical_key="forged-actor", actor_user_id=scope.other_user_id)
        db.execute(calls.insert().values(**row))
    before = persisted_state(pg43, owner)
    with pytest.raises(DBAPIError, match="scope"):
        with pg43.begin() as db:
            insert_use(db, scope.workspace_id, consumer_call_id=row["id"], consumer_call_part="result", source_id=units[0].source.source_id)
            db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert persisted_state(pg43, owner) == before


def test_dependency_noop_update_revalidates_current_scope(pg43):
    scope, repo, owner, policy, units, receipt, other, foreign = committed_pair(pg43)
    with pg43.begin() as db:
        db.execute(text("UPDATE memory_sources SET state='stale',invalidated_at=now() WHERE id=:id"), {"id": units[0].source.source_id})
    before = persisted_state(pg43, owner)
    with pytest.raises(DBAPIError, match="scope"):
        with pg43.begin() as db:
            db.execute(text("UPDATE memory_uses SET atom_key=atom_key WHERE consumer_snapshot_id=:id"), {"id": receipt.snapshot_id})
            db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert persisted_state(pg43, owner) == before



@pytest.mark.parametrize("claim", ["context_version", "actor_user_id", "workspace_id"])
def test_generation_capture_claims_match_persisted_call_and_snapshot_owner(pg43, claim):
    scope, repo, owner, policy, units, receipt, other, foreign = committed_pair(pg43)
    calls = Base.metadata.tables["memory_calls"]
    with pg43.begin() as db:
        original_call = db.scalar(text("SELECT generation_call_id FROM task_memory_snapshots WHERE id=:id"), {"id": receipt.snapshot_id})
        call = dict(db.execute(select(calls).where(calls.c.id == original_call)).mappings().one())
        call.update(id=str(uuid4()), logical_key="forged-capture-" + claim)
        capture = call["input_manifest"]["capture"]
        if claim == "context_version": capture[claim] = call["context_version"] + 1
        else: capture["owner"][claim] = scope.other_user_id if claim == "actor_user_id" else scope.other_workspace_id
        db.execute(calls.insert().values(**call))
    candidate = clone_candidate(pg43, receipt, units[:1], generation_call_id=call["id"])
    before = persisted_state(pg43, owner)
    with pytest.raises(DBAPIError, match="compaction_generation_owner_required"):
        with pg43.begin() as db:
            insert_candidate(db, candidate, units[:1], owner)
            db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert persisted_state(pg43, owner) == before


@pytest.mark.parametrize("null_anchor", [False, True])
def test_snapshot_anchor_must_match_execution_with_null_safe_equality(pg43, null_anchor):
    scope, repo, owner, policy, units = prepared(pg43, null_anchor=null_anchor)
    receipt = adopt(repo, repo.capture(owner, units, policy), policy)
    candidate = clone_candidate(pg43, receipt, units[:1], anchor_leaf_id=scope.leaf_id if null_anchor else None)
    before = persisted_state(pg43, owner)
    with pytest.raises(DBAPIError) as failure:
        with pg43.begin() as db:
            insert_candidate(db, candidate, units[:1], owner)
            db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert "manifest_mismatch" not in str(failure.value)
    assert "compaction_" in str(failure.value)
    assert persisted_state(pg43, owner) == before


@pytest.mark.parametrize("boundary", ["predicate", "call_use", "snapshot"])
def test_body_only_native_revision_revokes_live_scope_retains_history(pg43, boundary):
    scope, repo, owner, policy, units, receipt, other, foreign = committed_pair(pg43)
    candidate = clone_candidate(pg43, receipt, units[:1])
    with pg43.connect() as db:
        original = db.execute(text("SELECT m.id,m.content,m.compaction_revision,s.source_version FROM memory_sources s JOIN chat_messages m ON m.id=s.native_id WHERE s.id=:id"),
            {"id": units[0].source.source_id}).one()
        call = db.scalar(text("SELECT generation_call_id FROM task_memory_snapshots WHERE id=:id"), {"id": receipt.snapshot_id})
        assert db.scalar(text("SELECT compaction_source_scope(s,:owner,NULL) FROM memory_sources s WHERE id=:id"),
            {"owner": owner.owner_id, "id": units[0].source.source_id}) is True
    before = persisted_state(pg43, owner)
    with pg43.begin() as db:
        db.execute(text("UPDATE chat_messages SET content=:body WHERE id=:id"), {"body": original.content + " changed body only", "id": original.id})
        db.execute(text("UPDATE chat_memory_executions SET checkpoint_id=checkpoint_id WHERE id=:id"), {"id": owner.owner_id})
        db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pg43.connect() as db:
        assert db.scalar(text("SELECT compaction_revision FROM chat_messages WHERE id=:id"), {"id": original.id}) > original.compaction_revision
        assert db.scalar(text("SELECT source_version FROM memory_sources WHERE id=:id"), {"id": units[0].source.source_id}) == original.source_version
        assert db.scalar(text("SELECT compaction_snapshot_chat_owner(:id)"), {"id": receipt.snapshot_id}) == owner.owner_id
    assert persisted_state(pg43, owner) == before
    if boundary == "predicate":
        with pg43.connect() as db:
            assert db.scalar(text("SELECT compaction_source_scope(s,:owner,NULL) FROM memory_sources s WHERE id=:id"),
                {"owner": owner.owner_id, "id": units[0].source.source_id}) is False
    else:
        with pytest.raises(DBAPIError) as failure:
            with pg43.begin() as db:
                if boundary == "call_use":
                    insert_use(db, owner.workspace_id, consumer_call_id=call, consumer_call_part="result", source_id=units[0].source.source_id)
                else:
                    insert_candidate(db, candidate, units[:1], owner, direct_uses=False)
                db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        assert "scope" in str(failure.value) and "manifest_mismatch" not in str(failure.value)
    assert persisted_state(pg43, owner) == before


@pytest.mark.parametrize("field", ["messageId", "parentMessageId", "role", "status", "compactionRevision"])
def test_standalone_source_predicate_checks_exact_native_metadata(pg43, field):
    import json

    scope, repo, owner, policy, units = prepared(pg43)
    with pg43.connect() as db:
        native = db.scalar(text("SELECT native_version FROM memory_sources WHERE id=:id"), {"id": units[0].source.source_id})
        changed = dict(native)
        changed[field] = {
            "messageId": str(uuid4()), "parentMessageId": str(uuid4()),
            "role": "assistant" if native["role"] == "user" else "user",
            "status": "failed" if native["status"] == "completed" else "completed",
            "compactionRevision": native["compactionRevision"] + 1,
        }[field]
        assert db.scalar(text("SELECT compaction_source_scope(s,:owner,NULL) FROM memory_sources s WHERE id=:id"),
            {"owner": owner.owner_id, "id": units[0].source.source_id}) is True
        assert db.scalar(text("SELECT compaction_source_scope(jsonb_populate_record(s,CAST(:change AS jsonb)),:owner,NULL) FROM memory_sources s WHERE id=:id"),
            {"change": json.dumps({"native_version": changed}), "owner": owner.owner_id, "id": units[0].source.source_id}) is False
