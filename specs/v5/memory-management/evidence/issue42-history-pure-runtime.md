# Issue 42 pure history implementation evidence

Date: 2026-09-28. Candidate ready for original independent implementation review.
Scope: pure range/counting/query shapes only. No native feature activation.

## Candidate files

| Path | SHA-256 |
|---|---|
| packages/backend-contracts/src/citeframe_contracts/history.py | a771d0caf41ac0da307e1bb723da039aa2411f9cc35dd86e4c2ee460cf9d3c02 |
| packages/memory-service/src/citeframe_memory/history/__init__.py | 4c554257bcd2186adba89361614363bdc7ec92c969ccbb200e1ef6027a8dd3a0 |
| packages/memory-service/src/citeframe_memory/history/ranges.py | 65f068f1003692f0b30e4f7f0daa8c4ab3993b2f5fd44c6686163dca93669d08 |
| packages/memory-service/src/citeframe_memory/history/search.py | 1e399094f51ae3f4dcfd9c25474584ab85193ce745410fc836704a2433fa334f |
| packages/memory-service/tests/test_history_sources.py | 22ec11d67fe74a221b38dbed6a0a3d39fda538d5e1f7f09c66dd661f7883b944 |

## Implemented behavior

Canonical SourceReference is imported from the controller-supplied #43 contract. Text and locator selection shapes do not issue authority. Text windows preserve whole-body UTF-8 hashes, Unicode code points, BOM and CRLF; locator hydration remains unavailable. Initial before/after expansion is clipped once. Signed continuation holds original selection/window/expiry and opaque stable native binding; it contains no request, tool-call or counting-profile identity.

Each page replaces one result within a supplied complete GenerationRequest batch, preserving sibling results and tools. Actual #43 count_request validates the current expected CounterIdentity. Candidate and same-envelope empty-content baseline are counted separately; full capacity and 2000-token content delta are enforced, with a 16000-code-point ceiling. Overflow shrinks/recounts without a monotonic-token assumption. No-fit returns a payload-safe error without changing the input cursor. CountedPage returns exact request/hash, token counts, current call ID and credential-free counting profile hash. It does not archive or dispatch.

History policy parsing enforces exact v1/v2 parent key sets and strict nested history union. Parent budget/deadline scalar validation remains #43-owned; this shape projection is not an authorization receipt. Legacy v1 is read-only disabled. Search provides strict query parsing, enabled-kind projection and pure set intersection. It performs no ranking/index lookup and establishes no authorization or corpus completeness.

## Real dependencies and reproducible test

Unchanged local controller dependency:
packages/backend-contracts/src/citeframe_contracts/compaction.py
SHA-256 d77617a25ecf5cd9c0b808537f6c884b7ee67e2a2250bb0d955e99597ddb5e2b

Local compaction/policy.py is absent. This candidate requires the real owner43 module at integration. Tests explicitly extend the already loaded citeframe_memory package path using the environment below; no stub/helper copy, skip or fallback implementation is installed.

Read-only dependency:
D:/Code/citeframe-lanes/issue43-compaction/packages/memory-service/src/citeframe_memory/compaction/policy.py
SHA-256 f992b4d5e0d512a6cae7756cab3ed0e33def8f178a4948c05a919dc9b2796b44
Its adjacent compaction/__init__.py is the real package initializer. Controller must integrate these owner43 files through its own handoff; this lane does not copy them.

Executed in D:/Code/citeframe-lanes/issue42-persistence:

~~~powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:CITEFRAME_HISTORY43_SOURCE_ROOT='D:/Code/citeframe-lanes/issue43-compaction/packages/memory-service/src/citeframe_memory'
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -m pytest packages/memory-service/tests/test_history_sources.py packages/memory-service/tests/test_admission.py packages/memory-service/tests/test_instruction_memory.py::test_validation_and_fail_closed packages/memory-service/tests/test_instruction_memory.py::test_neutral_import_without_application_packages -q -p no:cacheprovider
~~~

Actual final result: 1647 passed in 3.05s, exit 0; no skipped tests.
Breakdown: 42 new history tests, 1603 existing admission tests, 2 existing P1a neutral validation/import tests.
Earlier initial history run: 34 passed; final candidate includes 8 additional tests.

Oracles include full-window stitching above 4000 characters, BOM/CRLF/astral/combining text; fixed terminal bounds; empty terminal source; unresolved locator and malformed range rejection; HMAC/binding/expiry rejection; C1 to C2 with different full framing/tool/profile; smaller positive page; no-fit retry at unchanged offset; exact counted request hash and unchanged siblings; current counter/profile mismatch; output reserve; nonmonotonic counter; 16000-code-point ceiling; counting profile excludes credentials. Counter fixtures are explicitly estimated deterministic algorithms, not provider tokenization evidence. Tests do not invoke a provider.

## Preserved governing artifacts

Approved contract:
specs/v5/memory-management/lanes/issue42-shared-sources.md
SHA-256 2befea01c88ff5fc7d3f8f54c23c9f22b9bb850dd5619dbf819d1091dcf3c042

Root review:
reviews/issue42-shared-sources.md
SHA-256 edaea6ceac0921d047713beca4352ca232f737e9ac93b033cdd06800239dad5a

Both and D77617A remain unchanged. No existing exports, schema, migration, memory.py, compaction files, CI, Git metadata, reviewer file or shared/private memory writes.

## Acceptance boundary and remaining delivery

Native issuer/all-output-reader metadata authorization before hydration and after counting remains an explicit integration gate. This module accepts already supplied text and cannot establish those permissions. Stable binding must be supplied by that actual issuer. Archive/replay/native CAS/dispatch-hash equality and suppression remain owner43 integration work. The pure fit result cannot authorize a send. Current-branch completed-chat native execution is still pending #42 resolver plus serial owner43 seam; no fake DB or constructible authority DTO is supplied.

No PostgreSQL or native transaction acceptance is claimed here. Approved invalidation barrier supports separate adoption then mutation statements; both same-data-modifying-CTE probes reject. This candidate implements neither mechanism.

Workspace corpus, notes, units, artifacts, index generation/invalidation and hybrid retrieval remain required subsequent grants/delivery. Pure set projection is not lexical search evidence. Full hybrid/provider relevance remains untested, and no paid backfill/evaluation was performed. A1 private-memory exclusion is unchanged.

Durable write-back for this bounded lane is this evidence file. Controller owns integration/commit and the original reviewer owns acceptance.


## 2026-09-29 current delivery addendum

The earlier file table and 1647-run record above identify the historical 22ec11d6 test candidate. Its complete original bytes have no verifiable retained copy; the exact historical diff cannot be recovered. No claim that the later edit has been proven to remove only the loader or preserve the full test body is made. The historical identity/results remain recorded, without treating reconstruction failure as evidence of a body change.

Current test source 737a5a85b8aa46331790b4cfe83c9e0302c72894e8352bc5b73788f7f5f6daee received fresh independent full-source bounded ACCEPT in reviews/issue42-history-ci.md §8, review SHA 8d7b9e82d93a8efe179eeee33c1f22ffe03f0d5cd5fc4c782d51d1d89f121b84. The basis is the complete current 42-case semantic review, same-hash 101 execution with image59, independent 20-page accumulated complete-request control and 24 rejection controls. These extra controls are reviewer evidence, not extra committed CI tests.

The controller has since integrated real owner43 policy/init into this checkout; the old sibling environment command above is historical reproduction only, not the current delivery path. Current imports and dedicated workflow use checkout-local modules. See issue42-history-ci.md and controller evidence for exact current commands/limits. Frozen install and hosted workflow remain pending. No source issuer/index/native or image activation is implied; full workspace/notes/units/artifacts/hybrid obligations remain.
