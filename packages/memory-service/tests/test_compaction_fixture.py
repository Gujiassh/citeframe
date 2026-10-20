"""Full-chain PostgreSQL fixtures shared only by Issue43 tests."""
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]
PREVIOUS = "t4b5c6d7e8f9"
HEAD = "u5c6d7e8f9a0"


def migrate(engine, target, *, downgrade=False):
    config = Config()
    config.set_main_option("script_location", str(ROOT / "apps/api/alembic"))
    scripts = ScriptDirectory.from_config(config)
    revisions = scripts._downgrade_revs if downgrade else scripts._upgrade_revs
    with engine.begin() as connection:
        context = MigrationContext.configure(connection, opts={
            "fn": lambda current, _: revisions(target, current),
            "transactional_ddl": True,
        })
        with Operations.context(context):
            context.run_migrations()


@contextmanager
def disposable_database(target=HEAD):
    url = os.environ.get("CITEFRAME_MEMORY43_POSTGRES_URL")
    if not url and os.environ.get("CI"):
        pytest.fail("CI requires CITEFRAME_MEMORY43_POSTGRES_URL")
    if not url:
        pytest.skip("requires disposable citeframe_memory43_test database")
    assert make_url(url).database == "citeframe_memory43_test", "Refusing non-test database"
    schema = "memory43_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    try:
        with admin.begin() as connection:
            extensions = set(connection.execute(text("SELECT extname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE n.nspname='public'")).scalars())
            assert {"vector", "pg_trgm"} <= extensions, "Controller must provision public vector and pg_trgm extensions"
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, pool_size=8, connect_args={"options":
            f"-c search_path={schema},public -c lock_timeout=2000 -c statement_timeout=10000"})
        migrate(engine, target)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def pg43():
    with disposable_database() as engine:
        yield engine


@dataclass(frozen=True)
class ChatFixture:
    user_id: str
    other_user_id: str
    workspace_id: str
    other_workspace_id: str
    membership_id: str
    thread_id: str
    other_thread_id: str
    parent_id: str
    leaf_id: str


def insert_message(connection, scope, message_id, *, thread_id=None, parent_id=None, content="37.5 ms; never production; only batch=8"):
    connection.execute(text("""INSERT INTO chat_messages
        (id, workspace_id, thread_id, parent_message_id, role, content, status, created_at)
        VALUES (:id,:workspace,:thread,:parent,'user',:content,'completed',now())"""),
        {"id": message_id, "workspace": scope.workspace_id,
         "thread": thread_id or scope.thread_id, "parent": parent_id, "content": content})


def seed_chat(engine):
    scope = ChatFixture(*(str(uuid4()) for _ in range(9)))
    with engine.begin() as connection:
        for uid in (scope.user_id, scope.other_user_id):
            connection.execute(text("""INSERT INTO users
                (id,email,name,password_hash,avatar_url,created_at,updated_at)
                VALUES (:id,:email,'fixture','unused','',now(),now())"""),
                {"id": uid, "email": uid + "@test.invalid"})
        for wid in (scope.workspace_id, scope.other_workspace_id):
            connection.execute(text("""INSERT INTO workspaces
                (id,name,created_by_user_id,system_prompt,retrieval_top_k,chunk_size,created_at,updated_at)
                VALUES (:id,'fixture',:user,'fixture system',6,1200,now(),now())"""),
                {"id": wid, "user": scope.user_id})
        connection.execute(text("""INSERT INTO workspace_memberships
            (id,workspace_id,user_id,role,created_at) VALUES (:id,:workspace,:user,'owner',now())"""),
            {"id": scope.membership_id, "workspace": scope.workspace_id, "user": scope.user_id})
        for tid in (scope.thread_id, scope.other_thread_id):
            connection.execute(text("""INSERT INTO chat_threads
                (id,workspace_id,created_by_user_id,title,last_message_at,created_at,updated_at)
                VALUES (:id,:workspace,:user,'fixture',now(),now(),now())"""),
                {"id": tid, "workspace": scope.workspace_id, "user": scope.user_id})
        insert_message(connection, scope, scope.parent_id)
        insert_message(connection, scope, scope.leaf_id, parent_id=scope.parent_id)
        connection.execute(text("UPDATE chat_threads SET active_message_id=:leaf WHERE id=:id"),
                           {"leaf": scope.leaf_id, "id": scope.thread_id})
    return scope

