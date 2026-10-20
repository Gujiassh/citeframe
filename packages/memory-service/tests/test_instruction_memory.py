"""Opt-in real PostgreSQL oracles. Every test owns a fresh schema in a test-only DB."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from hashlib import sha256
from alembic.config import Config
from alembic.script import ScriptDirectory
from dataclasses import replace
from datetime import UTC, datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from citeframe_contracts.memory import (
    AccessContext, AccessDenied, IdempotencyConflict, MemoryConditions, MemoryRequest,
    MemoryStatement, SourceUnavailable, VersionConflict,
)
from citeframe_memory.access import WorkspaceAccess
from citeframe_memory.commands import MemoryCommands
from citeframe_memory.lifecycle import invalidate_instruction
from citeframe_persistence.models import User, Workspace, WorkspaceMembership
from citeframe_persistence.models.memory import MemoryInstruction, MemoryOperation, MemoryRecord, MemoryRevision, MemorySource, MemoryUse

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("memory_migration", ROOT / "apps/api/alembic/versions/t4b5c6d7e8f9_instruction_memory.py")
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)
MARKER = "ER01_CONDITIONS_ONLY_7C92"


def request():
    return MemoryRequest(str(uuid4()), str(uuid4()))


def statement(marker="ordinary"):
    return MemoryStatement("Use 37.5 ms only for batch=8; never production", MemoryConditions(marker, "test only"), "constraint", True)


def test_validation_and_fail_closed():
    with pytest.raises(AccessDenied):
        MemoryCommands(None, None)
    with pytest.raises(ValueError):
        MemoryConditions("", "test")
    with pytest.raises(ValueError):
        MemoryConditions("test", "test", datetime.now())
    with pytest.raises(ValueError):
        MemoryStatement("x", MemoryConditions("s", "a"), pinned=True)


def test_neutral_import_without_application_packages():
    paths = [str(ROOT / "packages" / name / "src") for name in (
        "backend-contracts", "backend-persistence", "memory-service")]
    code = """
import importlib.abc, sys
class DenyApps(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('ai_pdf_api', 'ai_pdf_worker'):
            raise AssertionError(fullname)
sys.meta_path.insert(0, DenyApps())
import citeframe_contracts.memory
import citeframe_memory.access, citeframe_memory.commands, citeframe_memory.sources, citeframe_memory.lifecycle
print('neutral-import-pass')
"""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(paths), "PYTHONDONTWRITEBYTECODE": "1"}
    assert "neutral-import-pass" in subprocess.check_output([sys.executable, "-c", code], env=env, text=True)


def migrate(engine,target,*,downgrade=False):
    config=Config()
    config.set_main_option("script_location",str(ROOT / "apps/api/alembic"))
    scripts=ScriptDirectory.from_config(config)
    revisions=scripts._downgrade_revs if downgrade else scripts._upgrade_revs
    with engine.begin() as conn:
        context=MigrationContext.configure(conn,opts={"fn":lambda current,_:revisions(target,current),"transactional_ddl":True})
        with Operations.context(context):context.run_migrations()


@contextmanager
def migrated_private(target):
    url = os.environ.get("CITEFRAME_MEMORY42_POSTGRES_URL")
    if not url and os.environ.get("CI"):
        pytest.fail("CI requires CITEFRAME_MEMORY42_POSTGRES_URL; PostgreSQL oracles must not skip")
    if not url:
        pytest.skip("requires disposable citeframe_memory42_test database")
    assert make_url(url).database == "citeframe_memory42_test", "Refusing non-test database"
    schema = "memory42_" + uuid4().hex
    admin = create_engine(url)
    engine=None
    try:
        with admin.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public"))
            extensions=set(conn.execute(text("SELECT extname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE n.nspname='public'")).scalars())
            assert {"vector","pg_trgm"} <= extensions
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine=create_engine(url,pool_size=8,connect_args={"options":f"-c search_path={schema},public -c lock_timeout=8000 -c statement_timeout=15000"})
        migrate(engine,target)
        uid,other,wid=(str(uuid4()) for _ in range(3))
        with Session(engine) as db,db.begin():
            for id_ in (uid,other):
                db.add(User(id=id_,email=id_+"@test.invalid",name="fixture",password_hash="unused",avatar_url=""))
            db.flush()
            db.add(Workspace(id=wid,name="fixture",created_by_user_id=other))
            db.flush()
            db.add_all([WorkspaceMembership(id=str(uuid4()),workspace_id=wid,user_id=uid,role="member"),
                        WorkspaceMembership(id=str(uuid4()),workspace_id=wid,user_id=other,role="owner")])
        yield engine,AccessContext(uid,wid,"management","private"),other
    finally:
        if engine is not None:engine.dispose()
        with admin.begin() as conn:conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def pg():
    with migrated_private("u5c6d7e8f9a0") as value:yield value


@pytest.fixture
def pg_t4():
    with migrated_private("t4b5c6d7e8f9") as value:yield value


def command(engine, method, context, *args):
    with Session(engine) as db:
        return getattr(MemoryCommands(db, WorkspaceAccess(db)), method)(context, *args)


def test_create_replay_conflict_lost_ack_and_owner_privacy(pg):
    engine, ctx, other = pg
    req = request()
    first = command(engine, "remember", ctx, req, statement())
    assert command(engine, "remember", ctx, req, statement()) == first
    assert command(engine, "reconcile", ctx, req.request_id) == first
    with pytest.raises(IdempotencyConflict):
        command(engine, "remember", ctx, req, statement("changed"))
    for forbidden in (replace(ctx, actor_user_id=other), replace(ctx, purpose="chat", output_audience="workspace"),
                      replace(ctx, purpose="research_planning", output_audience="workspace")):
        with pytest.raises(AccessDenied):
            command(engine, "read", forbidden, first.resource.memory_id)
        with pytest.raises((AccessDenied, SourceUnavailable)):
            command(engine, "read_source", forbidden, first.resource.confirmation_source_id)
    assert command(engine, "read_source", ctx, first.resource.confirmation_source_id).actor_user_id == ctx.actor_user_id


def test_all_revision_conditions_erasure_and_replay(pg):
    engine, ctx, _ = pg
    req = request()
    saved = command(engine, "remember", ctx, req, statement(MARKER))
    mid = saved.resource.memory_id
    inactive = command(engine, "deactivate", ctx, request(), mid, 1)
    erased = command(engine, "delete", ctx, request(), mid, inactive.resource.version)
    assert erased.resource.intent == "deleted" and erased.resource.statement is None
    assert command(engine, "remember", ctx, req, statement(MARKER)).resource.statement is None
    assert all(v.erased and v.statement is None for v in command(engine, "history", ctx, mid))
    with pytest.raises(SourceUnavailable):
        command(engine, "read_source", ctx, saved.resource.confirmation_source_id)
    with engine.connect() as conn:
        for table in MIGRATION.TABLES:
            payload = conn.execute(text(f"SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]') FROM {table} t")).scalar()
            assert MARKER not in json.dumps(payload)
        assert conn.scalar(text("SELECT count(*) FROM memory_revisions WHERE erased_at IS NOT NULL AND conditions IS NULL AND content IS NULL AND content_sha256 IS NULL")) == 3
        assert conn.scalar(text("SELECT count(*) FROM memory_uses")) == 3


def test_correction_cas_race_and_shared_instruction_preservation(pg):
    engine, ctx, _ = pg
    first = command(engine, "remember", ctx, request(), statement())
    mid = first.resource.memory_id
    barrier = Barrier(2)
    def contender(action):
        barrier.wait()
        try:
            args = (request(), mid, 1, statement("corrected")) if action == "correct" else (request(), mid, 1)
            return command(engine, action, ctx, *args)
        except VersionConflict:
            return "conflict"
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(contender, ("correct", "deactivate")))
    assert sum(r == "conflict" for r in results) == 1
    current = command(engine, "read", ctx, mid)
    if current.intent == "inactive":
        successor = command(engine, "correct", ctx, request(), mid, current.version, statement("corrected"))
        current = command(engine, "read", ctx, mid)
    else:
        successor = next(r for r in results if r != "conflict")
    command(engine, "delete", ctx, request(), mid, current.version)
    assert command(engine, "read_source", ctx, successor.resource.confirmation_source_id).content == statement().content
    assert command(engine, "read", ctx, successor.resource.memory_id).intent == "active"
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM memory_records WHERE supersedes_id=:mid"), {"mid": mid}) == 1


def test_same_key_concurrent_one_mutation(pg):
    engine, ctx, _ = pg
    req, barrier = request(), Barrier(2)
    def run(_):
        barrier.wait()
        return command(engine, "remember", ctx, req, statement())
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(run, range(2)))
    assert results[0] == results[1]
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM memory_records")) == 1
        assert conn.scalar(text("SELECT count(*) FROM memory_operations")) == 1


def test_invalidation_preserves_intent_and_source_validity(pg):
    engine, ctx, _ = pg
    saved = command(engine, "remember", ctx, request(), statement())
    with Session(engine) as db:
        invalidate_instruction(MemoryCommands(db, WorkspaceAccess(db)), ctx, saved.resource.confirmation_source_id)
    view = command(engine, "read", ctx, saved.resource.memory_id)
    assert (view.intent, view.validity) == ("active", "invalidated")
    result = command(engine, "deactivate", ctx, request(), view.memory_id, view.version)
    assert (result.resource.intent, result.resource.validity) == ("inactive", "invalidated")


@pytest.mark.parametrize("sql", [
    "UPDATE memory_revisions SET conditions='{}'::jsonb",
    "UPDATE memory_revisions SET content=NULL",
    "UPDATE memory_revisions SET intent='inactive'",
    "UPDATE memory_revisions SET erased_at=now(), content=NULL, content_sha256=NULL",
    "DELETE FROM memory_uses",
    "UPDATE memory_records SET current_version=99",
    "UPDATE memory_instructions SET actor_user_id=:other",
    "UPDATE memory_sources SET owner_user_id=:other, actor_user_id=:other",
])
def test_illegal_sql_rejected(pg, sql):
    engine, ctx, other = pg
    command(engine, "remember", ctx, request(), statement())
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text(sql), {"other": other})


def test_erased_restore_and_retained_fk_rejected(pg):
    engine, ctx, _ = pg
    first = command(engine, "remember", ctx, request(), statement())
    command(engine, "delete", ctx, request(), first.resource.memory_id, 1)
    for sql in ("UPDATE memory_revisions SET erased_at=NULL", "DELETE FROM memory_instructions",
                "UPDATE memory_revisions SET erased_at=erased_at + interval '1 second'",
                "UPDATE memory_revisions SET conditions='{}'::jsonb"):
        with pytest.raises(DBAPIError):
            with engine.begin() as conn:
                conn.execute(text(sql))


def test_revocation_archive_and_cross_workspace_fail_closed(pg):
    engine, ctx, _ = pg
    first = command(engine, "remember", ctx, request(), statement())
    with pytest.raises(AccessDenied):
        command(engine, "read", replace(ctx, workspace_id=str(uuid4())), first.resource.memory_id)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM workspace_memberships WHERE user_id=:uid"), {"uid": ctx.actor_user_id})
    with pytest.raises(AccessDenied):
        command(engine, "reconcile", ctx, first.request_id)
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM memory_records")) == 1


def test_populated_down_refused_empty_down_up_preserves_native(pg_t4):
    engine,ctx,_=pg_t4
    with engine.connect() as conn:
        before=conn.execute(text("SELECT jsonb_agg(to_jsonb(w)) FROM workspaces w")).scalar()
        assert conn.scalar(text("SELECT version_num FROM alembic_version"))=="t4b5c6d7e8f9"
    migrate(engine,"s3a4b5c6d7e8",downgrade=True)
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version"))=="s3a4b5c6d7e8"
    migrate(engine,"t4b5c6d7e8f9")
    with engine.begin() as conn:
        assert conn.execute(text("SELECT jsonb_agg(to_jsonb(w)) FROM workspaces w")).scalar()==before
        conn.execute(text("""INSERT INTO memory_instructions(id,workspace_id,actor_user_id,operation,request_id,content,content_sha256,created_at)
            VALUES(:id,:wid,:uid,'remember',:request,'historical',encode(sha256(convert_to('historical','UTF8')),'hex'),now())"""),
            {"id":str(uuid4()),"wid":ctx.workspace_id,"uid":ctx.actor_user_id,"request":str(uuid4())})
    with pytest.raises(RuntimeError,match="approved export/erasure"):
        migrate(engine,"s3a4b5c6d7e8",downgrade=True)
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version"))=="t4b5c6d7e8f9"
        assert conn.scalar(text("SELECT count(*) FROM memory_instructions"))==1



@pytest.mark.parametrize("role", ["viewer", "administrator", "", "OWNER"])
def test_unknown_member_roles_fail_closed(pg, role):
    engine, ctx, _ = pg
    with engine.begin() as conn:
        conn.execute(text("UPDATE workspace_memberships SET role=:role WHERE user_id=:uid"),
                     {"role": role, "uid": ctx.actor_user_id})
    with pytest.raises(AccessDenied):
        command(engine, "remember", ctx, request(), statement())


def test_deleted_identity_cannot_append_live_head(pg):
    engine, ctx, _ = pg
    first = command(engine, "remember", ctx, request(), statement())
    with engine.connect() as conn:
        original = dict(conn.execute(select(MemoryRevision.__table__)).mappings().one())
        support = dict(conn.execute(select(MemoryUse.__table__)).mappings().one())
    command(engine, "delete", ctx, request(), first.resource.memory_id, 1)
    original.update(version=3, revision_id=str(uuid4()))
    support.update(id=str(uuid4()), consumer_revision_id=original["revision_id"])
    with pytest.raises(DBAPIError, match="memory_terminal_intent"):
        with engine.begin() as conn:
            conn.execute(MemoryRevision.__table__.insert().values(**original))
            conn.execute(MemoryUse.__table__.insert().values(**support))
            conn.execute(text("UPDATE memory_records SET current_version=3 WHERE id=:mid"),
                         {"mid": first.resource.memory_id})


@pytest.mark.parametrize("conditions", [None, {}, {"subject": "s", "applicability": "a"},
    {"subject": "", "applicability": "a", "effectiveFrom": None},
    {"subject": "s", "applicability": 42, "effectiveFrom": None},
    {"subject": "s", "applicability": "a", "effectiveFrom": "2026-99-99T00:00:00Z"},
    {"subject": "s", "applicability": "a", "effectiveFrom": None, "extra": "forbidden"}])
def test_insert_malformed_conditions_rejected(pg, conditions):
    engine, ctx, _ = pg
    first = command(engine, "remember", ctx, request(), statement())
    with engine.connect() as conn:
        original = dict(conn.execute(select(MemoryRevision.__table__)).mappings().one())
        support = dict(conn.execute(select(MemoryUse.__table__)).mappings().one())
    original.update(version=2, revision_id=str(uuid4()), conditions=conditions)
    support.update(id=str(uuid4()), consumer_revision_id=original["revision_id"])
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(MemoryRevision.__table__.insert().values(**original))
            conn.execute(MemoryUse.__table__.insert().values(**support))
            conn.execute(text("UPDATE memory_records SET current_version=2 WHERE id=:mid"),
                         {"mid": first.resource.memory_id})


def test_commit_ack_loss_reconciles_without_duplicate(pg):
    engine, ctx, _ = pg
    req = request()
    with Session(engine) as db:
        def lose_ack(session):
            raise ConnectionError("synthetic_post_commit_ack_loss")
        event.listen(db, "after_commit", lose_ack, once=True)
        with pytest.raises(ConnectionError, match="synthetic_post_commit_ack_loss"):
            MemoryCommands(db, WorkspaceAccess(db)).remember(ctx, req, statement())
    receipt = command(engine, "reconcile", ctx, req.request_id)
    assert receipt is not None
    assert command(engine, "remember", ctx, req, statement()) == receipt
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM memory_records")) == 1


def test_archive_blocks_all_private_management(pg):
    engine, ctx, _ = pg
    first = command(engine, "remember", ctx, request(), statement())
    with engine.begin() as conn:
        conn.execute(text("UPDATE workspaces SET archived_at=now()"))
    for method, args in (("read", (first.resource.memory_id,)),
                         ("history", (first.resource.memory_id,)),
                         ("delete", (request(), first.resource.memory_id, 1)),
                         ("reconcile", (first.request_id,))):
        with pytest.raises(AccessDenied):
            command(engine, method, ctx, *args)



def test_failed_delete_rolls_back_all_erasure(pg):
    engine, ctx, _ = pg
    first = command(engine, "remember", ctx, request(), statement(MARKER))
    with Session(engine) as db:
        def fail_commit(session):
            raise RuntimeError("synthetic_before_commit_failure")
        event.listen(db, "before_commit", fail_commit, once=True)
        with pytest.raises(RuntimeError, match="synthetic_before_commit_failure"):
            MemoryCommands(db, WorkspaceAccess(db)).delete(ctx, request(), first.resource.memory_id, 1)
    result = command(engine, "read", ctx, first.resource.memory_id)
    assert result.version == 1 and result.statement.conditions.subject == MARKER
    assert command(engine, "read_source", ctx, result.confirmation_source_id).content == statement().content


def test_shared_source_retained_until_last_dependent_erased(pg):
    engine, ctx, _ = pg
    a = command(engine, "remember", ctx, request(), statement("a"))
    b = command(engine, "remember", ctx, request(), statement("b"))
    with engine.begin() as conn:
        conn.execute(MemoryUse.__table__.insert().values(id=str(uuid4()), workspace_id=ctx.workspace_id,
            consumer_revision_id=b.resource.revision_id, source_id=a.resource.confirmation_source_id,
            use_mode="support", atom_key="extra", support_group="source", relation="supports"))
    command(engine, "delete", ctx, request(), a.resource.memory_id, 1)
    assert command(engine, "read_source", ctx, a.resource.confirmation_source_id).content == statement().content
    command(engine, "delete", ctx, request(), b.resource.memory_id, 1)
    with pytest.raises(SourceUnavailable):
        command(engine, "read_source", ctx, a.resource.confirmation_source_id)


def test_cross_owner_and_cross_workspace_support_sql_rejected(pg):
    engine, ctx, other = pg
    a = command(engine, "remember", ctx, request(), statement("a"))
    b = command(engine, "remember", replace(ctx, actor_user_id=other), request(), statement("b"))
    for workspace_id, source_id in ((ctx.workspace_id, b.resource.confirmation_source_id),
                                    (str(uuid4()), a.resource.confirmation_source_id)):
        with pytest.raises(DBAPIError):
            with engine.begin() as conn:
                conn.execute(MemoryUse.__table__.insert().values(id=str(uuid4()), workspace_id=workspace_id,
                    consumer_revision_id=a.resource.revision_id, source_id=source_id,
                    use_mode="support", atom_key="illegal", support_group="source", relation="supports"))



def test_frozen_t4_migration_matches_historical_catalog(pg_t4):
    from sqlalchemy import inspect
    engine,_,_=pg_t4
    frozen=json.dumps(MIGRATION.DDL,separators=(",",":"),ensure_ascii=False).encode()
    assert sha256(frozen).hexdigest()=="1a2114ae27b2a0097a165dbfa9ad12ade251464028d3500f180ba9d797b1ad2f"
    expected={'memory_instructions': {'id': False,
                             'workspace_id': False,
                             'actor_user_id': False,
                             'operation': False,
                             'request_id': False,
                             'target_memory_id': True,
                             'expected_version': True,
                             'content': True,
                             'content_sha256': True,
                             'created_at': False,
                             'erased_at': True},
     'memory_sources': {'id': False,
                        'workspace_id': False,
                        'kind': False,
                        'native_id': False,
                        'instruction_id': False,
                        'source_version': False,
                        'native_version': False,
                        'content_sha256': True,
                        'actor_user_id': False,
                        'audience': False,
                        'owner_user_id': False,
                        'state': False,
                        'created_at': False,
                        'invalidated_at': True},
     'memory_records': {'id': False,
                        'workspace_id': False,
                        'owner_user_id': False,
                        'scope_kind': False,
                        'visibility': False,
                        'current_version': False,
                        'supersedes_id': True,
                        'created_at': False},
     'memory_revisions': {'workspace_id': False,
                          'memory_id': False,
                          'version': False,
                          'revision_id': False,
                          'intent': False,
                          'validity': False,
                          'cause': False,
                          'kind': False,
                          'content': True,
                          'content_sha256': True,
                          'confirmation': False,
                          'confirmation_source_id': False,
                          'conditions': True,
                          'pinned': False,
                          'valid_until': True,
                          'instruction_id': False,
                          'created_at': False,
                          'erased_at': True},
     'memory_uses': {'id': False,
                     'workspace_id': False,
                     'consumer_revision_id': False,
                     'source_id': False,
                     'use_mode': False,
                     'atom_key': False,
                     'support_group': False,
                     'relation': False},
     'memory_operations': {'id': False,
                           'workspace_id': False,
                           'actor_user_id': False,
                           'request_id': False,
                           'method': False,
                           'path': False,
                           'key': False,
                           'request_sha256': False,
                           'state': False,
                           'resource_id': True,
                           'result_version': True,
                           'created_at': False,
                           'settled_at': True,
                           'http_status': True}}
    checks={'memory_instructions': ['ck_instruction_operation',
                             'ck_instruction_target',
                             'ck_instruction_payload'],
     'memory_operations': ['ck_memory_operation', 'ck_memory_operation_result'],
     'memory_records': ['ck_memory_record_scope'],
     'memory_revisions': ['ck_memory_revision_enums', 'ck_memory_revision_payload'],
     'memory_sources': ['ck_source_identity', 'ck_source_state', 'ck_source_native_version'],
     'memory_uses': ['ck_memory_use']}
    indexes={'memory_instructions': [],
     'memory_operations': [],
     'memory_records': [],
     'memory_revisions': [],
     'memory_sources': ['uq_memory_source_current'],
     'memory_uses': ['ix_memory_use_source']}
    catalog=inspect(engine)
    assert {name for name in catalog.get_table_names() if name.startswith("memory_")}==set(expected)
    for name,columns in expected.items():
        assert {c["name"]:c["nullable"] for c in catalog.get_columns(name)}==columns
        assert {c["name"] for c in catalog.get_check_constraints(name)}==set(checks[name])
        assert {i["name"] for i in catalog.get_indexes(name) if not i.get("duplicates_constraint")}==set(indexes[name])
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version"))=="t4b5c6d7e8f9"


def test_current_six_table_models_match_full_u5_chain(pg):
    from alembic.autogenerate import compare_metadata
    from sqlalchemy import inspect
    engine,_,_=pg
    def include(obj,name,type_,reflected,compare_to):
        return (name if type_=="table" else getattr(getattr(obj,"table",None),"name",None)) in MIGRATION.TABLES
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version"))=="u5c6d7e8f9a0"
        columns={c["name"] for c in inspect(conn).get_columns("memory_uses")}
        assert {"consumer_snapshot_id","consumer_call_id","consumer_call_part","used_snapshot_id","used_tool_call_id"} <= columns
        context=MigrationContext.configure(conn,opts={"include_object":include,"compare_type":True,"compare_server_default":True})
        assert compare_metadata(context,MemoryUse.metadata)==[]


def test_forged_revision_hash_rejected(pg):
    engine, ctx, _ = pg
    first = command(engine, "remember", ctx, request(), statement())
    with engine.connect() as conn:
        original = dict(conn.execute(select(MemoryRevision.__table__)).mappings().one())
    original.update(version=2, revision_id=str(uuid4()), content_sha256="0" * 64)
    with pytest.raises(DBAPIError, match="ck_memory_revision_payload"):
        with engine.begin() as conn:
            conn.execute(MemoryRevision.__table__.insert().values(**original))



@pytest.mark.parametrize("head_first", [False, True])
@pytest.mark.parametrize("terminal_action", ["deactivate", "correct", "delete"])
def test_intent_fence_independent_of_sql_write_order(pg, head_first, terminal_action):
    engine, ctx, _ = pg
    first = command(engine, "remember", ctx, request(), statement())
    with engine.connect() as conn:
        original = dict(conn.execute(select(MemoryRevision.__table__)).mappings().one())
        support = dict(conn.execute(select(MemoryUse.__table__)).mappings().one())
    args = (request(), first.resource.memory_id, 1)
    if terminal_action == "correct":
        args += (statement("successor"),)
    command(engine, terminal_action, ctx, *args)
    original.update(version=3, revision_id=str(uuid4()))
    support.update(id=str(uuid4()), consumer_revision_id=original["revision_id"])
    with pytest.raises(DBAPIError, match="memory_terminal_intent"):
        with engine.begin() as conn:
            def advance():
                conn.execute(text("UPDATE memory_records SET current_version=3 WHERE id=:mid"),
                             {"mid": first.resource.memory_id})
            if head_first:
                advance()
            conn.execute(MemoryRevision.__table__.insert().values(**original))
            conn.execute(MemoryUse.__table__.insert().values(**support))
            if not head_first:
                advance()
            conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))



def test_sqlite_native_fixtures_can_create_metadata_but_memory_commands_are_disabled():
    from citeframe_persistence import Base
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        with pytest.raises(ValueError, match="memory_requires_postgresql"):
            MemoryCommands(db, WorkspaceAccess(db))
    engine.dispose()
