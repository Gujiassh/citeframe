# History index storage

The history index storage module defines `memory_index_manifests` and `memory_index_entries` in SQLAlchemy metadata when explicitly imported. It does not register itself through the persistence model exports. Existing table and index definitions remain unchanged. Production schema activation needs a separately reviewed successor migration; this module supplies no Alembic revision, native corpus issuer, index builder, search API or embedding call.

## Workspace corpus identity

A manifest describes one workspace/shared source kind and generation, a declared source set and an exact retrieval profile. Private ownership is excluded: `owner_user_id` must be NULL and both audience and corpus scope must be `workspace`. Declared kinds are `chat_message`, `note`, `content_unit` and `research_artifact`; actual acceptance also requires a matching current `memory_sources` row, so the declaration alone does not enable native issuance for every kind. Private instruction sources cannot enter this corpus.

The source set uses strictly ordered unique canonical UUIDs, positive bounded source versions, lowercase SHA256 values and bounded chunk counts. It is limited to 4096 sources and 1048576 canonical UTF8 bytes. The Python bind layer requires exact integer types; SQL JSONB validates integral numeric values within the same bounds. Canonical hashes use the module's finite source-set/profile domains. They are not general JSON canonicalization services.

Profiles fix `history-index-profile-v1`, `history_text`, `codepoint-v1` chunks of 1200 codepoints with 200 overlap, and `simple-trgm-rrf-v1` lexical parameters. Whole-profile fingerprints and entry configuration fingerprints have distinct inputs. Lexical profiles carry no embedding tuple. Hybrid profiles bind provider/model/modelVersion/configuration fingerprint and 1024 dimensions; ready vectors must be finite and nonzero. Synthetic vectors in tests establish storage/query plumbing, with no provider or retrieval quality claim.

## Entry and activation integrity

Each entry has composite workspace/manifest and workspace/source foreign keys. Its source version, hash and generation must agree with the declared manifest member and the current shared registry source. Text ranges use Unicode codepoints: start is ordinal*1000, text length equals end-start, text SHA256 covers UTF8 bytes, non-final chunks fill 1200 codepoints, and later final chunks extend beyond the 200-codepoint overlap. These constraints do not compare text against the native original; exact native slices and truthful original completeness require the future issuer.

Activation revalidates entries and every declared current source, exact chunk counts, contiguous ordinals and readiness (`lexical_ready` or `ready`). There is one active generation per workspace/audience/source kind. Previously activated manifest identity, source set, profile, generation and activation metadata remain immutable after retirement. Active entries reject INSERT, UPDATE and DELETE; retirement permits payload deletion. An atomic retirement/replacement transaction exposes the committed generation to other readers.

## Transaction and source barriers

All manifest and entry INSERT, UPDATE and DELETE operations require **READ COMMITTED**. The IS01 guard rejects other isolation levels before dependent lock/read operations. Writes take a workspace `FOR UPDATE NOWAIT` barrier; entry writes also lock their manifest, and source validation uses `FOR SHARE NOWAIT`. Locks are held until transaction completion. Manifest DELETE uses the old workspace identity. Contention fails rather than waiting through a stale snapshot.

The storage tests cover concurrent source changes versus activation, competing activation and committed generation visibility. These table-local barriers do not implement native mutation hooks or invalidate an already active generation after later native changes. Future native integration must coordinate current-source invalidation, generation retirement, derived-payload erasure and dependent-reader suppression in the same approved transaction boundary. Storage rows alone confer no authorization or provenance authority.

## Lexical and hybrid SQL fixtures

Entries expose a stored `simple` TSVECTOR with a GIN index, a GiST trigram index and an HNSW cosine index for ready vectors. The dedicated test SQL ranks up to 100 candidates per lexical channel, uses word-similarity threshold 0.3 and reciprocal-rank fusion K=60, then applies deterministic ties and source collapse. This SQL is a fixture, not a callable product search interface.

`pg_trgm` word classification follows the database locale. The Unicode oracle checks actual trigram cardinality and exact candidate ordinals before requiring the appropriate 1/61 or 2/61 score; ASCII and retired-generation controls remain mandatory. PostgreSQL acceptance therefore records the actual database locale and extensions, and hosted execution must retain this oracle rather than hardcoding one locale's score.

For source definitions see [memory_index.py](../../packages/backend-persistence/src/citeframe_persistence/models/memory_index.py); storage, isolation and SQL controls are in [test_history_index_postgres.py](../../packages/memory-service/tests/test_history_index_postgres.py). The dedicated workflow requires all 156 cases to complete setup, call and teardown without skips or xfails. Native activation, migration upgrade/rollback, authorized corpus enumeration, real search integration and budgeted compatible embeddings require separate acceptance.
