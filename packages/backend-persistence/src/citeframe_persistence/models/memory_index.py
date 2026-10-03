"""Source-only workspace index tables; explicitly imported, never auto-activated."""
import json
from hashlib import sha256
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy.types import TypeDecorator
from sqlalchemy import (
    BigInteger, CheckConstraint, Column, Computed, DDL, DateTime, ForeignKey, event,
    ForeignKeyConstraint, Index, Integer, String, Table, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

from citeframe_persistence.base import Base



CHUNKING = {"version": "codepoint-v1", "size": 1200, "overlap": 200}
LEXICAL = {"version": "simple-trgm-rrf-v1", "ftsConfig": "simple",
           "trgmThreshold": "0.3", "candidateLimit": 100, "rrfK": 60}


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("invalid_index_shape")


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("invalid_index_integer")


def _hash_shape(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid_index_hash")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def source_set_bytes(value):
    if type(value) is not list or len(value) > 4096:
        raise ValueError("index_scope_too_large")
    previous = ""
    for member in value:
        _keys(member, ("source_id", "version", "sha256", "chunk_count"))
        source_id = member["source_id"]
        if type(source_id) is not str:
            raise ValueError("invalid_index_source")
        try:
            valid = str(UUID(source_id)) == source_id
        except ValueError:
            valid = False
        if not valid or source_id <= previous:
            raise ValueError("invalid_index_source_order")
        previous = source_id
        _integer(member["version"], 1, 9223372036854775807)
        _integer(member["chunk_count"], 0, 2147483647)
        _hash_shape(member["sha256"])
    result = _canonical(value)
    if len(result) > 1048576:
        raise ValueError("index_scope_too_large")
    return result


def profile_bytes(value):
    _keys(value, ("schemaVersion", "mode", "space", "chunking", "lexical", "embedding"))
    if (any(type(value[key]) is not str for key in ("schemaVersion", "mode", "space"))
            or value["schemaVersion"] != "history-index-profile-v1"
            or value["mode"] not in ("lexical", "hybrid") or value["space"] != "history_text"):
        raise ValueError("invalid_index_profile")
    _keys(value["chunking"], CHUNKING)
    _keys(value["lexical"], LEXICAL)
    for part, expected in ((value["chunking"], CHUNKING), (value["lexical"], LEXICAL)):
        if any(type(part[key]) is not type(item) or part[key] != item for key, item in expected.items()):
            raise ValueError("invalid_index_profile")
    embedding = value["embedding"]
    if value["mode"] == "lexical":
        if embedding is not None:
            raise ValueError("invalid_index_profile")
    else:
        _keys(embedding, ("provider", "model", "modelVersion", "dimensions", "configFingerprint"))
        _integer(embedding["dimensions"], 1024, 1024)
        _hash_shape(embedding["configFingerprint"])
        for key, limit in (("provider", 64), ("model", 128), ("modelVersion", 64)):
            item = embedding[key]
            if type(item) is not str or not 1 <= len(item) <= limit or "\x00" in item:
                raise ValueError("invalid_index_profile")
            try:
                item.encode("utf-8")
            except UnicodeError:
                raise ValueError("invalid_index_profile") from None
    return _canonical(value)


def lexical_config_fingerprint():
    return sha256(_canonical({"schemaVersion": "history-lexical-config-v1",
                              "chunking": CHUNKING, "lexical": LEXICAL})).hexdigest()


class _IndexJSON(TypeDecorator):
    impl = JSONB
    cache_ok = True

    def __init__(self, kind):
        super().__init__()
        self.kind = kind

    def process_bind_param(self, value, dialect):
        (source_set_bytes if self.kind == "sources" else profile_bytes)(value)
        return value


def _column(name, type_, *, nullable=False, primary_key=False):
    return Column(name, type_, nullable=nullable, primary_key=primary_key)


def _digest(name):
    return CheckConstraint(f"{name} ~ '^[0-9a-f]{{64}}$'", name=f"ck_memory_index_{name}")


manifests = Table(
    "memory_index_manifests", Base.metadata,
    _column("id", String(36), primary_key=True),
    Column("workspace_id", String(36), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False),
    _column("owner_user_id", String(36), nullable=True),
    _column("audience", String(16)),
    _column("source_kind", String(32)),
    _column("corpus_scope", String(16)),
    _column("generation", BigInteger),
    _column("retrieval_mode", String(16)),
    _column("profile_fingerprint", String(64)),
    _column("source_set", _IndexJSON("sources")),
    _column("profile_snapshot", _IndexJSON("profile")),
    _column("source_set_sha256", String(64)),
    _column("state", String(16)),
    _column("created_at", DateTime(timezone=True)),
    _column("activated_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint("workspace_id", "id", name="uq_memory_index_manifest_workspace"),
    UniqueConstraint("workspace_id", "audience", "source_kind", "generation",
                     name="uq_memory_index_manifest_generation"),
    CheckConstraint("owner_user_id IS NULL AND audience = 'workspace' AND corpus_scope = 'workspace'",
                    name="ck_memory_index_manifest_scope"),
    CheckConstraint("source_kind IN ('chat_message','note','content_unit','research_artifact')",
                    name="ck_memory_index_manifest_kind"),
    CheckConstraint("generation >= 1", name="ck_memory_index_manifest_generation"),
    CheckConstraint("retrieval_mode IN ('lexical','hybrid')", name="ck_memory_index_manifest_mode"),
    CheckConstraint("state IN ('building','active','retired','failed') AND "
                    "(state <> 'active' OR activated_at IS NOT NULL) AND "
                    "(state NOT IN ('building','failed') OR activated_at IS NULL)",
                    name="ck_memory_index_manifest_state"),
    _digest("profile_fingerprint"), _digest("source_set_sha256"),
)
Index("uq_memory_index_manifest_active", manifests.c.workspace_id, manifests.c.audience,
      manifests.c.source_kind, unique=True,
      postgresql_where=text("state = 'active' AND owner_user_id IS NULL"))

entries = Table(
    "memory_index_entries", Base.metadata,
    _column("id", String(36), primary_key=True),
    _column("workspace_id", String(36)),
    _column("manifest_id", String(36)),
    _column("source_id", String(36)),
    _column("chunk_ordinal", Integer),
    _column("start_cp", BigInteger), _column("end_cp", BigInteger),
    _column("text_content", Text), _column("text_sha256", String(64)),
    _column("source_version", BigInteger), _column("source_sha256", String(64)),
    _column("index_generation", BigInteger),
    _column("embedding_space", String(32)),
    _column("provider", String(64), nullable=True),
    _column("model", String(128), nullable=True),
    _column("model_version", String(64), nullable=True),
    _column("dimensions", Integer, nullable=True),
    _column("config_fingerprint", String(64)),
    _column("embedding", Vector(1024), nullable=True),
    _column("state", String(16)),
    _column("created_at", DateTime(timezone=True)),
    Column("search_vector", TSVECTOR, Computed("to_tsvector('simple'::regconfig, text_content)", persisted=True)),
    ForeignKeyConstraint(["workspace_id", "manifest_id"],
                         ["memory_index_manifests.workspace_id", "memory_index_manifests.id"],
                         name="fk_memory_index_entry_manifest", ondelete="RESTRICT"),
    ForeignKeyConstraint(["workspace_id", "source_id"],
                         ["memory_sources.workspace_id", "memory_sources.id"],
                         name="fk_memory_index_entry_source", ondelete="RESTRICT"),
    UniqueConstraint("manifest_id", "source_id", "chunk_ordinal", name="uq_memory_index_entry_chunk"),
    CheckConstraint("chunk_ordinal >= 0 AND start_cp >= 0 AND end_cp > start_cp "
                    "AND end_cp - start_cp = char_length(text_content)",
                    name="ck_memory_index_entry_range"),
    CheckConstraint("text_sha256 = encode(sha256(convert_to(text_content, 'UTF8')), 'hex')",
                    name="ck_memory_index_entry_text_hash"),
    CheckConstraint("source_version >= 1 AND index_generation >= 1",
                    name="ck_memory_index_entry_versions"),
    CheckConstraint("embedding_space = 'history_text'", name="ck_memory_index_entry_space"),
    CheckConstraint("state IN ('pending','lexical_ready','ready','retired')",
                    name="ck_memory_index_entry_state"),
    CheckConstraint(
        "((provider IS NULL AND model IS NULL AND model_version IS NULL AND dimensions IS NULL "
        "AND embedding IS NULL AND state IN ('pending','lexical_ready','retired')) OR "
        "(provider IS NOT NULL AND length(provider) > 0 AND model IS NOT NULL AND length(model) > 0 "
        "AND model_version IS NOT NULL AND length(model_version) > 0 AND dimensions IS NOT NULL "
        "AND dimensions = 1024 AND state IN ('pending','ready','retired') "
        "AND (state <> 'ready' OR (embedding IS NOT NULL AND vector_norm(embedding) > 0))))",
        name="ck_memory_index_entry_profile_state"),
    _digest("text_sha256"), _digest("source_sha256"), _digest("config_fingerprint"),
)
Index("ix_memory_index_entry_scope", entries.c.workspace_id, entries.c.index_generation, entries.c.source_id)
Index("ix_memory_index_entry_fts", entries.c.search_vector, postgresql_using="gin")
Index("ix_memory_index_entry_trgm", entries.c.text_content, postgresql_using="gist",
      postgresql_ops={"text_content": "gist_trgm_ops"})
Index("ix_memory_index_entry_embedding", entries.c.embedding, postgresql_using="hnsw",
      postgresql_ops={"embedding": "vector_cosine_ops"}, postgresql_where=text("state = 'ready'"))


class MemoryIndexManifest(Base):
    __table__ = manifests


class MemoryIndexEntry(Base):
    __table__ = entries



# SQL canonicalization is private to these two validated, finite JSON domains.
_JSON_DDL = r"""
CREATE FUNCTION memory_index_canonical(v jsonb) RETURNS text LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE result text; item record;
BEGIN
 CASE jsonb_typeof(v)
 WHEN 'object' THEN
   result := '';
   FOR item IN SELECT key,value FROM jsonb_each(v) ORDER BY key COLLATE "C" LOOP
     result := result || CASE WHEN result='' THEN '' ELSE ',' END ||
       to_json(item.key)::text || ':' || memory_index_canonical(item.value);
   END LOOP;
   RETURN '{' || result || '}';
 WHEN 'array' THEN
   SELECT string_agg(memory_index_canonical(value),',' ORDER BY ordinality) INTO result
     FROM jsonb_array_elements(v) WITH ORDINALITY;
   RETURN '[' || coalesce(result,'') || ']';
 WHEN 'number' THEN RETURN trunc(v::text::numeric)::text;
 ELSE RETURN v::text;
 END CASE;
END $$;

CREATE FUNCTION memory_index_sources_valid(v jsonb) RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE member jsonb; previous text := ''; current_id text; n numeric;
BEGIN
 IF jsonb_typeof(v) IS DISTINCT FROM 'array' THEN RETURN false; END IF;
 IF jsonb_array_length(v)>4096 THEN RETURN false; END IF;
 FOR member IN SELECT value FROM jsonb_array_elements(v) LOOP
   IF (jsonb_typeof(member)='object' AND
       member ?& ARRAY['source_id','version','sha256','chunk_count'] AND
       (member-ARRAY['source_id','version','sha256','chunk_count'])='{}'::jsonb AND
       jsonb_typeof(member->'source_id')='string' AND
       jsonb_typeof(member->'sha256')='string' AND
       (member->>'sha256') ~ '^[0-9a-f]{64}$') IS NOT TRUE THEN RETURN false; END IF;
   current_id := member->>'source_id';
   IF (current_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
       AND current_id COLLATE "C" > previous COLLATE "C") IS NOT TRUE THEN RETURN false; END IF;
   previous := current_id;
   IF jsonb_typeof(member->'version') IS DISTINCT FROM 'number' OR
      jsonb_typeof(member->'chunk_count') IS DISTINCT FROM 'number' THEN RETURN false; END IF;
   n := (member->>'version')::numeric;
   IF n<>trunc(n) OR n<1 OR n>9223372036854775807 THEN RETURN false; END IF;
   n := (member->>'chunk_count')::numeric;
   IF n<>trunc(n) OR n<0 OR n>2147483647 THEN RETURN false; END IF;
 END LOOP;
 RETURN octet_length(convert_to(memory_index_canonical(v),'UTF8'))<=1048576;
END $$;

CREATE FUNCTION memory_index_profile_valid(v jsonb) RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE e jsonb;
BEGIN
 IF (jsonb_typeof(v)='object' AND
     v ?& ARRAY['schemaVersion','mode','space','chunking','lexical','embedding'] AND
     (v-ARRAY['schemaVersion','mode','space','chunking','lexical','embedding'])='{}'::jsonb AND
     v->>'schemaVersion'='history-index-profile-v1' AND v->>'space'='history_text' AND
     v->'chunking'='{"version":"codepoint-v1","size":1200,"overlap":200}'::jsonb AND
     v->'lexical'='{"version":"simple-trgm-rrf-v1","ftsConfig":"simple","trgmThreshold":"0.3","candidateLimit":100,"rrfK":60}'::jsonb
     ) IS NOT TRUE THEN RETURN false; END IF;
 e := v->'embedding';
 IF v->>'mode'='lexical' THEN RETURN e='null'::jsonb;
 ELSIF v->>'mode'='hybrid' THEN
   RETURN (jsonb_typeof(e)='object' AND
     e ?& ARRAY['provider','model','modelVersion','dimensions','configFingerprint'] AND
     (e-ARRAY['provider','model','modelVersion','dimensions','configFingerprint'])='{}'::jsonb AND
     jsonb_typeof(e->'provider')='string' AND length(e->>'provider') BETWEEN 1 AND 64 AND
     jsonb_typeof(e->'model')='string' AND length(e->>'model') BETWEEN 1 AND 128 AND
     jsonb_typeof(e->'modelVersion')='string' AND length(e->>'modelVersion') BETWEEN 1 AND 64 AND
     e->'dimensions'='1024'::jsonb AND jsonb_typeof(e->'configFingerprint')='string' AND
     (e->>'configFingerprint') ~ '^[0-9a-f]{64}$') IS TRUE;
 END IF;
 RETURN false;
END $$;

-- Row locks cannot refresh an already established REPEATABLE READ snapshot.
-- Every index write must use the tested READ COMMITTED serialization path.
CREATE FUNCTION memory_index_require_read_committed() RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 IF current_setting('transaction_isolation') <> 'read committed' THEN
   RAISE EXCEPTION 'index_write_requires_read_committed' USING ERRCODE='0A000';
 END IF;
END $$;

CREATE FUNCTION memory_index_manifest_shape() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM memory_index_require_read_committed();
 IF NOT memory_index_sources_valid(NEW.source_set) OR NOT memory_index_profile_valid(NEW.profile_snapshot)
    OR NEW.retrieval_mode IS DISTINCT FROM NEW.profile_snapshot->>'mode'
    OR NEW.source_set_sha256 IS DISTINCT FROM encode(sha256(convert_to(memory_index_canonical(NEW.source_set),'UTF8')),'hex')
    OR NEW.profile_fingerprint IS DISTINCT FROM encode(sha256(convert_to(memory_index_canonical(NEW.profile_snapshot),'UTF8')),'hex')
 THEN RAISE EXCEPTION 'invalid_index_manifest' USING ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' AND OLD.activated_at IS NOT NULL AND
   ROW(NEW.id,NEW.workspace_id,NEW.owner_user_id,NEW.audience,NEW.source_kind,NEW.corpus_scope,
       NEW.generation,NEW.retrieval_mode,NEW.profile_fingerprint,NEW.profile_snapshot,
       NEW.source_set,NEW.source_set_sha256,NEW.activated_at,NEW.created_at)
   IS DISTINCT FROM
   ROW(OLD.id,OLD.workspace_id,OLD.owner_user_id,OLD.audience,OLD.source_kind,OLD.corpus_scope,
       OLD.generation,OLD.retrieval_mode,OLD.profile_fingerprint,OLD.profile_snapshot,
       OLD.source_set,OLD.source_set_sha256,OLD.activated_at,OLD.created_at)
 THEN RAISE EXCEPTION 'index_manifest_immutable' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
"""
event.listen(manifests, "before_create", DDL(_JSON_DDL).execute_if(dialect="postgresql"))
event.listen(manifests, "after_create", DDL("""
CREATE TRIGGER memory_index_manifest_shape BEFORE INSERT OR UPDATE ON memory_index_manifests
FOR EACH ROW EXECUTE FUNCTION memory_index_manifest_shape()
""").execute_if(dialect="postgresql"))

_RELATIONAL_DDL = r"""
CREATE FUNCTION memory_index_entry_valid(e jsonb,m jsonb) RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE member jsonb; source_row record; expected_config text; p jsonb; amount bigint;
BEGIN
 SELECT value INTO member FROM jsonb_array_elements(m->'source_set')
   WHERE value->>'source_id'=e->>'source_id';
 IF member IS NULL THEN RETURN false; END IF;
 SELECT workspace_id,kind,audience,owner_user_id,state,source_version,content_sha256
   INTO source_row FROM memory_sources WHERE id=e->>'source_id' FOR SHARE NOWAIT;
 IF NOT FOUND THEN RETURN false; END IF;
 IF (source_row.workspace_id=e->>'workspace_id' AND source_row.kind=m->>'source_kind' AND
     source_row.audience='workspace' AND source_row.owner_user_id IS NULL AND source_row.state='current' AND
     source_row.source_version=(member->>'version')::numeric AND
     source_row.content_sha256=member->>'sha256' AND
     e->>'workspace_id'=m->>'workspace_id' AND e->>'manifest_id'=m->>'id' AND
     (e->>'index_generation')::bigint=(m->>'generation')::bigint AND
     (e->>'source_version')::bigint=(member->>'version')::numeric AND
     e->>'source_sha256'=member->>'sha256') IS NOT TRUE THEN RETURN false; END IF;
 amount := (member->>'chunk_count')::numeric::bigint;
 IF ((e->>'chunk_ordinal')::bigint < amount AND
     (e->>'start_cp')::bigint=(e->>'chunk_ordinal')::bigint*1000 AND
     (e->>'end_cp')::bigint-(e->>'start_cp')::bigint<=1200 AND
     ((e->>'chunk_ordinal')::bigint=amount-1 OR
       (e->>'end_cp')::bigint-(e->>'start_cp')::bigint=1200) AND
     ((e->>'chunk_ordinal')::bigint=0 OR
       (e->>'end_cp')::bigint>(e->>'start_cp')::bigint+200)) IS NOT TRUE THEN RETURN false; END IF;
 p := m->'profile_snapshot';
 IF m->>'retrieval_mode'='lexical' THEN
   expected_config := encode(sha256(convert_to(memory_index_canonical(jsonb_build_object(
     'schemaVersion','history-lexical-config-v1','chunking',p->'chunking','lexical',p->'lexical')),'UTF8')),'hex');
   RETURN (e->>'provider' IS NULL AND e->>'model' IS NULL AND e->>'model_version' IS NULL AND
     e->>'dimensions' IS NULL AND e->>'embedding' IS NULL AND e->>'config_fingerprint'=expected_config AND
     e->>'state' IN ('pending','lexical_ready','retired')) IS TRUE;
 END IF;
 RETURN (e->>'provider'=p->'embedding'->>'provider' AND e->>'model'=p->'embedding'->>'model' AND
   e->>'model_version'=p->'embedding'->>'modelVersion' AND
   (e->>'dimensions')::integer=1024 AND e->>'config_fingerprint'=p->'embedding'->>'configFingerprint' AND
   e->>'state' IN ('pending','ready','retired')) IS TRUE;
END $$;

CREATE FUNCTION memory_index_check_manifest(mid varchar, complete boolean) RETURNS void LANGUAGE plpgsql AS $$
DECLARE m record; e record; member jsonb; source_row record; count_ bigint; max_ bigint; min_ bigint;
BEGIN
 SELECT * INTO STRICT m FROM memory_index_manifests WHERE id=mid;
 FOR e IN SELECT * FROM memory_index_entries WHERE manifest_id=mid ORDER BY source_id,chunk_ordinal LOOP
   IF NOT memory_index_entry_valid(to_jsonb(e),to_jsonb(m)) THEN
     RAISE EXCEPTION 'index_entry_manifest_conflict' USING ERRCODE='23514';
   END IF;
   IF complete AND e.state IS DISTINCT FROM (CASE WHEN m.retrieval_mode='lexical' THEN 'lexical_ready' ELSE 'ready' END)
   THEN RAISE EXCEPTION 'index_incomplete' USING ERRCODE='23514'; END IF;
 END LOOP;
 IF complete THEN
   FOR member IN SELECT value FROM jsonb_array_elements(m.source_set) LOOP
     SELECT workspace_id,kind,audience,owner_user_id,state,source_version,content_sha256
       INTO source_row FROM memory_sources WHERE id=member->>'source_id' FOR SHARE NOWAIT;
     IF NOT FOUND THEN RAISE EXCEPTION 'index_source_unavailable' USING ERRCODE='23514'; END IF;
     IF (source_row.workspace_id=m.workspace_id AND source_row.kind=m.source_kind AND
         source_row.audience='workspace' AND source_row.owner_user_id IS NULL AND source_row.state='current' AND
         source_row.source_version=(member->>'version')::numeric AND
         source_row.content_sha256=member->>'sha256') IS NOT TRUE
     THEN RAISE EXCEPTION 'index_source_unavailable' USING ERRCODE='23514'; END IF;
     SELECT count(*),min(chunk_ordinal),max(chunk_ordinal) INTO count_,min_,max_
       FROM memory_index_entries WHERE manifest_id=mid AND source_id=member->>'source_id';
     IF count_<>(member->>'chunk_count')::numeric OR (count_>0 AND (min_<>0 OR max_<>count_-1))
     THEN RAISE EXCEPTION 'index_incomplete' USING ERRCODE='23514'; END IF;
   END LOOP;
 END IF;
END $$;

CREATE FUNCTION memory_index_manifest_lock() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM memory_index_require_read_committed();
 IF TG_OP='DELETE' THEN
   PERFORM id FROM workspaces WHERE id=OLD.workspace_id FOR UPDATE NOWAIT;
   RETURN OLD;
 END IF;
 PERFORM id FROM workspaces WHERE id=NEW.workspace_id FOR UPDATE NOWAIT;
 IF TG_OP='UPDATE' AND NEW.workspace_id IS DISTINCT FROM OLD.workspace_id
 THEN RAISE EXCEPTION 'index_workspace_immutable' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER memory_index_manifest_lock BEFORE INSERT OR UPDATE OR DELETE ON memory_index_manifests
FOR EACH ROW EXECUTE FUNCTION memory_index_manifest_lock();

CREATE FUNCTION memory_index_manifest_complete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.state IN ('building','active') THEN
   PERFORM memory_index_check_manifest(NEW.id,NEW.state='active');
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER memory_index_manifest_complete AFTER INSERT OR UPDATE ON memory_index_manifests
FOR EACH ROW EXECUTE FUNCTION memory_index_manifest_complete();

CREATE FUNCTION memory_index_entry_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m record; row_ jsonb; wid varchar; mid varchar;
BEGIN
 PERFORM memory_index_require_read_committed();
 row_ := CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
 wid := row_->>'workspace_id'; mid := row_->>'manifest_id';
 PERFORM id FROM workspaces WHERE id=wid FOR UPDATE NOWAIT;
 SELECT * INTO m FROM memory_index_manifests WHERE id=mid AND workspace_id=wid FOR UPDATE NOWAIT;
 IF NOT FOUND THEN RAISE EXCEPTION 'index_manifest_unavailable' USING ERRCODE='23503'; END IF;
 IF m.state='active' THEN RAISE EXCEPTION 'index_active_immutable' USING ERRCODE='23514'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 IF TG_OP='UPDATE' AND
    ROW(NEW.id,NEW.workspace_id,NEW.manifest_id,NEW.source_id,NEW.chunk_ordinal,
        NEW.start_cp,NEW.end_cp,NEW.text_content,NEW.text_sha256,NEW.source_version,
        NEW.source_sha256,NEW.index_generation,NEW.embedding_space,
        NEW.provider,NEW.model,NEW.model_version,NEW.dimensions,NEW.config_fingerprint,NEW.created_at)
    IS DISTINCT FROM
    ROW(OLD.id,OLD.workspace_id,OLD.manifest_id,OLD.source_id,OLD.chunk_ordinal,
        OLD.start_cp,OLD.end_cp,OLD.text_content,OLD.text_sha256,OLD.source_version,
        OLD.source_sha256,OLD.index_generation,OLD.embedding_space,
        OLD.provider,OLD.model,OLD.model_version,OLD.dimensions,OLD.config_fingerprint,OLD.created_at)
 THEN RAISE EXCEPTION 'index_entry_immutable' USING ERRCODE='23514'; END IF;
 IF m.state<>'building' OR NOT memory_index_entry_valid(row_,to_jsonb(m))
 THEN RAISE EXCEPTION 'index_entry_manifest_conflict' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER memory_index_entry_guard BEFORE INSERT OR UPDATE OR DELETE ON memory_index_entries
FOR EACH ROW EXECUTE FUNCTION memory_index_entry_guard();
"""
event.listen(entries, "after_create", DDL(_RELATIONAL_DDL).execute_if(dialect="postgresql"))
