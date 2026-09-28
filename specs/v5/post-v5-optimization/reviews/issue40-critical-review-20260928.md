# Issue40 independent Critical review

## Final exact-SHA verdict

**Code/security: ACCEPT with bounded residuals** for `5903d60b7103d32d7d8a0c173691250407460b13` only.

**Delivery-manifest admission: ACCEPT** for the exact manifest blob recorded in E9, against accepted product SHA5903d60. No additional code-security or manifest rework finding was identified.

**Integration/delivery: MERGE HOLD.** The controller confirms all six core CI jobs green at SHA5903d60, including closure of the two earlier test failures. Conflict-services, research-services and R800 remain blocked by the unchanged pinned MinIO image gate. Historical R800 infrastructure unauthorized failure is also confirmed by the downloaded artifact inspected here. Local admission verification does not establish runtime CI success. No image/workflow substitution, gate bypass, merge or total-delivery approval is granted.

Date: 2026-09-28, Asia/Shanghai. Baseline: `8812fda4d69b7f0e654e749c357fa05b5e8da72f`. Intermediate product commit: `635bb2b8703ae6c77fee5cb28d08d852bd67b7ae`. Branch: `refactor/workspace-access-dependencies`; draft PR47. The tracked worktree was clean at the initial final-code verification. At the later delivery-only review, HEAD still equalled the accepted SHA; pending changes were the manifest, Issue40 ledger/evidence and this review artifact, plus excluded untracked Issue41 documents. Product paths remained unchanged.

No unresolved High/Medium code-security finding remains in the reviewed scope. F1's fixture acceptance blocker is closed; F2 is an explicitly accepted low-severity design tradeoff. Any subsequent product/test/evidence delta requires review before extending this verdict.

## Governing goal and review ownership

The actual controller-fetched Issue40 body was read from `.local-runtime/artifacts/issue40-controller-issue.md`. Outcome: shared typed WorkspaceAccess and member/owner request dependencies across jobs/model-settings and all applicable workspace routes, with real cross-workspace denial and unchanged valid behavior, role semantics, public errors, internal-token trust boundary, resource scoping and write protections. The selected composition preserves validation-first precedence through route-specific validated-input wrappers.

The reviewer read the active Windows rules, MEMORY-POLICY, project-architecture skill, relevant SSoT/specifications, source/test changes, developer evidence and controller browser record. Private MEMORY.md was not read. Product/tests/branches/credentials/workbench and Issue41 files were not edited. Only this audit artifact was authored; authorized disposable pytest directories and a reviewer-owned PostgreSQL evidence file were created. The PostgreSQL safety invocation created its own new database and fresh object prefixes, without modifying browser A/B state.

## Finding dispositions

### F1 — Closed: synthetic Research provenance mismatch

Initial references: ignored `runtime/seed.py:63-68`; `apps/api/src/ai_pdf_api/services/research/research_views.py:526-546`; `research_artifacts.py:49-61`.

Initial independent observation: the generating attempt succeeded, but `attempt.output_sha256 != artifact.content_sha256`; full domain validation raised `research_artifact_chain_invalid` and the API returned 410. The seed had replaced the report bytes/hash without updating this fixture provenance link. No permission-refactor defect was established.

The original developer repaired only the designated synthetic attempt link; the product validator is unchanged. This final review independently rechecked:

- matching attempt/artifact hash and successful full `artifact_detail` domain validation;
- artifact detail, content and report-edit GET returning 200 for both owner and creator (six live reads);
- downloaded original bytes matching the expected original SHA-256;
- saved user edition version 5, `verificationStatus=unverified`, original hash preserved.

Controller's recorded actual Chrome walkthrough now covers report creator save, second-tab persistence, stale-tab 409 presentation with draft preservation/disabled Save, and explicit use-latest-version recovery followed by save. These close the previously blocked recorded UI path. Evidence: `evidence/issue40/provenance-repair.json` and `controller-browser-acceptance.md`. No provenance check was weakened.

### F2 — Accepted residual: two short initial SSE sessions

References: `apps/api/src/ai_pdf_api/routers/research.py:496-527`; `docs/ssot/workspace-access.md`.

Independent old/new measurement: initial completed-run SSE uses 1 versus 2 sessions, with the same 4 SQL queries and 1 membership query. The dependency closes its authorization session before the handler reads the scoped run/events in another short session. The controller explicitly accepts this request-boundary design tradeoff.

Residual semantics remain explicit: the initial read-session lifecycle differs from baseline and incurs a second pool checkout/transaction boundary. No demonstrated access leak was found. No write transaction, service lock or polling revalidation moved; no live session is retained for the entire stream. This disposition does not add continuous revocation guarantees to baseline Chat/file streams, nor archive cancellation guarantees to Worker membership checks.

## Final delta review: 635bb2b..5903d60

Reviewed all twelve changed paths, including tests, both oracle JSON captures, oracle helper, browser/model readiness records, model setup helper, PostgreSQL helper/results, CI rework record and delivery ledger.

- **Product identity:** all nine routers retain the reviewed manifest. There is no subsequent API product, Worker product, shared-package, service, schema, timestamp-conversion or workflow change in this delta.
- **Timezone fixture repair:** `http_oracle.py:25-48` restores only this fixture's exact known UTC created/updated timestamps after SQLite ORM loads/refreshes, and only for the current fixture session. Listeners are removed in `finally`. This is fixture input restoration, not product timestamp rewriting or general response-error normalization. Tests exercise expunge/load, expire/refresh and actual HTTP serialization. Native Windows passed; POSIX `UTC0`/`CST-8` switching is skipped on Windows and remains for Linux CI. Prior recorded oracle differences are only the two workspace-read timestamp pairs.
- **Worker direct-call adaptation:** `apps/worker/tests/test_v5b_mixed_workspace.py:1084-1085` obtains access through `require_delete_asset_access` before calling the changed handler. Existing deletion/cleanup/late-ingest non-resurrection assertions remain. No lifecycle assertion was removed.
- **Model browser setup:** helper targets only the designated synthetic A generation configuration, retains an existing same-base fixture key, and performs settings GET/PATCH, not a provider invocation. It must not be rerun during controller editing. This reviewer inspected it but did not run it or alter A settings.
- **PostgreSQL safety helper:** each invocation creates a new database and new workspace/object IDs. It runs migrations without changing schema definitions, calls actual Worker-facing persistence entrypoints and report save service, and labels its seeded adoption-finalizer boundary honestly. No provider or long-running Worker is invoked.
- **Evidence honesty:** controller-browser record is a normal visible Chrome walkthrough, not reviewer-operated browser evidence; synthetic reports/ingestion are not real-model execution or user-value evidence. Historical prior-candidate references are retained as chronology. The exact final review target is the SHA above.

## Architecture and policy conclusions

Membership/archive lookup remains centralized in `routers/deps.py`; WorkspaceOwnerDependency.check applies owner policy with route-specific error details. Validated body/query wrappers authorize after validation and pass the same typed input to the handler. They do not acquire new write locks or own commits/rollbacks. Existing-user variants preserve the 401-versus-404 distinction; public auth, health/metrics, and workspace collection routes remain separate.

All 56 workspace-path operations were evaluated through actual request execution, not return annotations alone. With valid inputs, outsider requests produce the expected denial envelope, execute one membership query and leave all mapped rows unchanged. Router+parameter+nested-owner execution confirms request-cache sharing, object identity and one query per request. Resource queries retain workspace/parent predicates; dual-membership tests exercise A paths with B resources. Thread creator-or-owner and Research action-specific owner exceptions remain domain rules.

Report creator identity, refreshed run locks, transactional membership share locks, artifact/base/hash validation and version CAS remain in unchanged services. Owner status does not grant another creator's report-edit privilege. Worker claim/heartbeat/provider/adoption checks were not replaced by request-cached access. Fresh-session Research SSE polling revalidation remains.

## Independent execution evidence

### E1 — Earlier Critical selection on identical product: 163 passed

Using `apps/api/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q` and a fresh GUID reviewer basetemp, executed:

`test_workspace_access_dependencies.py`, `test_workspace_permission_precedence.py`, `test_workspace_router.py`, `test_workspace_model_settings.py`, `test_research_report_edit.py`, `test_research_router_basic.py`, `test_research_router_plan.py`, `test_research_router_recovery.py`, `test_research_router_artifacts.py`, `test_research_publication_adoption.py`, `test_evaluation_api.py`, `test_notes_router.py`, `test_chat_router.py`, `test_asset_router_http.py`, `test_asset_router_lifecycle.py`, `test_research_adaptive_recovery.py`.

Result: **163 passed**, one existing TestClient/httpx deprecation warning, 152.24s. Covers baseline/error isolation, legitimate writes, report CAS/integrity/noncreator denial, SSE revocation, publication before/after PUT and reconciliation, and rejection side effects. These publication tests are SQLite/fixture-store evidence, not PostgreSQL stress.

### E2 — Earlier Worker runtime selection on identical product: 35 passed

```powershell
$tmp = '.local-runtime/artifacts/issue40-review-worker-' + [guid]::NewGuid().ToString('N')
apps/worker/.venv/Scripts/python.exe -B -m pytest -c pytest.ini -p no:cacheprovider --basetemp=$tmp -q apps/worker/tests/test_research_runtime.py apps/worker/tests/test_research_runtime_integration.py
```

Result: **35 passed**, 165.65s. No long-running real Worker/provider claim is inferred.

### E3 — Final-SHA focused reruns

```powershell
$tmp = '.local-runtime/artifacts/issue40-review-final-api-' + [guid]::NewGuid().ToString('N')
apps/api/.venv/Scripts/python.exe -B -m pytest -c pytest.ini -p no:cacheprovider --basetemp=$tmp -q apps/api/tests/test_workspace_access_dependencies.py apps/api/tests/test_workspace_permission_precedence.py apps/api/tests/test_research_report_edit.py apps/api/tests/test_workspace_model_settings.py
```

Result: **37 passed, 2 skipped**, one existing warning, 23.94s. The skips are only the POSIX timezone-switch cases on Windows; native-host UTC fixture load/refresh/HTTP coverage passed.

```powershell
$tmp = '.local-runtime/artifacts/issue40-review-final-worker-' + [guid]::NewGuid().ToString('N')
apps/worker/.venv/Scripts/python.exe -B -m pytest -c pytest.ini -p no:cacheprovider --basetemp=$tmp -q apps/worker/tests/test_v5b_mixed_workspace.py::test_delete_route_cleanup_and_late_ingest_cannot_resurrect
```

Result: **1 passed**, 1.69s. This independently verifies the exact repaired direct caller; the developer's broader Worker acceptance result is separately 58 passed / 411 deselected.

### E4 — Independently regenerated exact old/new contracts

Fresh child Python processes loaded the nine baseline routers directly from `git show 8812fda:<path>` using a read-only in-memory import hook; the second process used final candidate source. Both invoked the final fresh-database-per-case oracle.

- **378 baseline cases / 378 candidate cases: exact equality**, without additional timestamp removal in the comparator.
- The oracle itself omits Research requestId and replaces generated successful-thread ID/createdAt/lastMessageAt with a marker. Its workspace timestamps are fixed fixture inputs. All remaining payload/status/detail fields compare exactly.
- **64-operation OpenAPI equality**, sorting parameter presentation order only.
- Finite matrix scope: identity, owner/member/outsider/unknown-user failures, invalid body/query precedence and selected valid requests. Successful business persistence and resource integrity are supported by the separate tests/live/UI evidence.

### E5 — Independent live negative/read probes and repaired artifact follow-up

Earlier live probes against API18400/PostgreSQL18432/MinIO18410 returned all 27 expected denials: missing/invalid internal token, missing user, unknown-user workspace 401 versus job 404, A-only member targeting B, B owner targeting A, dual owner using B asset/job/note under A, foreign note PATCH and asset DELETE, member settings restrictions, validation-first cases, SSE Accept/cursor/membership ordering, wrong-workspace Research resources, and owner-but-noncreator report PUT.

Six positive reads passed. Initial completed-run SSE returned four contiguous synthetic ledger events and correct cache header. Every mapped-table row snapshot and object name/etag/size inventory was unchanged across the negative/read block. Snapshot sessions were PostgreSQL read-only. No paid calls, fixture reset or controller browser-state mutation occurred.

Final follow-up independently verified F1's six successful repaired reads/full validator, user-edition version 5/unverified/original-hash preservation, and generation revision 4 with the controller-saved model name and configured-key flag. No credential value or report body was printed. These read checks support, but do not replace, the controller's visible interactions.

### E6 — Independent real PostgreSQL 17.11 six-check safety run

Reviewer output: `.local-runtime/artifacts/issue40-review-final-6d25bcf77e4346f893410da164b402c5/postgres-safety.json`.

Database: `issue40_safety_24c3cdf8d5fb`; migration: `s3a4b5c6d7e8`. The existing ignored runtime credentials were used in memory. The source was executed unchanged except exact substitution of its output-file assignment to a fresh reviewer-owned path. No assertions, product calls, fixture state or safety logic were altered; the developer's sibling JSON hash was verified unchanged.

Invocation orchestration:

```python
source = Path('specs/v5/post-v5-optimization/evidence/issue40/postgres_safety.py').resolve()
s = source.read_text(encoding='utf-8')
needle = "output = Path(__file__).with_name('postgres-safety.json')"
assert s.count(needle) == 1
# out is a newly allocated reviewer-owned local artifact path.
exec(compile(s.replace(needle, 'output = Path(' + repr(str(out)) + ')'), str(source), 'exec'),
     {'__file__': str(source), '__name__': '__main__'})
```

All six checks passed:

| Check | Independently observed result |
| --- | --- |
| Revoked creator before Worker claim | 403 research_permission_denied; run cancelled; zero attempts |
| Revoked creator before heartbeat | 403; run cancel_requested; existing active attempt retained by cancellation protocol |
| Revocation after synthetic upload, at adoption finalizer | Intent compensating; run cancel_requested; zero final artifacts/completion events; uploaded bytes unchanged |
| Concurrent first edition saves, expectedVersion 0 | Exactly one 200/version1 and one 409 version conflict |
| Concurrent subsequent saves, expectedVersion 1 | Exactly one 200/version2 and one 409 version conflict |
| Revocation after preliminary membership read while run-lock wait observed | pg_stat_activity confirmed Lock; after revocation commit/unblock, service returned 403; full edit row and original object hash unchanged |

Scope limits: the adoption test starts from a seeded durable uploaded intent and calls the real finalizer; it does not exercise successful-output provenance, end-to-end publication preparation or compensation completion. The object remains present for pending compensation, as asserted. Report tests use actual object bytes/hash with synthetic completed-report state. Full view provenance is separately verified by F1 closure. Worker entrypoints are invoked directly; no broad multi-Worker stress, crash/restart schedule or exhaustive revocation-interleaving sweep is claimed. New databases/prefixes are retained for controller-managed disposal; existing A/B state was not used.

### E7 — Controller visible browser evidence accepted within its recorded paths

`evidence/issue40/controller-browser-acceptance.md` records actual Chrome, normal login and controls, with no browser storage/session injection or route mocking:

- owner A/B visibility and A selection;
- workspace prompt and Notes save/full reload;
- required-input feedback for empty model base;
- successful owner model-name save/reload at revision4, credential field untouched, no provider call;
- A-only member visibility, disabled settings and absent owner model panel;
- direct B navigation denied without B contents;
- report creator save, second-tab persistence, two-tab conflict/draft retention and explicit recovery/save.

This is controller-operated visible evidence, not an independent reviewer browser session. It was recorded on 635bb2b and applies to final 5903d60 because product source is identical. It does not establish every UI action, real-provider Research completion, model quality or real-user value.

### E8 — CI and secret/delivery hygiene

`git diff --check 8812fda..5903d60` passed. Exact-value scan of candidate changed files against six ignored runtime secret fields plus the synthetic provider key returned no matches. This bounded scan is not a universal credential audit.

The original Windows full API run had 983 passed / 11 skipped / 5 baseline-reproduced environment failures. Initial Linux CI on 635bb2b ran those previously environment-limited areas and instead exposed the two diagnosed test issues: API 992 passed / 6 skipped / 1 failure and Worker acceptance 57 passed / 411 deselected / 1 failure. This reviewer inspected the saved log and final fixes. The final focused reruns passed. The later controller-confirmed CI update below closes those two failures; required runtime gates remain open.

`gh pr checks 47 --repo Gujiassh/citeframe` from this lane failed because the environment denied GitHub network access. Current GitHub statuses are therefore attributed to the controller, not independently fetched by this lane. Controller-confirmed SHA5903d60 results:

| Core CI job | Controller-confirmed result |
| --- | --- |
| api | pass; 996 passed, 6 skipped; Alembic upgrade/check reports no new operations |
| worker-acceptance | pass; 58 passed |
| worker-fast | pass |
| web | pass |
| web-e2e | pass |
| evaluation | pass |

The reviewer independently read `.local-runtime/artifacts/issue40-r800-ci-5903/r800-baseline/infrastructure.err`: the historical baseline attempted postgres/redis/minio pulls and failed with `minio Error unauthorized: access to the requested resource is not authorized`, followed by the daemon unauthorized error. This corroborates the historical infrastructure failure without claiming independent registry access or concealing baseline failure. Conflict-services, research-services and R800 all require successful actual runtime execution on the final package. No workflow/image substitution or gate bypass is approved.

### E9 — Delivery-only R800 admission review

**Disposition: pass / ACCEPT for exact-source manifest admission.** The unchanged product/test acceptance remains pinned to `5903d60b7103d32d7d8a0c173691250407460b13`. Reviewed actual pending manifest diff, the appended 63-line Issue40 ledger section, and `evidence/issue40/r800-delta-admission.json`; no broader product authorization is implied.

Manifest: `specs/v5/worker-layout/integrated-product-delta.json`.

| Identity | Value |
| --- | --- |
| Previous committed manifest Git blob at SHA5903d60 | `6882401c53f3a2d7a54aa76f33bee04f03240295` |
| Reviewed pending manifest Git blob (`git hash-object`, without writing) | `b1c772cdb2e7bef9fb6b50d3d6fd477552155f92` |
| Reviewed raw-file SHA-256 | `c209c3909e1f3d8f4f89e99ee8ade989ec4af8b836d1f5699c90e1f7b13c8f0c` |
| Unchanged architecture base | `5ed02c8b7b5f357f58d1c3fd270ead0718e7afbf` |

Independent assertions compared old/new complete JSON records and actual Git objects, in addition to reading the diff:

- The 16 changed admissions exactly equal the Git-derived Issue40 baseline8812fda-to-candidate5903d60 delta under unchanged `PRODUCT_PATHS`. There are 10 added admissions, 6 updated, no removals or duplicate paths, and 217 unrelated entries preserved structurally in full. Total admission count is 233.
- All 16 have source head exactly SHA5903d60, source path exactly their actual path, and both source/integrated blobs exactly `git rev-parse 5903d60:<path>`. The candidate-byte transformation label agrees with those objects.
- Each updated entry's `inheritedProvenance` equals the complete previous admission, with the evidence `previousAdmission` equal to that record. Its old integrated blob also equals the actual Issue40 baseline path blob. Historical source-head ancestry and source-path/blob resolution were independently checked for all six retained records, recursively where applicable.
- Schema version and architecture base are unchanged. Previous source heads and functional-oracle entries remain intact; only SHA5903d60 and the bounded Issue40 oracle were appended. Previous scope text remains as a prefix. Candidate SHA5903d60 is the current reviewed source/target; the unchanged verifier validates all declared heads as ancestors of the target, including equality for this candidate.
- There is no Issue40 change or pending change to the validator, its tests or `.github`, and no pending change under `PRODUCT_PATHS`. Its exact admission boundary still includes apps/packages/evaluation, deployment Docker/scripts and package manifests; it has not been narrowed to hide product changes. No workflow/image change was admitted.

Exact independently resolved changed-path blobs:

| Path (relative to repository) | Admission | Actual SHA5903d60 Git blob |
| --- | --- | --- |
| apps/api/src/ai_pdf_api/routers/assets.py | updated | `09028f89c0e0d192ac872dd6dbf51e67b64119ab` |
| apps/api/src/ai_pdf_api/routers/chat.py | added | `c74cb92e33cd2a9a528496f3e4991437d00cc9d7` |
| apps/api/src/ai_pdf_api/routers/deps.py | added | `716f999552417032736bc82bafe0a5743bb5d3b6` |
| apps/api/src/ai_pdf_api/routers/evaluation.py | added | `f86fe5c3ed0081003cb174d0abb3502f289b929a` |
| apps/api/src/ai_pdf_api/routers/jobs.py | added | `95fe7dec52569179960bd882d40f71c13df4aba9` |
| apps/api/src/ai_pdf_api/routers/model_settings.py | updated | `c6a91c93325d8f8a2c9f156a53d06b2dbdb9f806` |
| apps/api/src/ai_pdf_api/routers/notes.py | added | `f1ed74abfe159561160626486f45fb5c8a8e0f2b` |
| apps/api/src/ai_pdf_api/routers/research.py | updated | `c8f129e1b3dfdd844c5ca06057270298754748b9` |
| apps/api/src/ai_pdf_api/routers/workspaces.py | updated | `d7191a2d42a17d97b6cd7ee806e5e7a85502edff` |
| apps/api/tests/test_embedding_current_scope.py | added | `4246324c92d2b39a8c39a385614bdd105188b3ef` |
| apps/api/tests/test_embedding_index_contract.py | updated | `640f5dd6a30a032b70578c8a5bb28a70c5e2e647` |
| apps/api/tests/test_image_evidence_lifecycle.py | added | `75c84c3dc915ff8af3db0f089fa82d95496e101a` |
| apps/api/tests/test_image_ingestion.py | added | `0aaec90d3d95608dcc9da8f074378959fb9bcc5b` |
| apps/api/tests/test_workspace_access_dependencies.py | added | `6afe23443c5c361e0a0402f4f11967f37fabcdd4` |
| apps/api/tests/test_workspace_permission_precedence.py | added | `899b726f6132221500b2b53c9c1e721b8d3e4642` |
| apps/worker/tests/test_v5b_mixed_workspace.py | updated | `e0d15faa3af9d72d43e79ca906ff4dfc312a6fd3` |

Independent execution:

```powershell
apps/api/.venv/Scripts/python.exe -B -m unittest discover -s infra/testing -p test_r800_product_delta.py
```

**6 tests passed**, exit 0, using the unchanged tests/validator, including duplicate/unknown/missing/changed admission rejection controls. A read-only stdin Python invocation imported unchanged `infra/testing/r800_product_delta.py` and ran `verify_product_delta(Path.cwd(), '5903d60b7103d32d7d8a0c173691250407460b13')`: **pass, 233 exact paths**, exit 0. This verifier reads the pending manifest and compares Git target product blobs, source blobs and ancestry. Independent record-preservation assertions above also passed.

Evidence limit: these are local exact-manifest and validator-control results. They do not establish the R800 deployed exact-PR/negative-control campaign or historical/candidate runtime success. The manifest/evidence's pending-independent-review language records its creation state; this section supplies the subsequent bounded review disposition. Existing functional evidence is retained without extrapolating it to the infrastructure-blocked jobs.

The next package review must be a **read-only exact-final-SHA attestation**: verify SHA5903d60 ancestry, identical accepted product/test blobs, this exact manifest Git blob, only the authorized docs/audit/manifest delta, and final required CI status. A docs-only package can preserve the reviewed product and admission; no unknown future SHA is accepted in advance. No additional artifact edits are needed for that attestation.

## Final area judgments

| Area | Judgment | Evidence / bound |
| --- | --- | --- |
| Goal, architecture, centralized policy | pass | Nine-router source review; same accepted product fingerprint |
| 56 workspace guards, trust boundary, unknown-user variants | pass | Executed requests/SQL, source, oracle and live negatives |
| Owner/member/creator and resource isolation | pass | Dual-membership queries, noncreator denial, actual rejected writes |
| Error ordering, payloads, OpenAPI | pass | Independently regenerated exact bounded oracle and schema parity |
| Request caching and query count | pass | Executed identity/query tests; F2 session tradeoff explicitly accepted |
| Report write and integrity invariants | pass | Service locks unchanged; tests, live reads and actual PostgreSQL CAS/revocation schedule |
| SSE authorization/revalidation | pass | Header/cursor precedence, poll-revocation tests; F2 residual retained |
| Worker revocation and adoption boundary | pass | SQLite regressions, runtime tests and real-PG claim/heartbeat/finalizer checks |
| Full multi-Worker stress/crash/compensation sweep | not applicable to this bounded claim | Not executed; no such coverage implied by six-check pass |
| Recorded visible product paths | pass | Bounded controller Chrome walkthrough plus independent persisted-state reads |
| Final pinned code/delta review | pass | Exact SHA5903d60; product/test bytes unchanged during delivery follow-up |
| R800 exact-source admission | pass | E9 exact manifest blob, inherited provenance, unchanged verifier and six controls |
| Six core CI jobs at SHA5903d60 | pass (controller-confirmed) | E8; not independently fetched by reviewer |
| New schema/migration or frontend implementation | not applicable | No such product changes |
| Final CI/integration/merge | blocked | Conflict-services, research-services and R800 runtime gates remain open; final package SHA attestation pending |

## Critical reverse review

- A typed wrapper that failed to execute membership would fail the 56 valid-input outsider requests, query-count assertions and row snapshots.
- Owner privilege incorrectly allowing another creator's report write would fail both isolated and live noncreator/no-side-effect checks.
- Dual-membership resource leakage would fail A-path/B-resource probes and scoped SQL tests.
- Permission-before-validation drift or duplicated validation errors would fail the regenerated contract matrix for recorded combinations; new inputs require their own extensions.
- Cross-request/poll caching would fail revocation/archive/SSE tests. Transactional report recheck removal would fail the observed-lock-wait PostgreSQL revocation schedule.
- Non-atomic first/save CAS would fail the two independent-session schedules at versions0/1.
- Revoked Worker progress/adoption would fail actual claim/heartbeat/finalizer checks; compensation cleanup correctness remains outside this finalizer-only test.
- Treating report-edit HTTP success as usable UI would have missed F1; full provenance validation and the later visible walkthrough close that specific gap.
- Admitting an unrelated path/blob or losing previous provenance would fail the exact Git delta, complete-record preservation, source ancestry/blob checks and unchanged validator controls in E9. Runtime correctness still requires the separate deployment gates.
- Applying these results to later code would invalidate exact-SHA acceptance. Any delta requires a new bounded comparison.

## Residuals and handoff

1. Merge remains blocked until all required final-package CI is green. Six core jobs at SHA5903d60 are controller-confirmed green; conflict-services, research-services and R800 remain runtime gates. Registry access is not a code-fix authorization or gate waiver. The delivery commit requires the read-only identity/boundary attestation described in E9.
2. F2's extra initial SSE checkout/transaction boundary is accepted and documented, not eliminated.
3. Concurrency evidence covers two CAS schedules and one coordinated revocation wait, plus seeded adoption finalization; no broad stress/crash/cleanup completeness claim.
4. Native Windows cannot run POSIX timezone-switch variants. The controller now confirms the final Linux API suite green; this reviewer did not independently fetch that CI run. Product timestamp code remains unchanged.
5. Browser evidence is the controller's recorded normal paths on identical product source. Synthetic data and fixture keys establish engineering behavior only.
6. Existing Worker archive behavior and baseline Chat/file-stream revocation semantics remain unchanged; no stronger policy is claimed.
7. Reviewer-created isolated safety database/object prefixes remain retained. Controller owns their lifecycle; no deletion was performed.
8. Untracked Issue41 `docs/ssot/memory-management.md` and `specs/v5/memory-management/` were not inspected or changed and are outside this acceptance/delivery grouping.

No additional code-security rework is requested for the pinned candidate. Rework on any subsequent finding remains with the original developer. Reviewer lane is idle and available for follow-up; no commit, push, merge or workbench action was taken.

## Product checkpoint fingerprint

The original inspected worktree, 635bb2b and final 5903d60 share this raw-file manifest:

```json
{
  "apps/api/src/ai_pdf_api/routers/assets.py": "e7d27a94995f0646c00069abc201fd383b598f36a4b855f3d02390414b3be44d",
  "apps/api/src/ai_pdf_api/routers/chat.py": "9062fa3b3592c441fc8917ee76a3892a17821dae10f922a2a229750d49450a73",
  "apps/api/src/ai_pdf_api/routers/deps.py": "ac067cdae26a100c99dc435ee3b5d76f5bcb0084f3b371e30942cf2c11cf38da",
  "apps/api/src/ai_pdf_api/routers/evaluation.py": "3aa7ce54314b4ff4a528c26b30a77b21d68513937ad9c1d8f2a814fa9ec89f1c",
  "apps/api/src/ai_pdf_api/routers/jobs.py": "8de94334de5741445c1fb3815bf4eb601da1d494929bc0cbed41a7bbd128c5bf",
  "apps/api/src/ai_pdf_api/routers/model_settings.py": "dfe1118e2b730d2ea92707c689b406a5d37890b3d8ff240ee4d3cc0f5d14fa62",
  "apps/api/src/ai_pdf_api/routers/notes.py": "ce41505335ba1ca72fc060b5aabaf8c78cbec65e4c232b848b233777d67b100c",
  "apps/api/src/ai_pdf_api/routers/research.py": "304cf9cbea2cdf85cac397a114e8a4dcad480e963c1fcc69afcec46d990feda6",
  "apps/api/src/ai_pdf_api/routers/workspaces.py": "03ed048798fba9b11cb76d96d73bf5993f6d8b5c84e7a277310ff8e302f3ea1a"
}
```

Manifest SHA-256 of Python `json.dumps(manifest, sort_keys=True)` UTF-8: `4dd71da985aa47bb8ea6f3be8ae0ade44978e4efcd1b16bbeb28f3ede02e3349`.

Independent PostgreSQL evidence file SHA-256: `90ee2a5279bfa81eed17868352c1308fdc69510b47696bd7417c1646919bdb3f`.

Durable review write-back is this artifact. No private-memory or controller-owned workbench write was made.
