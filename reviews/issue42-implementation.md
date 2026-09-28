# Issue #42 P1a independent implementation review

## Disposition

**ACCEPT — bounded P1a instruction-only persistence/management candidate.** Targeted final review closes IR6; IR1–IR5 retain their independently verified closures. No open finding remains in this reviewed slice. The final rerun passed **57 tests: 44 real-PostgreSQL P1a tests and 13 persistence/research boundary tests**, with no skips. The frozen native 85-table/97-index oracle and exact six-table additive boundary are preserved.

Accepted identity: committed storage candidate `2e9287638fee9567c6474b8356c3b3ba93fec16a`, including shared contract `9ad428bfa673ac06f85f98a856519516fc079b9c` after scaffold `eac4de4`. The final formatting-only recheck below supersedes the earlier migration/test hashes and retains the bounded ACCEPT. This acceptance covers the pure core only. It is not completion of Issue #42 or #41, hosted CI/final-image acceptance, or acceptance of future adapters/provider loops, compaction, UI or model quality. Controller-reported frozen lock/export checks are recorded with attribution; local Docker is unavailable and final-image smoke remains a hosted-CI gate.

## Authority and boundary

- Review branch: `work/issue42-memory-persistence`; starting HEAD `8812fda4d69b7f0e654e749c357fa05b5e8da72f`.
- Governing authority: canonical `D:/Code/citeframe/specs/v5/memory-management/spec.md` v4, especially §§13–14; current canonical design §§3–5 and 12.1; previous final design reviews. Initial local copied spec is v3 and its #40/A1 holds are superseded by current authorization.
- Accepted slice: six additive instruction-only tables, owner-private management/storage, exact manual provenance, CAS/successor, operation replay, synchronous all-revision semantic-byte erasure, neutral contracts/package scaffold.
- No new private task/audience schema; no private content in shared context, tools, history, summary, checkpoint or planning, including the owner's own private content. No mounted routes/UI or model execution in P1a. Native messages/assets/notes/Research records retain their semantics.
- #42 is sole shared `memory.py`/package scaffold owner; #44 adapters remain separate. No unrelated #40 dependency or canonical worktree changes.
- Reviewer writes only this artifact. No product/test file edits, commits, paid providers, private profile memory, shared workbench changes or existing runtime/database use.

## Independent runtime preparation — 2026-09-28

Verified Python 3.12.14 with SQLAlchemy 2.0.51, psycopg 3.3.4, Alembic and pytest using `D:/Code/citeframe/apps/api/.venv/Scripts/python.exe`. Every review invocation sets `PYTHONDONTWRITEBYTECODE=1` and lane-local `PYTHONPATH` so the executable's pre-existing editable installs do not select canonical product code.

Disposable PostgreSQL 17.11 uses the verified existing portable binaries at `D:/Code/citeframe/.local-runtime/postgresql/pgsql/bin`, a newly initialized temporary cluster, loopback only, port `55442`, role `reviewer`, database `issue42_review`. No existing database was connected. Neither MinIO nor a provider is needed.

Temporary cluster/evidence root: `C:/Users/baiao/AppData/Local/Temp/citeframe-issue42-review-3174ea83c95f4539945ac26ed8ef7eb0`. This is disposable runtime state, not a repository artifact. `initdb -U reviewer --auth=trust --encoding=UTF8 --no-locale` succeeded. `pg_ctl start` encountered the sandbox restricted-token error; launching the exact `postgres.exe -D <temp>/data -h 127.0.0.1 -p 55442` with `Start-Process -WindowStyle Hidden` succeeded. This did not alter PostgreSQL binaries or sandbox policy. Both `CREATE EXTENSION vector` and `CREATE EXTENSION pg_trgm` succeeded.

Baseline command (passed):

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH="$PWD/apps/api/src;$PWD/packages/backend-contracts/src;$PWD/packages/backend-persistence/src;$PWD/packages/research-persistence/src"
$env:AI_PDF_DATABASE_URL='postgresql+psycopg://reviewer@127.0.0.1:55442/issue42_review'
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m alembic -c apps/api/alembic.ini upgrade s3a4b5c6d7e8
```

Seeded synthetic users (owner/member/viewer/nonmember), two workspaces and six memberships, plus one each of native chat thread/message, note, Research run and PDF asset. Recorded all 85 native tables' rows and native column metadata before candidate migration in temporary `baseline.json`. Full native-row snapshot SHA-256: `6a40852c3f357e2c915189b1fc17e893ab739e6f1da160522e1c1fadd09023d3`. This hash supports later exact comparison; it is not a feature acceptance result.

## Governing semantic oracles

| Area | Required direct evidence | Current status |
|---|---|---|
| Fail-closed access | Missing authorizer, invalid/unknown role, missing/revoked member, archive, cross-owner (including workspace owner), cross-workspace denial; appropriate row guards through transaction | Pending candidate |
| Shared-output exclusion | Owner and second member cannot use private sources through nonmanagement/shared purpose; no new consumer injection or native audience schema | Pending candidate |
| Manual attribution | Exact content and conditions, authenticated actor, instruction/source identity, no caller-forged confirmation or source ownership | Pending candidate |
| CAS/successor | Concurrent same-version mutations produce one winner; one correction successor; loser leaves no partial instruction/revision/operation | Pending candidate |
| Deletion/ER01 | Marker only in conditions; multiple revisions; every conditions/content/hash SQL NULL after delete; retained support identities; no leaked history/replay or resurrection | Pending candidate |
| Direct SQL integrity | Malformed/missing conditions, erased-row payload, irreversible erasure, required confirmation support, cross-workspace and cross-owner source edges | Pending candidate |
| Replay/commit | Same key and requestId deduplicate, mismatch conflicts, lost acknowledgement reconciles from new connection, replay after delete returns content-free result | Pending candidate |
| Intent/validity | Invalidation/repair cannot reactivate inactive/superseded/deleted identity; expiry preserves intent | Pending candidate |
| Migration/native parity | Populated baseline up adds only approved structures and preserves all native rows/columns; empty safe down; populated guarded refusal; extensions preserved | Baseline prepared; candidate migration unrun |
| Neutral imports/deployment | Actual use cases/contracts import with both apps unavailable; package/dependency/lock/deploy declarations coherent; no paid IO | Pending candidate |
| Future provider/UI/model | Actual shared loops/compaction and browser/semantic evaluation belong to later slices | Unrun; no acceptance claim |

## Write-back and handoff

Durable review state is confined to this artifact. No private/global memory or canonical #40 workbench entry was read or updated. The isolated `memory42-p1a` workbench registration was read and confirmed. Candidate identity, findings, exact independent test commands/results and cleanup will be appended when the developer supplies the completed candidate. No broad PASS is issued from prior design, baseline migration or CI.

## Growing-candidate observations (provisional, before final candidate)

### IR1 — P1: membership role is not validated by the private authorizer

`packages/memory-service/src/citeframe_memory/access.py`, `WorkspaceAccess.authorize`, currently accepts every existing membership row without validating its role. Independent disposable-PG invocation authorized `owner`, `member`, and the deliberately unsupported `viewer`; nonmember was denied with `membership_required`. The native role domain must be honored and unknown values must fail closed. Final adjudication requires the completed candidate; this observation is not a completed review of still-growing code.

Reproduction: create a synthetic `workspace_memberships` row with `role='viewer'`; within a real SQLAlchemy transaction call `WorkspaceAccess(session).authorize(AccessContext(user_id, workspace_id, 'management', 'private'), owner_user_id=user_id)`. Observed: returns normally. This is a new memory-path guard finding; no claim is made that the legacy application's member gate already enforced a stricter role policy.

### Independent growing-candidate evidence

- `alembic ... upgrade t4b5c6d7e8f9` succeeded on the populated baseline. Exactly six `memory_%` tables were present. Exact row comparison across all 85 pre-existing native tables found no changes. Native column comparison and final migration rerun remain pending.
- Importing the actual lane-local `citeframe_contracts.memory`, `citeframe_persistence.models.memory`, and `citeframe_memory` with a `MetaPathFinder` that raises on any `ai_pdf_api`/`ai_pdf_worker` import succeeded. Full use-case imports were not available at that snapshot and must be checked after completion.
- PostgreSQL remains limited to the disposable review cluster. No existing service state was modified.

### IR2 — P1: a deleted identity can receive a new live revision through direct SQL

Growing migration `t4b5c6d7e8f9_instruction_memory.py`, `memory_record_immutable` / `memory_check_head`: the record guard permits any `current_version + 1`; the head predicate checks the new head without preserving the preceding deleted state. On a deleted four-revision fixture, independently inserted version 5 with `intent='active'`, non-NULL content/hash/conditions and a retained confirmation support edge, advanced the head to 5, and executed `SET CONSTRAINTS ALL IMMEDIATE`. PostgreSQL accepted the live head (`active`, `RESURRECTED`). The probe was rolled back. Direct UPDATE restoration of an erased revision was correctly rejected by `revision_erasure_monotonic`; retaining this negative alone would miss the append/head bypass.

Required correction: fence same-identity resurrection at the database head/append boundary and add the corresponding negative test. A new explicit instruction may create a fresh identity under the approved contract. Deleted identity and erased historical payload must remain terminal. Recheck the exact completed candidate before assigning final disposition.

Additional successful growing-code probes: manual remember/source attribution, same-request replay, deactivate then source invalidation preserves `inactive`, delete creates a content-free tombstone, all four revisions have SQL NULL content/hash/conditions, history and original-create replay after deletion return no statement. Deferred support deletion was rejected. Both whole-second and microsecond timezone-aware `effectiveFrom` values were accepted.

## Independent executed coverage on the growing candidate

These executions used real PostgreSQL transactions on port 55442 and lane-local source imports. They do not establish acceptance of a later changed candidate.

| Oracle | Observed result |
|---|---|
| Owner/workspace/shared-output separation | 27 denied read/history/source probes: workspace owner reading member memory, same actor in another workspace, and all nonmanagement/private-or-workspace audience combinations. Missing authorizer denied. |
| Current membership/archive | An archived workspace and a removed actor membership each denied an existing memory read. Synthetic native rows were restored exactly after each test. Unsupported-role issue IR1 remains open. |
| Correction race | Two barrier-synchronized independent sessions corrected the same version: one successor, one `VersionConflict`; SQL successor count exactly one. |
| Simultaneous idempotent replay | Two barrier-synchronized sessions remembered identical request/key/body: identical operation/resource receipt. Changed body returned `IdempotencyConflict`. |
| Lost DB acknowledgement | Session `after_commit` raised `synthetic_lost_commit_ack` after a durable successful commit. Fresh-session `reconcile(request_id)` returned the committed receipt; same-key replay matched it. This tests database acknowledgement recovery, not external-provider exactly-once. |
| ER01 byte erasure | Remember with marker only in `conditions.subject`; deactivate; invalidate; delete. All four stored revisions had zero non-NULL content/hash/conditions. History and replay of original remember returned content-free metadata. |
| Intent versus validity | Deactivation followed by source invalidation preserved `inactive` while changing validity to `invalidated`. Recompute/reactivation is not implemented in P1a and was not simulated as a passing product path. |
| Conditions direct-SQL inserts | 12 malformed variants rejected before commit: JSON NULL, empty object, missing/null/numeric/empty/oversized subject, empty applicability, unknown key, impossible date, missing timezone, array. Probe inserted revisions with normal support and forced `SET CONSTRAINTS ALL IMMEDIATE`, then rolled back. |
| Immutable erased revisions | UPDATE restoring an erased revision rejected by `revision_erasure_monotonic`. New-revision/head resurrection bypass remains IR2. |
| Required support and FK integrity | Removing confirmation support rejected at deferred validation; cross-owner support rejected; cross-workspace and nonexistent source edges rejected by FKs. |
| Reference-safe instruction erasure | Created two legitimate same-owner records sharing an instruction source via a direct fixture. Deleting the first retained the second record's exact source text. Deleting the last dependent made source resolution unavailable. |
| Populated upgrade | `upgrade t4b5c6d7e8f9` succeeded; six new tables. Exact row snapshots for all 85 native tables and all native column name/type/nullability metadata remain unchanged after memory operations. |
| Populated guarded downgrade | `downgrade s3a4b5c6d7e8` raised the explicit export/erasure guard; transaction rollback retained head `t4b5c6d7e8f9` and native rows. |
| Empty downgrade | Separate disposable database `issue42_review_empty`: fresh full upgrade to `t4b5c6d7e8f9`, downgrade to `s3a4b5c6d7e8`; zero memory tables, both `vector` and `pg_trgm` retained. |
| App-unavailable imports | Raising meta-path blocker for both applications; actual `citeframe_contracts.memory`, persistence memory models, and memory access/sources/commands/lifecycle imported successfully from this lane. |

Growing source identity during these probes: scaffold commit `eac4de4` plus uncommitted persistence implementation. SHA-256: access `E17D85D1F92F3D178E68EDC3AD8953C1B802F385DC273410B00AC4AC9813F270`; commands `B98DFDB5BCD1554A69ADBED9384558BE053EA37147F6E9CC0A45C351E46D21C8`; lifecycle `7346AC060189247C58A6E337908C7E9BD331828D7EC596AC1121083987C611B8`; sources `805F7E5BE3B807444615327B45BC51CBA3E19EA04BA6BAF24D25413E83DF4CE3`; migration `CB954191A9B873EB243C059EF22BB8CE190F294884BD0602A9C3027AEBC86917`; model `04087320564F9545616727C8FE55BEB353FE1A789B2791F4F4A16C75339FBDF0`.

The core structure stays within the intended neutral, instruction-only six-table boundary. It currently has the two concrete safety findings above. Product acceptance, exact final-candidate replay and repository test-suite review remain pending; future UI/model paths are explicitly unrun.

## Rework verification and a remaining transition-order finding

IR1 is corrected in current source: `WorkspaceAccess` accepts only `owner`/`member`; a fresh full populated migration database independently denies `viewer`. IR2's deleted-to-new-live-head reproduction now rejects with `memory_terminal_intent`; a live orphan revision against a deleted record is also rejected by `memory_revision_head_required`. The added PostgreSQL regression suite was independently executed: **32 passed in 7.44s** (all database cases enabled, no skips).

### IR3 — P1: head-first SQL ordering bypasses the inactive-to-active guard

On the newly migrated `issue42_review_final` database, create a memory and deactivate it to version 2. Save its original active version-1 row/support as a fixture. In one transaction:

1. `UPDATE memory_records SET current_version=3 WHERE id=:id` **before** inserting revision 3.
2. Insert a clone of the original active revision with version 3/new revision ID, plus its valid same-owner support edge.
3. `SET CONSTRAINTS ALL IMMEDIATE`.

Observed: PostgreSQL accepts the active head. `memory_record_immutable` reads `new_intent` while the deferred-FK target revision is absent; `new_intent` is SQL NULL and the conditional does not reject it. Later deferred head/support checks do not re-evaluate the previous-to-current intent transition. This bypass remains after the deleted-identity fix. It can also affect the superseded branch of that immediate guard. Both insert-first and head-first ordering must enforce the same transition invariant, preferably with the final old/new revision transition validated at commit. The inactive intent must not be silently repaired to active through an invalidation/recomputation-shaped revision; P1a does not authorize reactivation. All probes were rolled back and native data remains untouched.

Exact repository suite command:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:CITEFRAME_MEMORY42_POSTGRES_URL='postgresql+psycopg://reviewer@127.0.0.1:55442/citeframe_memory42_test'
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q packages/memory-service/tests/test_instruction_memory.py
```

The suite's current green result does not cover the head-first transition-order negative above. IR3 requires original-developer rework and independent retest before a scoped acceptance.

### IR3 recheck

The transition predicate now runs in deferred `memory_check_head`, checks both old and new intent for SQL NULL, and uses the recorded OLD/NEW head versions. The newly added insert-first/head-first × deactivate/correct/delete tests all passed in an independent rerun: **43 passed in 10.34s**. IR3 is corrected at this candidate snapshot; final identity binding remains pending.

### IR4 — P2: CI currently skips the PostgreSQL regression suite

`.github/workflows/ci.yml` invokes `pytest packages/memory-service/tests/test_instruction_memory.py` without setting `CITEFRAME_MEMORY42_POSTGRES_URL` or creating its required `citeframe_memory42_test` database. The fixture explicitly skips every PG test when that variable is absent. Independent reproduction with the variable removed: **3 passed, 40 skipped in 1.24s**, exit 0; with disposable PostgreSQL enabled: **43 passed**. Configure a dedicated test database and that environment variable in the existing CI service/job so the new CAS/access/erasure/migration regressions actually execute. Local independent PostgreSQL evidence remains valid; an unchanged CI configuration would not continuously enforce those invariants.

### IR5 — P1: eagerly exporting PG-only tables breaks existing SQLite native-feature fixtures

`packages/backend-persistence/src/citeframe_persistence/models/__init__.py` now eagerly imports all six memory tables into the shared `Base.metadata`. `models/memory.py` uses unconditional PostgreSQL regex/hash/JSONB expressions. Existing unrelated API/Worker fixtures call `Base.metadata.create_all(sqlite_engine)` and now fail before exercising their native behavior.

Independent actual regression command:

```powershell
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q apps/worker/tests/test_audio_ingestion.py::test_audio_adapter_fails_closed_without_asr --tb=short
```

Observed: **1 failed**, `sqlite3.OperationalError: near "~": syntax error` while creating `memory_instructions` at existing test line 85. A read-only import-loader comparison that executes only the `8812fda` version of the persistence model package `__init__.py` (all other current source unchanged) makes the same test **1 passed in 0.75s**. No product/test file was changed for the comparison. Other affected entry points include API `asset_router_test_support.py:141`, Research fixture builders and Worker image/document/HTML/office/audio suites.

Preserve the existing native-feature fixture path without weakening or substituting the actual PG integrity evidence. Resolve dialect-specific metadata registration/DDL behavior cleanly and run both the real PostgreSQL memory suite and representative existing native API/Worker tests. Do not claim that a SQLite-compatible fixture proves PG constraints. Final candidate acceptance remains blocked on this concrete regression and the outstanding CI execution gap.

## Follow-up regression results

- IR4 wiring is corrected in current `.github/workflows/ci.yml`: dedicated `createdb citeframe_memory42_test`, `PGPASSWORD` and explicit `CITEFRAME_MEMORY42_POSTGRES_URL`. Static configuration inspection passes; hosted CI itself was not executed here.
- IR5 is corrected with PostgreSQL-only CHECK emission and SQLite JSON type variants for legacy fixtures. `MemoryCommands` explicitly rejects non-PostgreSQL sessions. Independent combined execution: **47 passed in 10.24s** (44 current memory tests with PG enabled plus all 3 audio ingestion tests). This preserves SQLite native fixtures while retaining the actual PostgreSQL schema checks.
- Existing image-stream tests and unaffected persistence checks: **7 passed**. Full frozen native 85-table PostgreSQL CREATE TABLE/index snapshot, restricted to the original table set and including the existing approved deltas, compares exactly unchanged. The six memory tables are the only additions.

### IR6 — P2: legacy persistence boundary assertions are not synchronized with the additive schema

Independent run of `apps/api/tests/test_persistence_boundary.py` plus `test_asset_image_stream.py`: **3 failed, 7 passed**. Existing boundary assertions at lines 96, 134 and subprocess line 187 still require identical legacy/new export lists and a global 85-table total. The neutral package now has six approved new-only exports and 91 tables; the old 85-table DDL/index projection itself remains exact. Preserve that frozen native oracle and explicitly assert the six approved additive exports/tables, rather than replacing the historic snapshot or broadly dropping equality checks. These failing integration gates require an owned correction before merge. Developer's handoff already reports them and requests controller file-ownership confirmation.

Other verification limits: `uv lock --offline --check` for API/Worker/evaluation could not execute because the sandbox denies starting installed `uv.exe`; no alternate privilege/path bypass was attempted. Full Worker contract test collection using the available API environment hit missing `langgraph`; this is recorded as an environment limit, not a product failure or a pass. Docker/final-image and hosted CI remain unrun.


## Final candidate-bound review — 2026-09-28

Branch `work/issue42-memory-persistence`, HEAD `eac4de4` (contract/scaffold), plus the uncommitted storage/dependency/CI/doc candidate recorded below. The governing current local spec is now synchronized to v4. No reviewer commit, product/test write or branch operation occurred.

### Findings and scoped judgment

| Item | Final disposition | Evidence boundary |
|---|---|---|
| IR1 unrecognized membership role | **Closed** | Exact owner/member allowlist; independent fresh-PG denial and four malformed-role regression variants. |
| IR2 deleted-identity resurrection | **Closed** | Deferred head/support constraints reject new live head/orphan revision; payload restoration still rejected. |
| IR3 head-first terminal-intent bypass | **Closed** | Deferred OLD/NEW transition validation; both SQL orders × inactive/superseded/deleted reject. |
| IR4 CI PG tests silently skipped | **Closed at configuration scope** | Dedicated database/URL present; CI-without-URL explicitly fails fixture. Hosted execution remains unrun. |
| IR5 native SQLite fixtures broken | **Closed** | PG-only CHECK emission/JSON variants; memory commands remain PostgreSQL-only; 47-pass combined PG/native-audio run. |
| IR6 existing persistence-boundary expectations | **Open P2; integration gate blocked** | Three observed failures. Exact old 85-table DDL/index projection passes independently; six approved new tables/exports need explicit assertions. |

Current architecture remains aligned: one neutral contract owner, one Base, six scoped tables, synchronous command transactions, immutable revision payload except irreversible erasure, and no unrelated native source/task/provider/UI activation. Corrected SQL predicates address the reproduced failures without introducing extra tables, jobs, schemas or permission fallbacks. The isolated scope is appropriate for later authorized integration, subject to IR6 and the remaining delivery gates.

### Final verification status

- **Pass — P1a runtime/PG:** 44 memory tests enabled on a reviewer-owned disposable PostgreSQL 17.11 cluster, plus independent probes described above. Combined memory + native audio command: 47 passed; API image-stream and unaffected boundary assertions: 7 passed, with IR6's three failures reported separately.
- **Pass — final migration:** Re-executed the final migration hash below over a separately populated baseline (four synthetic users, two workspaces, six memberships, native chat/message/note/run/asset). All 85 native table row snapshots unchanged; `alembic check` reported no new upgrade operations. Empty-memory down preserved all native rows and `vector`/`pg_trgm`; memory tables removed. Populated-memory down refusal is covered by enabled PG tests and the earlier independent transaction probe.
- **Pass — native data/contract preservation:** Exact compiled frozen native 85-table/index projection unchanged; only approved memory tables added. No native record/audience column or source hook change observed.
- **Pass — neutral imports/current private boundary:** Actual contracts, models and all four use-case modules import with both application packages prohibited. Current owner-private reads/mutations deny shared/nonmanagement purposes. This does not accept any not-yet-implemented provider, summary, checkpoint or planning consumer.
- **Blocked — IR6 integration checks:** Three known legacy-boundary failures remain and must not be masked by the 44 memory passes.
- **Blocked/unrun — lock/image/hosted CI:** Installed uv executable is denied by this sandbox; Docker is unavailable. Controller must run frozen checks for API/Worker/evaluation and the deployment gate. No package-lock correctness claim from TOML parsing alone.
- **Not applicable to P1a / unrun — mounted API/UI, actual shared provider loops, compaction and real-model quality:** No activation or paid evaluation. These remain later required parent-feature evidence.
- **Pass — repository hygiene check:** `git diff --check` returned no whitespace errors. Concurrent developer/controller changes are preserved.

### Runtime cleanup and handoff

Stopped only the reviewer cluster at the verified exact temporary data directory with `pg_ctl -D <review-root>/data -m fast -w stop`; `pg_isready 127.0.0.1:55442` returned no response and its `postmaster.pid` was removed. Temporary fixture/log files remain for forensic reproduction; no directory was deleted. Developer port 56492, canonical runtime/database, #40 worktree and shared workbench were not touched.

Reviewer work for this candidate is complete. Return IR6 to the original replacement developer via controller ownership assignment; preserve the native snapshot rather than relaxing its meaning. Re-review only the new delta and affected native/PG gates after the bounded correction, and bind the result to the new candidate. No broad feature or merge approval is issued here.

Write-back check completed: durable findings/evidence/handoff reside only in this owned review artifact. Private/global memory and canonical #40 workbench state were not read or modified.

### Exact final inspected file identities

| File | SHA-256 |
|---|---|
| `packages/backend-contracts/src/citeframe_contracts/memory.py` | `7fe4d79830e7484f9d1fbb98e090bf837a9fd2d49819f4c5c2e41da6d2716f4c` |
| `packages/backend-contracts/src/citeframe_contracts/__init__.py` | `b2bbef417ab301ccd50b4a2e1528affc90c025bc374f9de273027060c98c196f` |
| `packages/backend-persistence/src/citeframe_persistence/models/memory.py` | `a5dc08b1ee6e70dabc5ca9a1067741ce5f1b8ff6ec92ff1f7338d17fec3a9967` |
| `packages/backend-persistence/src/citeframe_persistence/models/__init__.py` | `1eb1bc810cd3a31b36b3566104867b0babe259402a1aefaf1582f8319a3515d9` |
| `apps/api/alembic/versions/t4b5c6d7e8f9_instruction_memory.py` | `261d30c99bb4000219264a6169b0a91ad9a267d6a774fdffc87f2f205e209155` |
| `packages/memory-service/pyproject.toml` | `ee4ddb932ac7fd3abc72a08bc9b7c82b81b87d4c1e3f8c327dcf0fe06bccfd0a` |
| `packages/memory-service/src/citeframe_memory/__init__.py` | `a67c64d215b8cb7ec3aead2003797eba9cf734a43562db09498888c668f5df98` |
| `packages/memory-service/src/citeframe_memory/access.py` | `286a3ffecdd83469c871351264283f078749ffea06622b60bd1c33dcbbbb972b` |
| `packages/memory-service/src/citeframe_memory/sources.py` | `805f7e5be3b807444615327b45bc51cba3e19ea04ba6baf24d25413e83df4ce3` |
| `packages/memory-service/src/citeframe_memory/commands.py` | `2f9285e6049ed52d4eb66e957647e1ce8a88bf0773c149b7785ca7090a07a2c7` |
| `packages/memory-service/src/citeframe_memory/lifecycle.py` | `7346ac060189247c58a6e337908c7e9bd331828d7ec596ac1121083987c611b8` |
| `packages/memory-service/tests/test_instruction_memory.py` | `6b906cd254a6b67fad6f33a3d152c58f30bd1d67078564194b014bd45e3cf5d1` |
| `.github/workflows/ci.yml` | `734eaebb1c579ab7cb2e0f967159c5a6044ab5ca82891add39f373c673b70f40` |
| `apps/api/pyproject.toml` | `17a546289bad50c1c07bbf315cea01292140de70a36bf453e2f21fc5de9fb115` |
| `apps/api/uv.lock` | `f68143541abffde4af5f61f63ea2293e7ee5ac7e5150bf61a5df58b3745c6cf0` |
| `apps/api/requirements.deploy.txt` | `bd445d1508c8df78597d666de0a5606143e3e730c1a1d263de028da2a1c50771` |
| `apps/worker/pyproject.toml` | `1961337a3361522b99e08f5a74544459554032b71d9f7e38e1fa23ad5df6603b` |
| `apps/worker/uv.lock` | `57c09fe7b974b85b6f662e6af39de9e8d66700ec1d5574e098bf2f750b146755` |
| `apps/worker/requirements.deploy.txt` | `82bf455bd55fee6223ff36a949a8de7df277d2f25fa1041bf0b3f625e43499bb` |
| `tools/evaluation/uv.lock` | `80847e56c82fcc5e94dc03932e3fca147f981c2bfec73b7f390be23df5b96097` |
| `infra/docker/Dockerfile.python` | `52fbd1c93d960fceaf230fe935ca51d3988e98aef91d3ec75524b8dd0f5ca113` |
| `infra/scripts/a2a-deploy-gate.sh` | `9658efc884382a688d72b427e4c8d21dceeb1b34bf1b9ef669c9aa2a7c43c9a3` |
| `pytest.ini` | `3ae300be3d174675cf1b31b52a22d74b72094b13276116f3d28efbde72874e83` |
| `specs/v5/memory-management/spec.md` | `566f549b415e34c1e7317a9a630bf0e11545fb3f689a55ecd0cd8e78af990874` |
| `specs/v5/memory-management/design.md` | `b06f0e0cb36b01efffe007560c11f6dcc507031f851237daf0452bbbd13cb690` |


## Targeted final P1a acceptance — IR6 and shared-contract delta

**Result: ACCEPT for the exact bounded P1a candidate. No new findings; IR1–IR6 are closed within their recorded implementation scope.** This section supersedes the preceding rework-required disposition and open IR6 status. Earlier runtime, migration, native-data and reverse-review evidence is retained; no broad design or feature review was repeated.

### IR6 correction independently inspected

`apps/api/tests/test_persistence_boundary.py` retains the original frozen snapshot file/hash, all previously approved native deltas, exact PostgreSQL DDL equality for the 85 original tables and their 97 indexes, shared Base/metadata identity, ordered legacy exports and existing object identities. It names precisely these six neutral-only additions: `MemoryInstruction`, `MemorySource`, `MemoryRecord`, `MemoryRevision`, `MemoryUse`, `MemoryOperation`, each mapped to its corresponding `memory_*` table.

The revised assertions require the complete table-name set to equal the frozen native set union those six names and the total to be 91. Only those six explicit names are removed when comparing the native snapshot; arbitrary additions or native DDL/index drift still fail. The new model test checks each class's defining module, exact table/name/metadata object, neutral root export identity and absence from the legacy API exports. Application-unavailable import checks remain in force. This is the bounded additive-schema correction requested in IR6, with no replacement or weakening of the historical native snapshot.

### Shared-contract and no-drift check

Inspected commit `9ad428bfa673ac06f85f98a856519516fc079b9c`: `HTTPTransport.stream` now requires keyword-only `follow_redirects: bool` with no default; runtime signature/type-hint inspection passed. `Usage.input_tokens` documents the total uncached/cache-read/cache-creation input and keeps unknown totals as `None`. No DTO field was added by that comment. No #44 adapters are present in this lane and no adapter redirect/runtime behavior is accepted here.

Rehashed every file in the previous final inspected manifest before/after the targeted run: the only changed entry is the authorized `memory.py` contract delta. The newly modified boundary-test file is identified below. Storage models/migration, access/commands/sources/lifecycle, all 44 P1a tests, CI/dependency/deploy wiring and governing v4 spec/design remain identical to the previously reviewed final core. Git scope inspection shows no mounted route/UI, native task/audience mutation or provider consumer. A1 choice2 still denies nonmanagement/shared purpose even for the private memory's owner; the prior explicit denial probes and current regression execution remain applicable.

### Independent targeted execution

Restarted only the existing reviewer-owned disposable PostgreSQL 17.11 cluster after verifying its exact temp data directory, missing postmaster PID and unoccupied loopback port `55442`. Used `citeframe_memory42_test`; each PG case creates/removes its own generated schema. No existing application/developer database was used.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH="$PWD/apps/api/src;$PWD/apps/worker/src;$PWD/packages/backend-contracts/src;$PWD/packages/backend-persistence/src;$PWD/packages/research-persistence/src;$PWD/packages/memory-service/src"
$env:CITEFRAME_MEMORY42_POSTGRES_URL='postgresql+psycopg://reviewer@127.0.0.1:55442/citeframe_memory42_test'
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q packages/memory-service/tests/test_instruction_memory.py apps/api/tests/test_persistence_boundary.py apps/api/tests/test_research_persistence_boundary.py --tb=short
```

Observed: **57 passed, 1 existing Starlette deprecation warning, 12.04 seconds; exit 0; no skips.** `git diff --check` also passed. The PostgreSQL cases exercised the unchanged schema/transaction/erasure/permission tests, including both intent-transition write orders and the neutral import checks. The 13 boundary cases now pass with the original native snapshot equality intact.

A `finally` cleanup stopped only this reviewer cluster with `pg_ctl -D <verified-review-root>/data -m fast -w stop`. Observed `server stopped`, `pg_isready 127.0.0.1:55442` returned no response, and postmaster PID was absent. Developer port 56492 and canonical runtime were untouched; no temporary directory was deleted.

### Evidence-scoped delivery decision

| Area | Disposition |
|---|---|
| IR6 and native85/additive6 boundary | **Pass; closed**, actual corrected assertions and 13 boundary tests independently checked. |
| Instruction-only P1a core | **ACCEPT**, carrying forward IR1–IR5 closures and all recorded independent real-PG/native preservation evidence; 44 PG suite cases rerun. |
| Shared transport contract delta | **Pass at contract scope**; required redirect argument and usage semantics inspected, no adapter implementation in #42. |
| Frozen locks/deploy export bodies | **Controller-verified**, not independently rerun here: controller reports uv 0.12.7 `lock --check` passing for API/Worker/evaluation (62/95/96 packages) and both fresh export dependency bodies matching checked-in requirements excluding generated command headers. Counts are descriptive, not an acceptance oracle. |
| Final images and hosted CI | **Gate outstanding**; local Docker unavailable. No final-image smoke or hosted-CI pass claimed. |
| Mounted API/UI, real provider/compaction flows, model quality | **Not delivered/unrun** in this pure-core slice. No broad Issue #42/#41 acceptance. |
| Commit/push/draft PR/merge | **Controller-owned next action**; reviewer made no Git writes. Scope acceptance does not waive hosted gates or authorize parent completion. |

Reviewer handoff is complete. Controller may commit/push this coherent candidate and create the partial-foundation draft PR under the existing authorization, then enforce hosted CI/final-image gates. No further P1a rework is requested by this review. Any subsequent product delta requires a matching evidence-bound review.

Write-back check: durable final judgment and candidate identities are recorded only here. No private/global memory, canonical #40 workbench, product, test or adapter file was changed by the reviewer.

### Final targeted candidate identities

All entries of the earlier **Exact final inspected file identities** table remain identical except the contract entry superseded below. The boundary test and stable developer handoff record are additionally pinned here. Thus the earlier complete manifest plus these replacements/additions identifies the accepted working-tree candidate; HEAD alone does not include the uncommitted storage slice.

| File | SHA-256 |
|---|---|
| `packages/backend-contracts/src/citeframe_contracts/memory.py` | `b1a0d53b5d21bac31ac12609a5a798cceda5f9aab43eefaa4e178a3d9d5aae45` |
| `apps/api/tests/test_persistence_boundary.py` | `234b7325892351adee64e34203373c1fe2ed3d35123b3afe6044f00d758ae24f` |
| `specs/v5/memory-management/lane42-report.md` | `a2e2eb5b52942d6346f6c381c43c988384c2b943b1c3b199f304c8781ceaa504` |
| `packages/backend-persistence/src/citeframe_persistence/models/memory.py` | `a5dc08b1ee6e70dabc5ca9a1067741ce5f1b8ff6ec92ff1f7338d17fec3a9967` |
| `apps/api/alembic/versions/t4b5c6d7e8f9_instruction_memory.py` | `261d30c99bb4000219264a6169b0a91ad9a267d6a774fdffc87f2f205e209155` |
| `packages/memory-service/src/citeframe_memory/access.py` | `286a3ffecdd83469c871351264283f078749ffea06622b60bd1c33dcbbbb972b` |
| `packages/memory-service/src/citeframe_memory/commands.py` | `2f9285e6049ed52d4eb66e957647e1ce8a88bf0773c149b7785ca7090a07a2c7` |
| `packages/memory-service/src/citeframe_memory/sources.py` | `805f7e5be3b807444615327b45bc51cba3e19ea04ba6baf24d25413e83df4ce3` |
| `packages/memory-service/src/citeframe_memory/lifecycle.py` | `7346ac060189247c58a6e337908c7e9bd331828d7ec596ac1121083987c611b8` |
| `packages/memory-service/tests/test_instruction_memory.py` | `6b906cd254a6b67fad6f33a3d152c58f30bd1d67078564194b014bd45e3cf5d1` |


## Final formatting-only delta confirmation — 2026-09-28

**ACCEPT retained. No new finding.** This check is limited to migration EOL cleanup, the corresponding frozen-DDL oracle normalization and controller-owned authority/documentation alignment. Prior IR1–IR6 closure, 57-test independent runtime/boundary evidence and all acceptance limitations remain in force; no architecture review was repeated.

At initial inspection, the index held the previously accepted migration blob `c3d7ffe` and the working tree held the formatting correction. The controller advanced the index and committed during this review. The final comparison therefore pinned that original staged blob explicitly and verified the resulting committed candidate `2e9287638fee9567c6474b8356c3b3ba93fec16a`; the reviewer did not stage, commit or otherwise change Git state.

### Exact delta and oracle check

- The entire new migration text equals the prior staged text after removing only trailing ASCII spaces/tabs from each line. There are exactly **118 changed lines**, all comma-terminated DDL lines; line count/order and every non-EOL character are unchanged. No SQL token or quoted literal was modified. Normalized Python AST equality also passed; functions, triggers, constraints and upgrade/downgrade operations are unchanged.
- The sole test-code delta adds `line.rstrip(" \t")` on each generated expected DDL line and a reason comment. Full statement equality against `MIGRATION.DDL` remains. The prior statement-set comparison and leading/internal whitespace, SQL identifiers, literal contents, constraints and token ordering are not relaxed by this addition.
- Independent in-memory negative controls changed `current_version >= 1` to `current_version >= 2`, then `visibility = 'private'` to `visibility = 'workspace'`. The actual updated frozen-DDL oracle rejected both with `AssertionError`. No product/test file was altered by these probes.
- Controller-owned current design header, brief and delivery checkpoint consistently state the existing spec v4/A1 choice2 and isolated neutral-lane authorization, while retaining historical evidence. Markdown EOL cleanup changes no operative contract. No new private audience/task mode or shared-private consumer is introduced.

### Bounded independent verification

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH="$PWD/apps/api/src;$PWD/apps/worker/src;$PWD/packages/backend-contracts/src;$PWD/packages/backend-persistence/src;$PWD/packages/research-persistence/src;$PWD/packages/memory-service/src"
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q packages/memory-service/tests/test_instruction_memory.py::test_frozen_migration_matches_current_six_table_models apps/api/tests/test_persistence_boundary.py::test_persistence_models_share_one_metadata_object_and_match_snapshot --tb=short
```

Observed: **2 passed, 1 existing Starlette warning, 0.18 seconds**. The six-table migration/model DDL oracle and exact frozen native85/97-index equality both pass on the formatting-clean candidate. The whole-file/AST comparisons and both negative controls above passed independently. `git diff --check` and `git diff --cached --check` returned no errors after the controller's commit. The developer's separate formatting-candidate 57-test real-PG and downgrade/up/check reruns are recorded in `lane42-report.md`; they were not rerun by this bounded review.

No PostgreSQL server was started for this formatting check. The reviewer-owned disposable cluster remains stopped (`postmaster.pid` absent). No paid call, product/test edit or Git write occurred. Only this review addendum was written; the controller can include it in the delivery ledger without changing the accepted product bytes.

### Stable candidate hashes after formatting

| File | SHA-256 |
|---|---|
| `apps/api/alembic/versions/t4b5c6d7e8f9_instruction_memory.py` | `8c4b2f0e86dfb6de3f383e29247e7716a040e030179d4157717078d286836bd9` |
| `packages/memory-service/tests/test_instruction_memory.py` | `f4117dfbcb878cd26b799a8b0c5f9a0d9ec67964f1c6d882a09e3b97d774d3f1` |
| `specs/v5/memory-management/lane42-report.md` | `e19a2ebc63dd5f0740f5ff14ae5795432f60f44784236a76b827c2d81fc350ce` |
| `specs/v5/memory-management/spec.md` | `a15b1b55e2542b01455b47b67508cffd673dd532dab2932702ad771b08a1fe85` |
| `specs/v5/memory-management/design.md` | `828effb02b5fbf9818604e35ea13662814e12ccc605b704dd895fd7bbafe6236` |
| `specs/v5/memory-management/controller-brief.md` | `5fcb90cd11f87319dc8a1cc9bca9c4013f7824bd8c119f6b2b64ce6d529a350a` |
| `specs/v5/memory-management/delivery.md` | `21adb2ec4f45e3a309c55be7e55901ce5f47b63efb8eec2b9b28e98fc0a71aaa` |

Final handoff: **bounded P1a ACCEPT, ready for the controller's draft-PR handoff subject to existing hosted CI/final-image gates**. No broad #42/#41 completion, mounted UI/provider/compaction or model-quality claim. Durable write-back remains solely this review artifact.
