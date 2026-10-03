"""Real SQL storage oracles; no issuer, registry service, migration or endpoint."""
from datetime import UTC, datetime
from hashlib import sha256
import json
from copy import deepcopy
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, StatementError
from sqlalchemy.orm import Session

from citeframe_persistence.base import Base
from citeframe_persistence.models import User, Workspace
from citeframe_persistence.models.memory import MemorySource
from citeframe_persistence.models.memory_index import (
    manifests, entries, CHUNKING, LEXICAL, source_set_bytes, profile_bytes,
    lexical_config_fingerprint,
)


@pytest.fixture(scope="module")
def pg():
    url = os.environ.get("CITEFRAME_HISTORY42_INDEX_POSTGRES_URL")
    if not url:
        pytest.fail("CITEFRAME_HISTORY42_INDEX_POSTGRES_URL required; no skip")
    parsed = make_url(url)
    assert parsed.database == "citeframe_history42_index_test"
    assert parsed.host in ("127.0.0.1", "localhost")
    schema = "history42_index_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    try:
        with admin.begin() as conn:
            assert 170000 <= int(conn.execute(text("SHOW server_version_num")).scalar_one()) < 180000
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public"))
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-c search_path={schema},public -c statement_timeout=15000 -c lock_timeout=1000"})
        Base.metadata.create_all(engine)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def db(pg):
    with pg.connect() as conn:
        transaction = conn.begin()
        try:
            with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
                yield session
        finally:
            transaction.rollback()


def seed(db):
    user = User(id=str(uuid4()), email=str(uuid4())+"@test.invalid", name="fixture",
                password_hash="unused", avatar_url="")
    db.add(user)
    db.flush()
    workspaces = [Workspace(id=str(uuid4()), name="fixture", created_by_user_id=user.id) for _ in range(2)]
    db.add_all(workspaces)
    db.flush()
    body = "历史证据 exact original 😀e\u0301\r\n"
    digest = sha256(body.encode()).hexdigest()
    native_id = str(uuid4())
    source = MemorySource(id=str(uuid4()), workspace_id=workspaces[0].id, kind="chat_message",
                          native_id=native_id, instruction_id=None, source_version=1,
                          native_version={"messageId": native_id, "parentMessageId": None,
                                          "role": "user", "status": "completed",
                                          "contentSha256": digest, "compactionRevision": 1},
                          content_sha256=digest, actor_user_id=None, audience="workspace",
                          owner_user_id=None, state="current", created_at=datetime.now(UTC))
    db.add(source)
    db.flush()
    return workspaces[0].id, workspaces[1].id, source.id, body, digest


def profile(mode="lexical"):
    return dict(schemaVersion="history-index-profile-v1", mode=mode, space="history_text",
                chunking=deepcopy(CHUNKING), lexical=deepcopy(LEXICAL),
                embedding=None if mode=="lexical" else
                dict(provider="synthetic", model="sql-plumbing", modelVersion="1",
                     dimensions=1024, configFingerprint="b"*64))


def member(source, digest, count=1, version=1):
    return dict(source_id=source, version=version, sha256=digest, chunk_count=count)


def manifest_values(workspace, *, source=None, digest=None, count=1, **changes):
    value = dict(id=str(uuid4()), workspace_id=workspace, owner_user_id=None,
                 audience="workspace", source_kind="chat_message", corpus_scope="workspace",
                 generation=1, retrieval_mode="lexical", profile_fingerprint="a"*64,
                 source_set=[], source_set_sha256=sha256(b"[]").hexdigest(), state="building",
                 created_at=datetime.now(UTC), activated_at=None)
    if source is not None:
        value["source_set"] = [member(source,digest,count)]
        value["source_set_sha256"] = sha256(source_set_bytes(value["source_set"])).hexdigest()
    value["profile_snapshot"] = profile("hybrid" if changes.get("retrieval_mode")=="hybrid" else "lexical")
    value["profile_fingerprint"] = sha256(profile_bytes(value["profile_snapshot"])).hexdigest()
    value.update(changes)
    return value


def entry_values(workspace, manifest, source, body, digest, **changes):
    value = dict(id=str(uuid4()), workspace_id=workspace, manifest_id=manifest, source_id=source,
                 chunk_ordinal=0, start_cp=0, end_cp=len(body), text_content=body,
                 text_sha256=digest, source_version=1, source_sha256=digest, index_generation=1,
                 embedding_space="history_text", provider=None, model=None, model_version=None,
                 dimensions=None, config_fingerprint=lexical_config_fingerprint(), embedding=None, state="lexical_ready",
                 created_at=datetime.now(UTC))
    value.update(changes)
    return value


def rejects(db, statement):
    with pytest.raises((DBAPIError, StatementError)):
        with db.begin_nested():
            db.execute(statement)
            db.flush()


def test_actual_index_ddl(db):
    definitions = dict(db.execute(text(
        "SELECT indexname,indexdef FROM pg_indexes WHERE schemaname=current_schema() "
        "AND tablename IN ('memory_index_entries','memory_index_manifests')")).all())
    assert "USING gin" in definitions["ix_memory_index_entry_fts"]
    assert "USING gist" in definitions["ix_memory_index_entry_trgm"]
    assert "vector_cosine_ops" in definitions["ix_memory_index_entry_embedding"]
    assert "ready" in definitions["ix_memory_index_entry_embedding"]
    assert "owner_user_id IS NULL" in definitions["uq_memory_index_manifest_active"]


def test_workspace_composite_foreign_keys(db):
    workspace, other, source, body, digest = seed(db)
    first = manifest_values(workspace)
    second = manifest_values(other)
    db.execute(manifests.insert(), [first, second])
    rejects(db, entries.insert().values(**entry_values(other, first["id"], source, body, digest)))
    rejects(db, entries.insert().values(**entry_values(other, second["id"], source, body, digest)))


@pytest.mark.parametrize("changes", [
    {"audience": "private"}, {"owner_user_id": str(uuid4())},
    {"corpus_scope": "current_branch"}, {"source_kind": "memory_instruction"},
    {"generation": 0}, {"retrieval_mode": "guessed"},
    {"state": "active"}, {"state": "failed", "activated_at": datetime.now(UTC)},
])
def test_manifest_local_guards(db, changes):
    workspace, *_ = seed(db)
    rejects(db, manifests.insert().values(**manifest_values(workspace, **changes)))


def test_active_uniqueness(db):
    workspace, *_ = seed(db)
    first = manifest_values(workspace, state="active", activated_at=datetime.now(UTC))
    db.execute(manifests.insert().values(**first))
    rejects(db, manifests.insert().values(**manifest_values(workspace, generation=2,
            state="active", activated_at=datetime.now(UTC))))


@pytest.mark.parametrize("changes", [
    {"end_cp": 1}, {"start_cp": -1}, {"chunk_ordinal": -1},
    {"text_sha256": "b"*64}, {"source_version": 0}, {"index_generation": 0},
    {"embedding_space": "memory_text"}, {"state": "ready"},
    {"provider": "fixture"}, {"dimensions": 1024},
])
def test_entry_local_guards(db, changes):
    workspace, _, source, body, digest = seed(db)
    manifest = manifest_values(workspace,source=source,digest=digest)
    db.execute(manifests.insert().values(**manifest))
    rejects(db, entries.insert().values(**entry_values(workspace, manifest["id"], source, body, digest, **changes)))


def test_exact_unicode_and_hash(db):
    workspace, _, source, body, digest = seed(db)
    manifest = manifest_values(workspace,source=source,digest=digest)
    db.execute(manifests.insert().values(**manifest))
    value = entry_values(workspace, manifest["id"], source, body, digest)
    db.execute(entries.insert().values(**value))
    row = db.execute(text("SELECT text_content,char_length(text_content),text_sha256 "
                          "FROM memory_index_entries WHERE id=:id"), {"id":value["id"]}).one()
    assert row == (body, len(body), digest)


@pytest.mark.parametrize("changes", [
    {"profile_fingerprint": "b"*64}, {"generation": 2},
    {"source_set": [{"changed": True}]}, {"source_set_sha256": "c"*64},
    {"activated_at": None}, {"retrieval_mode": "hybrid"},
])
def test_activated_manifest_immutable_even_after_retirement(db, changes):
    workspace, *_ = seed(db)
    value = manifest_values(workspace, state="active", activated_at=datetime.now(UTC))
    db.execute(manifests.insert().values(**value))
    db.execute(manifests.update().where(manifests.c.id==value["id"]).values(state="retired"))
    rejects(db, manifests.update().where(manifests.c.id==value["id"]).values(**changes))


@pytest.mark.parametrize("changes", [
    {"chunk_ordinal": 1}, {"config_fingerprint": "b"*64}, {"source_version": 2},
    {"text_content": "changed", "text_sha256": sha256(b"changed").hexdigest(), "end_cp": 7},
])
def test_entry_identity_immutable(db, changes):
    workspace, _, source, body, digest = seed(db)
    manifest = manifest_values(workspace,source=source,digest=digest)
    db.execute(manifests.insert().values(**manifest))
    value = entry_values(workspace, manifest["id"], source, body, digest)
    db.execute(entries.insert().values(**value))
    rejects(db, entries.update().where(entries.c.id==value["id"]).values(**changes))


@pytest.mark.parametrize("vector", ["zero", "short", "nan", "infinity"])
def test_hybrid_ready_rejects_invalid_vectors(db, vector):
    workspace, _, source, body, digest = seed(db)
    manifest = manifest_values(workspace,source=source,digest=digest,retrieval_mode="hybrid")
    db.execute(manifests.insert().values(**manifest))
    value = entry_values(workspace, manifest["id"], source, body, digest, state="ready",
                         provider="synthetic", model="sql-plumbing", model_version="1", dimensions=1024, config_fingerprint="b"*64)
    # Cast through real SQL to test pgvector rather than client-side validation.
    value["embedding"] = None
    value["state"] = "pending"
    db.execute(entries.insert().values(**value))
    raw = ("["+",".join(["0"]*1024)+"]" if vector=="zero" else "[1,2]" if vector=="short"
           else "["+("NaN" if vector=="nan" else "Infinity")+","+",".join(["1"]*1023)+"]")
    rejects(db, text("UPDATE memory_index_entries SET state='ready',embedding=CAST(:v AS vector) WHERE id=:id")
            .bindparams(v=raw,id=value["id"]))


def test_synthetic_vector_sql_readiness_only(db):
    workspace, _, source, body, digest = seed(db)
    manifest = manifest_values(workspace,source=source,digest=digest,retrieval_mode="hybrid")
    db.execute(manifests.insert().values(**manifest))
    value = entry_values(workspace, manifest["id"], source, body, digest, state="ready",
                         provider="synthetic", model="sql-plumbing", model_version="1", dimensions=1024, config_fingerprint="b"*64,
                         embedding=[1.0]+[0.0]*1023)
    db.execute(entries.insert().values(**value))
    assert db.execute(text("SELECT vector_dims(embedding),vector_norm(embedding) "
                           "FROM memory_index_entries WHERE id=:id"),{"id":value["id"]}).one()==(1024,1.0)


def test_real_simple_fts_trigram_unicode_rrf_sql(db):
    workspace, _, source, body, digest = seed(db)
    body = "历史证据 exact alpha".ljust(1000) + "history lexical beta".ljust(1000) + "历史证据 exact gamma".ljust(300)
    digest = sha256(body.encode()).hexdigest()
    native = db.get(MemorySource, source)
    native.content_sha256 = digest
    native.native_version = {**native.native_version, "contentSha256": digest}
    db.flush()
    manifest = manifest_values(workspace,source=source,digest=digest,count=3)
    db.execute(manifests.insert().values(**manifest))
    for ordinal in range(3):
        payload = body[ordinal*1000:ordinal*1000+1200]
        value = entry_values(workspace,manifest["id"],source,payload,sha256(payload.encode()).hexdigest(),
                             source_sha256=digest,chunk_ordinal=ordinal,
                             start_cp=ordinal*1000,end_cp=ordinal*1000+len(payload))
        db.execute(entries.insert().values(**value))
    db.execute(manifests.update().where(manifests.c.id==manifest["id"])
               .values(state="active",activated_at=datetime.now(UTC)))
    db.execute(text("SET LOCAL pg_trgm.word_similarity_threshold=0.3"))
    query = text("""
    WITH eligible AS (
      SELECT e.* FROM memory_index_entries e JOIN memory_index_manifests m
        ON (m.workspace_id,m.id)=(e.workspace_id,e.manifest_id)
      JOIN memory_sources s ON (s.workspace_id,s.id)=(e.workspace_id,e.source_id)
        AND s.kind=m.source_kind AND s.state='current' AND s.audience='workspace'
        AND s.owner_user_id IS NULL AND s.source_version=e.source_version AND s.content_sha256=e.source_sha256
      WHERE e.workspace_id=:wid AND m.state='active' AND e.state='lexical_ready'
        AND m.retrieval_mode='lexical' AND e.source_id=:sid
    ), fts AS (
      SELECT source_id,chunk_ordinal,row_number() OVER
        (ORDER BY ts_rank(search_vector,plainto_tsquery('simple',:q)) DESC,source_id,chunk_ordinal) AS rank
      FROM eligible WHERE search_vector @@ plainto_tsquery('simple',:q)
      ORDER BY rank LIMIT 100
    ), trgm AS (
      SELECT source_id,chunk_ordinal,row_number() OVER
        (ORDER BY word_similarity(:q,text_content) DESC,source_id,chunk_ordinal) AS rank
      FROM eligible WHERE :q <% text_content ORDER BY rank LIMIT 100
    ), combined AS (
      SELECT source_id,chunk_ordinal,sum(1.0/(60+rank)) AS score FROM
      (SELECT * FROM fts UNION ALL SELECT * FROM trgm) hits GROUP BY source_id,chunk_ordinal
    ), collapsed AS (
      SELECT *,row_number() OVER(PARTITION BY source_id ORDER BY score DESC,chunk_ordinal) AS best
      FROM combined
    )
    SELECT source_id,chunk_ordinal,score FROM collapsed WHERE best=1
    ORDER BY score DESC,source_id,chunk_ordinal LIMIT 6
    """)
    rows = db.execute(query,{"wid":workspace,"sid":source,"q":"历史证据"}).all()
    assert len(rows)==1 and rows[0][:2]==(source,0)
    assert float(rows[0][2])==pytest.approx(1/61)
    # This disposable cluster's C locale indexes the CJK FTS token, but no CJK trigrams.
    assert db.execute(text("SELECT show_trgm('历史证据')")).scalar_one()==[]
    rows = db.execute(query,{"wid":workspace,"sid":source,"q":"exact"}).all()
    assert len(rows)==1 and float(rows[0][2])==pytest.approx(2/61)
    rows = db.execute(query,{"wid":workspace,"sid":source,"q":"lex"}).all()
    assert len(rows)==1 and rows[0][1]==0 and float(rows[0][2])==pytest.approx(1/61)
    db.execute(manifests.update().where(manifests.c.id==manifest["id"]).values(state="retired"))
    assert db.execute(query,{"wid":workspace,"sid":source,"q":"历史证据"}).all()==[]


def test_explicit_import_adds_only_two_tables_and_preserves_native_ddl():
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    code = """
import citeframe_persistence.models
from citeframe_persistence.base import Base
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects.postgresql import dialect
def snapshot():
    return {name: (str(CreateTable(table).compile(dialect=dialect())),
                   sorted(str(CreateIndex(index).compile(dialect=dialect())) for index in table.indexes))
            for name,table in Base.metadata.tables.items()}
before=snapshot()
import citeframe_persistence.models.memory_index
after=snapshot()
assert set(after)-set(before)=={'memory_index_manifests','memory_index_entries'}
assert all(after[name]==value for name,value in before.items())
assert not hasattr(citeframe_persistence.models,'MemoryIndexManifest')
print('native-ddl-unchanged',len(before),'new-tables',2)
"""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": os.pathsep.join(str(root/"packages"/name/"src") for name in
                                         ("backend-persistence","backend-contracts"))}
    result = subprocess.run([sys.executable,"-B","-c",code],env=env,text=True,capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "native-ddl-unchanged" in result.stdout


def raw_manifest(db, values):
    values = dict(values)
    for key in ("source_set","profile_snapshot"):
        values[key] = json.dumps(values[key], ensure_ascii=False, separators=(",",":"))
    columns = ",".join(values)
    parameters = ",".join(f"CAST(:{key} AS jsonb)" if key in ("source_set","profile_snapshot") else f":{key}" for key in values)
    return db.execute(text(f"INSERT INTO memory_index_manifests ({columns}) VALUES ({parameters})"),values)


def raw_rejects(db, values):
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            raw_manifest(db,values)


def ready_manifest(db, *, mode="lexical", state="lexical_ready", body_override=None):
    workspace, other, source, body, digest = seed(db)
    if body_override is not None:
        body = body_override
        digest = sha256(body.encode()).hexdigest()
        native = db.get(MemorySource,source)
        native.content_sha256 = digest
        native.native_version = {**native.native_version,"contentSha256":digest}
        db.flush()
    count = 0 if not body else max(1,(max(0,len(body)-1200)+999)//1000+1)
    value = manifest_values(workspace,source=source,digest=digest,count=count,retrieval_mode=mode)
    db.execute(manifests.insert().values(**value))
    for ordinal in range(count):
        part = body[ordinal*1000:ordinal*1000+1200]
        changes = dict(start_cp=ordinal*1000,end_cp=ordinal*1000+len(part),chunk_ordinal=ordinal,state=state)
        if mode=="hybrid":
            changes.update(provider="synthetic",model="sql-plumbing",model_version="1",dimensions=1024,
                           config_fingerprint="b"*64,embedding=[1.0]+[0.0]*1023 if state=="ready" else None)
        db.execute(entries.insert().values(**entry_values(workspace,value["id"],source,part,
                       sha256(part.encode()).hexdigest(),source_sha256=digest,**changes)))
    return value,source


def activate(db, mid):
    db.execute(manifests.update().where(manifests.c.id==mid).values(state="active",activated_at=datetime.now(UTC)))


def test_canonical_golden_python_sql(db):
    sources=[member("00000000-0000-0000-0000-000000000001","0"*64,0)]
    expected=[
        ([],source_set_bytes,2,"4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"),
        (sources,source_set_bytes,158,"9c12d08632627dd760071d3c3bebee12c4b3b0046c860a03103d1b813ee19fdb"),
        (profile(),profile_bytes,282,"2f42a80b403af92d175741eaa978ed0ebce028f362c5a0c5fe17fef53dde2538"),
    ]
    for value,encode,length,digest in expected:
        actual=encode(value)
        assert len(actual)==length and sha256(actual).hexdigest()==digest
        sql=db.execute(text("SELECT memory_index_canonical(CAST(:v AS jsonb))"),{"v":json.dumps(value)}).scalar_one()
        assert sql.encode()==actual
    assert lexical_config_fingerprint()=="e2f53590c07283726955744f0da86cdda46344cd59e36b0012b437aedfd34947"
    assert lexical_config_fingerprint()!=sha256(profile_bytes(profile())).hexdigest()


@pytest.mark.parametrize("label", ['quote"slash\\', "line\n\t\b\f\r", "中文😀e\u0301", "\u0001\u001f", "/"])
def test_profile_unicode_escaping_both_canonical_hashes(db,label):
    value=profile("hybrid")
    value["embedding"]["model"]=label
    expected=profile_bytes(value)
    row=db.execute(text("SELECT memory_index_canonical(CAST(:v AS jsonb)),"
                        "encode(sha256(convert_to(memory_index_canonical(CAST(:v AS jsonb)),'UTF8')),'hex')"),
                   {"v":json.dumps(value,ensure_ascii=False)}).one()
    assert row[0].encode()==expected and row[1]==sha256(expected).hexdigest()
    workspace,*_=seed(db)
    raw_manifest(db,manifest_values(workspace,retrieval_mode="hybrid",
                 profile_snapshot=value,profile_fingerprint=sha256(expected).hexdigest()))


@pytest.mark.parametrize("key,number", [
    ("version",True),("version",1.0),("version",0),("version",-1),
    ("version",9223372036854775808),("chunk_count",True),("chunk_count",0.0),
    ("chunk_count",-1),("chunk_count",2147483648),
])
def test_application_integer_layer_rejects(key,number):
    sources=[member("00000000-0000-0000-0000-000000000001","0"*64,0)]
    sources[0][key]=number
    with pytest.raises(ValueError):
        source_set_bytes(sources)


@pytest.mark.parametrize("token,valid", [
    ("1",True),("1.0",True),("1e0",True),("true",False),("1.5",False),
    ("0",False),("-1",False),("9223372036854775807",True),("9223372036854775808",False),
])
def test_direct_jsonb_integer_value_layer(db,token,valid):
    raw='[{"source_id":"00000000-0000-0000-0000-000000000001","sha256":"'+"0"*64+'","version":'+token+',"chunk_count":0}]'
    result=db.execute(text("SELECT memory_index_sources_valid(CAST(:v AS jsonb))"),{"v":raw}).scalar_one()
    assert result is valid
    if valid:
        encoded=db.execute(text("SELECT memory_index_canonical(CAST(:v AS jsonb))"),{"v":raw}).scalar_one()
        normalized=json.loads(raw)
        normalized[0]["version"]=int(normalized[0]["version"])
        assert encoded.encode()==source_set_bytes(normalized)


@pytest.mark.parametrize("token,valid", [
    ("0",True),("-0.0",True),("1e0",True),("2147483647",True),
    ("2147483648",False),("-1",False),("0.5",False),("false",False),
])
def test_direct_jsonb_chunk_count_domain(db,token,valid):
    raw='[{"source_id":"00000000-0000-0000-0000-000000000001","sha256":"'+"0"*64+'","version":1,"chunk_count":'+token+'}]'
    assert db.execute(text("SELECT memory_index_sources_valid(CAST(:v AS jsonb))"),{"v":raw}).scalar_one() is valid


@pytest.mark.parametrize("kind", ["null","object","duplicate","unordered","extra","missing","uppercase","bad_hash"])
def test_source_set_shape_sql_admission(db,kind):
    first=member("00000000-0000-0000-0000-000000000001","0"*64)
    second=member("00000000-0000-0000-0000-000000000002","1"*64)
    value=[first]
    if kind=="null": value=None
    if kind=="object": value={}
    if kind=="duplicate": value=[first,first]
    if kind=="unordered": value=[second,first]
    if kind=="extra": first["unexpected"]=1
    if kind=="missing": del first["version"]
    if kind=="uppercase": first["source_id"]="AAAAAAAA-0000-0000-0000-000000000001"
    if kind=="bad_hash": first["sha256"]="not-a-hash"
    workspace,*_=seed(db)
    raw_rejects(db,manifest_values(workspace,source_set=value))


def test_source_set_count_and_byte_bounds(db):
    values=[member(str(__import__("uuid").UUID(int=i+1)),"0"*64,2147483647,9223372036854775807) for i in range(4096)]
    encoded=source_set_bytes(values)
    assert len(encoded)<1048576
    assert db.execute(text("SELECT memory_index_sources_valid(CAST(:v AS jsonb))"),
                      {"v":encoded.decode()}).scalar_one() is True
    assert db.execute(text("SELECT memory_index_canonical(CAST(:v AS jsonb))"),
                      {"v":encoded.decode()}).scalar_one().encode()==encoded
    values.append(member(str(__import__("uuid").UUID(int=4097)),"0"*64))
    with pytest.raises(ValueError): source_set_bytes(values)
    assert db.execute(text("SELECT memory_index_sources_valid(CAST(:v AS jsonb))"),
                      {"v":json.dumps(values)}).scalar_one() is False
    oversized=[member("00000000-0000-0000-0000-000000000001","x"*1048577)]
    with pytest.raises(ValueError): source_set_bytes(oversized)
    assert db.execute(text("SELECT memory_index_sources_valid(CAST(:v AS jsonb))"),
                      {"v":json.dumps(oversized)}).scalar_one() is False


@pytest.mark.parametrize("change", ["missing","extra","null","mode","version","space","size","threshold","embedding","dimension"])
def test_profile_shape_sql_rejects(db,change):
    value=profile()
    if change=="missing": del value["lexical"]
    elif change=="extra": value["extra"]=True
    elif change=="null": value["chunking"]=None
    elif change=="mode": value["mode"]="fallback"
    elif change=="version": value["schemaVersion"]="unknown"
    elif change=="space": value["space"]="memory_text"
    elif change=="size": value["chunking"]["size"]=True
    elif change=="threshold": value["lexical"]["trgmThreshold"]=0.3
    elif change=="embedding": value["embedding"]={}
    elif change=="dimension":
        value=profile("hybrid")
        value["embedding"]["dimensions"]=1023
    workspace,*_=seed(db)
    raw_rejects(db,manifest_values(workspace,profile_snapshot=value))


def test_profile_fixed_numeric_layering(db):
    value=profile("hybrid")
    value["chunking"]["size"]=1200.0
    value["embedding"]["dimensions"]=1024.0
    with pytest.raises(ValueError): profile_bytes(value)
    normal=profile("hybrid")
    workspace,*_=seed(db)
    raw_manifest(db,manifest_values(workspace,retrieval_mode="hybrid",profile_snapshot=value,
                 profile_fingerprint=sha256(profile_bytes(normal)).hexdigest()))
    assert db.execute(text("SELECT memory_index_canonical(CAST(:v AS jsonb))"),
                      {"v":json.dumps(value)}).scalar_one().encode()==profile_bytes(normal)


@pytest.mark.parametrize("invalid", ["\x00","\ud800"])
def test_application_profile_unrepresentable_text_rejects(invalid):
    value=profile("hybrid")
    value["embedding"]["model"]=invalid
    with pytest.raises(ValueError): profile_bytes(value)


@pytest.mark.parametrize("field", ["source_set_sha256","profile_fingerprint"])
def test_spaced_json_hash_and_wrong_hash_reject(db,field):
    workspace,_,source,_,digest=seed(db)
    value=manifest_values(workspace,source=source,digest=digest)
    payload=value["source_set" if field=="source_set_sha256" else "profile_snapshot"]
    value[field]=sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    raw_rejects(db,value)


@pytest.mark.parametrize("changes", [
    {"index_generation":2},{"source_version":2},{"source_sha256":"c"*64},
    {"chunk_ordinal":1},{"start_cp":1},{"config_fingerprint":"a"*64},
    {"config_fingerprint":"2f42a80b403af92d175741eaa978ed0ebce028f362c5a0c5fe17fef53dde2538"},
    {"provider":"synthetic","model":"sql-plumbing","model_version":"1","dimensions":1024,
     "config_fingerprint":"b"*64,"state":"pending"},
])
def test_relational_entry_guards(db,changes):
    workspace,_,source,body,digest=seed(db)
    value=manifest_values(workspace,source=source,digest=digest)
    db.execute(manifests.insert().values(**value))
    rejects(db,entries.insert().values(**entry_values(workspace,value["id"],source,body,digest,**changes)))


@pytest.mark.parametrize("change", ["kind","version","hash","unavailable","membership"])
def test_source_metadata_and_membership_guards(db,change):
    workspace,_,source,body,digest=seed(db)
    value=manifest_values(workspace,source=source,digest=digest)
    if change=="kind": value["source_kind"]="note"
    elif change=="version": value["source_set"][0]["version"]=2
    elif change=="hash": value["source_set"][0]["sha256"]="c"*64
    elif change=="membership": value["source_set"]=[]
    elif change=="unavailable":
        db.execute(text("UPDATE memory_sources SET state='unavailable' WHERE id=:id"),{"id":source})
    value["source_set_sha256"]=sha256(source_set_bytes(value["source_set"])).hexdigest()
    db.execute(manifests.insert().values(**value))
    rejects(db,entries.insert().values(**entry_values(workspace,value["id"],source,body,digest)))
    if change!="membership":
        rejects(db,manifests.update().where(manifests.c.id==value["id"]).values(state="active",activated_at=datetime.now(UTC)))


@pytest.mark.parametrize("mode,state", [("lexical","pending"),("lexical","retired"),("hybrid","pending")])
def test_activation_requires_ready_entries(db,mode,state):
    value,_=ready_manifest(db,mode=mode,state=state)
    rejects(db,manifests.update().where(manifests.c.id==value["id"]).values(state="active",activated_at=datetime.now(UTC)))


def test_activation_missing_extra_ordinals_and_active_dml(db):
    value,source=ready_manifest(db,body_override="x"*2300)
    original=db.execute(entries.select().where(entries.c.manifest_id==value["id"]).order_by(entries.c.chunk_ordinal)).mappings().all()
    db.execute(entries.delete().where(entries.c.id==original[1]["id"]))
    rejects(db,manifests.update().where(manifests.c.id==value["id"]).values(state="active",activated_at=datetime.now(UTC)))
    restored=dict(original[1]);restored.pop("search_vector")
    db.execute(entries.insert().values(**restored))
    activate(db,value["id"])
    rejects(db,entries.delete().where(entries.c.id==original[0]["id"]))
    rejects(db,entries.update().where(entries.c.id==original[0]["id"]).values(state="retired"))
    extra=dict(restored);extra.update(id=str(uuid4()),chunk_ordinal=3,start_cp=3000,end_cp=4200)
    rejects(db,entries.insert().values(**extra))
    assert db.execute(text("SELECT count(*) FROM memory_index_entries WHERE manifest_id=:id"),{"id":value["id"]}).scalar_one()==3


@pytest.mark.parametrize("mutation", ["profile","source_set","generation","mode"])
def test_building_manifest_revalidates_existing_entries(db,mutation):
    value,_=ready_manifest(db)
    changes={}
    if mutation=="source_set": changes=dict(source_set=[],source_set_sha256=sha256(b"[]").hexdigest())
    elif mutation=="generation": changes=dict(generation=2)
    elif mutation=="mode":
        p=profile("hybrid")
        changes=dict(retrieval_mode="hybrid",profile_snapshot=p,profile_fingerprint=sha256(profile_bytes(p)).hexdigest())
    else:
        value,_=ready_manifest(db,mode="hybrid",state="ready")
        p=profile("hybrid");p["embedding"]["configFingerprint"]="c"*64
        changes=dict(profile_snapshot=p,profile_fingerprint=sha256(profile_bytes(p)).hexdigest())
    rejects(db,manifests.update().where(manifests.c.id==value["id"]).values(**changes))


def test_zero_chunk_and_profile_immutability(db):
    value,_=ready_manifest(db,body_override="")
    activate(db,value["id"])
    assert db.execute(text("SELECT count(*) FROM memory_index_entries WHERE manifest_id=:id"),{"id":value["id"]}).scalar_one()==0
    db.execute(manifests.update().where(manifests.c.id==value["id"]).values(state="retired"))
    p=profile("hybrid")
    rejects(db,manifests.update().where(manifests.c.id==value["id"]).values(
        profile_snapshot=p,profile_fingerprint=sha256(profile_bytes(p)).hexdigest(),retrieval_mode="hybrid"))


@pytest.mark.parametrize("mutation", ["insert","delete","pending","profile","source"])
def test_real_concurrent_mutation_blocks_activation(pg,mutation):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    with Session(pg) as db,db.begin():
        value,source=ready_manifest(db,body_override="x"*2200)
        rows=db.execute(entries.select().where(entries.c.manifest_id==value["id"])
                        .order_by(entries.c.chunk_ordinal)).mappings().all()
        last=dict(rows[-1]);last.pop("search_vector")
        if mutation=="insert":
            db.execute(entries.delete().where(entries.c.id==last["id"]))
    locked,release=Event(),Event()

    def writer():
        with pg.begin() as conn:
            if mutation=="insert": conn.execute(entries.insert().values(**last))
            elif mutation=="delete": conn.execute(entries.delete().where(entries.c.id==last["id"]))
            elif mutation=="pending": conn.execute(entries.update().where(entries.c.id==last["id"]).values(state="pending"))
            elif mutation=="profile":
                conn.execute(entries.delete().where(entries.c.manifest_id==value["id"]))
                p=profile("hybrid")
                conn.execute(manifests.update().where(manifests.c.id==value["id"]).values(
                    retrieval_mode="hybrid",profile_snapshot=p,profile_fingerprint=sha256(profile_bytes(p)).hexdigest()))
            else:
                conn.execute(text("UPDATE memory_sources SET state='stale' WHERE id=:id"),{"id":source})
            locked.set()
            assert release.wait(10), "writer_release_timeout"

    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(writer)
        try:
            assert locked.wait(10), "writer_did_not_lock"
            with pytest.raises(DBAPIError) as caught:
                with pg.begin() as conn:
                    conn.execute(manifests.update().where(manifests.c.id==value["id"]).values(
                        state="active",activated_at=datetime.now(UTC)))
            assert caught.value.orig.sqlstate=="55P03"
        finally:
            release.set()
        future.result(timeout=10)
    with Session(pg) as db,db.begin():
        if mutation=="insert":
            activate(db,value["id"])
        else:
            rejects(db,manifests.update().where(manifests.c.id==value["id"]).values(
                state="active",activated_at=datetime.now(UTC)))


def test_real_atomic_corpus_replacement_and_competing_activation(pg):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    with Session(pg) as db,db.begin():
        first,source=ready_manifest(db)
        activate(db,first["id"])
        prototype=dict(db.execute(entries.select().where(entries.c.manifest_id==first["id"])).mappings().one())
        prototype.pop("search_vector")
        others=[]
        for generation in (2,3):
            value=dict(first,id=str(uuid4()),generation=generation)
            db.execute(manifests.insert().values(**value))
            chunk=dict(prototype,id=str(uuid4()),manifest_id=value["id"],index_generation=generation)
            db.execute(entries.insert().values(**chunk))
            others.append(value)
    locked,release=Event(),Event()

    def replace_corpus():
        with Session(pg) as db,db.begin():
            db.execute(manifests.update().where(manifests.c.id==first["id"]).values(state="retired"))
            activate(db,others[0]["id"])
            locked.set()
            assert release.wait(10)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(replace_corpus)
        try:
            assert locked.wait(10)
            with pg.connect() as conn:
                # Other transactions see the old committed corpus until replacement commits.
                assert conn.execute(text("SELECT id FROM memory_index_manifests WHERE workspace_id=:w AND state='active'"),
                                    {"w":first["workspace_id"]}).scalars().all()==[first["id"]]
            with pytest.raises(DBAPIError) as caught:
                with Session(pg) as db,db.begin():
                    activate(db,others[1]["id"])
            assert caught.value.orig.sqlstate=="55P03"
        finally:
            release.set()
        future.result(timeout=10)
    with Session(pg) as db,db.begin():
        assert db.execute(text("SELECT id FROM memory_index_manifests WHERE workspace_id=:w AND state='active'"),
                          {"w":first["workspace_id"]}).scalars().all()==[others[0]["id"]]
        rejects(db,manifests.update().where(manifests.c.id==others[1]["id"]).values(
            state="active",activated_at=datetime.now(UTC)))
        # Failed replacement rolls back retirement too.
        with pytest.raises(DBAPIError):
            with db.begin_nested():
                db.execute(manifests.update().where(manifests.c.id==others[0]["id"]).values(state="retired"))
                db.execute(entries.delete().where(entries.c.manifest_id==others[1]["id"]))
                activate(db,others[1]["id"])
        assert db.execute(manifests.select().where(manifests.c.id==others[0]["id"])).mappings().one()["state"]=="active"


def test_private_instruction_source_cannot_enter_shared_index(db):
    from citeframe_persistence.models.memory import MemoryInstruction
    workspace,*_=seed(db)
    actor=db.get(Workspace,workspace).created_by_user_id
    instruction_id,request_id,source_id=(str(uuid4()) for _ in range(3))
    digest=sha256(b"private fixture").hexdigest()
    db.add(MemoryInstruction(id=instruction_id,workspace_id=workspace,actor_user_id=actor,
                            operation="remember",request_id=request_id,content="private fixture",
                            content_sha256=digest,created_at=datetime.now(UTC)))
    db.flush()
    db.add(MemorySource(id=source_id,workspace_id=workspace,kind="memory_instruction",
                        native_id=instruction_id,instruction_id=instruction_id,source_version=1,
                        native_version={"instructionId":instruction_id,"requestId":request_id},
                        content_sha256=digest,actor_user_id=actor,audience="private",owner_user_id=actor,
                        state="current",created_at=datetime.now(UTC)))
    db.flush()
    value=manifest_values(workspace,source=source_id,digest=digest)
    db.execute(manifests.insert().values(**value))
    rejects(db,entries.insert().values(**entry_values(workspace,value["id"],source_id,"private fixture",digest)))
    rejects(db,manifests.update().where(manifests.c.id==value["id"]).values(state="active",activated_at=datetime.now(UTC)))


@pytest.mark.parametrize("changes", [
    {"provider":"other"},{"model":"other"},{"model_version":"2"},
    {"config_fingerprint":"c"*64},
    {"provider":None,"model":None,"model_version":None,"dimensions":None,
     "config_fingerprint":lexical_config_fingerprint(),"state":"lexical_ready"},
])
def test_hybrid_tuple_exact_match(db,changes):
    workspace,_,source,body,digest=seed(db)
    value=manifest_values(workspace,source=source,digest=digest,retrieval_mode="hybrid")
    db.execute(manifests.insert().values(**value))
    chunk=entry_values(workspace,value["id"],source,body,digest,state="pending",
                       provider="synthetic",model="sql-plumbing",model_version="1",dimensions=1024,
                       config_fingerprint="b"*64)
    chunk.update(changes)
    rejects(db,entries.insert().values(**chunk))


def test_composite_fk_identity_without_user_triggers(db):
    workspace,other,source,body,digest=seed(db)
    first=manifest_values(workspace)
    second=manifest_values(other)
    db.execute(manifests.insert(),[first,second])
    db.execute(text("ALTER TABLE memory_index_entries DISABLE TRIGGER memory_index_entry_guard"))
    for mid,expected in ((first["id"],"fk_memory_index_entry_manifest"),
                         (second["id"],"fk_memory_index_entry_source")):
        with pytest.raises(DBAPIError) as caught:
            with db.begin_nested():
                db.execute(entries.insert().values(**entry_values(other,mid,source,body,digest)))
        assert caught.value.orig.diag.constraint_name==expected


def test_complete_ready_hybrid_and_incomplete_chunk_ranges(db):
    value,_=ready_manifest(db,mode="hybrid",state="ready")
    activate(db,value["id"])
    workspace,_,source,body,digest=seed(db)
    second=manifest_values(workspace,source=source,digest=digest,count=2)
    db.execute(manifests.insert().values(**second))
    # A non-final short chunk and a last chunk contained in the overlap cannot form coverage.
    rejects(db,entries.insert().values(**entry_values(workspace,second["id"],source,body,digest)))
    tail="t"*200
    rejects(db,entries.insert().values(**entry_values(workspace,second["id"],source,tail,
                sha256(tail.encode()).hexdigest(),source_sha256=digest,chunk_ordinal=1,start_cp=1000,end_cp=1200)))


def test_direct_sql_null_fields_fail_closed(db):
    workspace,*_=seed(db)
    for field in ("source_set","profile_snapshot","profile_fingerprint","source_set_sha256","retrieval_mode"):
        value=manifest_values(workspace)
        value[field]=None
        raw_rejects(db,value)


@pytest.mark.parametrize("mutation", ["delete","pending","source"])
def test_activation_holds_barrier_until_commit(pg,mutation):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    with Session(pg) as db,db.begin():
        value,source=ready_manifest(db)
        chunk=db.execute(entries.select().where(entries.c.manifest_id==value["id"])).mappings().one()
    locked,release=Event(),Event()
    def holder():
        with Session(pg) as db,db.begin():
            activate(db,value["id"])
            locked.set()
            assert release.wait(10)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(holder)
        try:
            assert locked.wait(10)
            with pytest.raises(DBAPIError) as caught:
                with pg.begin() as conn:
                    if mutation=="source":
                        conn.execute(text("UPDATE memory_sources SET state='stale' WHERE id=:id"),{"id":source})
                    elif mutation=="delete":
                        conn.execute(entries.delete().where(entries.c.id==chunk["id"]))
                    else:
                        conn.execute(entries.update().where(entries.c.id==chunk["id"]).values(state="pending"))
            assert caught.value.orig.sqlstate=="55P03"
        finally:
            release.set()
        future.result(timeout=10)
    with Session(pg) as db,db.begin():
        assert db.execute(manifests.select().where(manifests.c.id==value["id"])).mappings().one()["state"]=="active"
        assert db.get(MemorySource,source).state=="current"
        if mutation!="source":
            rejects(db,entries.delete().where(entries.c.id==chunk["id"]))


def test_application_decorator_enforces_strict_types_on_real_insert(db):
    workspace,*_=seed(db)
    sources=[member("00000000-0000-0000-0000-000000000001","0"*64)]
    sources[0]["version"]=1.0
    value=manifest_values(workspace,source_set=sources)
    with pytest.raises(StatementError) as caught:
        with db.begin_nested():
            db.execute(manifests.insert().values(**value))
    assert isinstance(caught.value.orig,ValueError)
    value=manifest_values(workspace)
    value["profile_snapshot"]["chunking"]["size"]=1200.0
    with pytest.raises(StatementError):
        with db.begin_nested():
            db.execute(manifests.insert().values(**value))


@pytest.mark.parametrize("escape", [r"\u0000",r"\ud800"])
def test_direct_jsonb_unrepresentable_profile_text_rejects(db,escape):
    raw=json.dumps(profile("hybrid")).replace('"sql-plumbing"','"'+escape+'"')
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(text("SELECT memory_index_profile_valid(CAST(:v AS jsonb))"),{"v":raw})


@pytest.mark.parametrize("isolation", ["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"])
@pytest.mark.parametrize("mutation", ["delete", "pending"])
def test_old_snapshot_cannot_activate_changed_entries(pg, isolation, mutation):
    with Session(pg) as db, db.begin():
        value, _ = ready_manifest(db)
    with pg.connect().execution_options(isolation_level=isolation) as reader:
        transaction = reader.begin()
        try:
            assert reader.execute(text(
                "SELECT count(*) FROM memory_index_entries WHERE manifest_id=:id"
            ), {"id": value["id"]}).scalar_one() == 1
            # The second real transaction commits after the first establishes its snapshot.
            with pg.begin() as writer:
                statement = entries.delete() if mutation == "delete" else entries.update().values(state="pending")
                writer.execute(statement.where(entries.c.manifest_id == value["id"]))
            with pytest.raises(DBAPIError) as caught:
                reader.execute(manifests.update().where(manifests.c.id == value["id"]).values(
                    state="active", activated_at=datetime.now(UTC)))
            assert caught.value.orig.sqlstate == ("23514" if isolation == "READ COMMITTED" else "0A000")
        finally:
            transaction.rollback()
    # Observe committed state through a fresh connection, rather than the old snapshot.
    with pg.connect() as observer:
        assert observer.execute(text(
            "SELECT state FROM memory_index_manifests WHERE id=:id"
        ), {"id": value["id"]}).scalar_one() == "building"
        states = observer.execute(text(
            "SELECT state FROM memory_index_entries WHERE manifest_id=:id"
        ), {"id": value["id"]}).scalars().all()
        assert states == ([] if mutation == "delete" else ["pending"])


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
@pytest.mark.parametrize("operation", [
    "manifest_insert", "manifest_update", "manifest_delete",
    "entry_insert", "entry_update", "entry_delete",
])
def test_unsupported_isolation_rejects_direct_index_writes(pg, isolation, operation):
    with Session(pg) as db, db.begin():
        value, source = ready_manifest(db)
        chunk = db.execute(entries.select().where(entries.c.manifest_id == value["id"])).mappings().one()
    statements = {
        "manifest_insert": manifests.insert().values(**manifest_values(value["workspace_id"], generation=2)),
        "manifest_update": manifests.update().where(manifests.c.id == value["id"]).values(generation=2),
        "manifest_delete": manifests.delete().where(manifests.c.id == value["id"]),
        "entry_insert": entries.insert().values(**entry_values(
            value["workspace_id"], value["id"], source, chunk["text_content"], chunk["text_sha256"])),
        "entry_update": entries.update().where(entries.c.id == chunk["id"]).values(state="pending"),
        "entry_delete": entries.delete().where(entries.c.id == chunk["id"]),
    }
    with pg.connect().execution_options(isolation_level=isolation) as writer:
        transaction = writer.begin()
        try:
            with pytest.raises(DBAPIError) as caught:
                writer.execute(statements[operation])
            assert caught.value.orig.sqlstate == "0A000"
            assert "index_write_requires_read_committed" in str(caught.value.orig)
        finally:
            transaction.rollback()
    with pg.connect() as observer:
        current = observer.execute(manifests.select().where(manifests.c.id == value["id"])).mappings().one()
        assert current["generation"] == 1 and current["state"] == "building"
        assert observer.execute(entries.select().where(entries.c.id == chunk["id"])).mappings().one()["state"] == "lexical_ready"
        assert observer.execute(text(
            "SELECT count(*) FROM memory_index_manifests WHERE workspace_id=:id"
        ), {"id": value["workspace_id"]}).scalar_one() == 1
