# Issue #25 conflict investigation

## Candidate and dependency

- Issue: https://github.com/Gujiassh/citeframe/issues/25
- Worktree: `D:/Code/citeframe-conflict-investigation`; branch: `work/issue25-conflict-investigation`.
- Stack: #28 prerequisites → #29 autonomy → #25 investigation. Base is #29 `5bfee6a0f9a7d8466d72b11a961cc5446fa7bca1` (includes #28 `a02dbfbb50826f0a362faa319aa0f1794898fe65`). Local normal merge: `53f66e0`; initial candidate checkpoint: `18f91da`.
- The initial repair1 1,989-file overlay was verified against embedded recipe pins and remote #29 `de66244`; only line endings differed. Overlay content is upstream input, not part of the #25 feature commits. No canonical or architecture-lane writes.
- Recipe SHA256: `dad2025355cf034af625f0aec245398197446e7805ec086282f30b6632c895fd`; frozen source manifest: `5bac5ae0b4fc865b8a6c929ae84151906a9e443cf00e3949cc23022b64e915e2`.

## State and persistence contract

The candidate adds workflow v4/Agent IO v3 with an explicit investigator role. Existing v2/v3 versions remain frozen. Gate operations persist request/result hashes, original sources, inspection conditions, revisions and separate verifier/critic outputs in `research_conflict_turns`, keyed by step/operation number with snapshot and attempt lineage.

States are started/succeeded per operation, with phases inspect/search/verify/critic/finish. The Worker allows three inspections and two targeted searches. Persistence caps journal indices, inspections, search count and normalized duplicate queries. A lease reservation precedes dispatch. Completed operations replay; unfinished external operations terminate unresolved without redispatch. Permission, cancellation, budget and frozen-scope guards are reused.

Corrections retain separate deterministic IDs, original-claim IDs and evidence handles. They must pass the original verifier and combined critic, including other supported findings. Exact source quotes and literal version/environment/time/conditions are required; unavailable conditions remain null. Original claims are not rewritten. The current candidate resolves the complete conflict set together; partially successful revisions are retained as intermediate turn history, while final unresolved output keeps originals and important gaps.

Preparation and final adoption share a workflow-selected renderer. Adoption checks current journal hashes, frozen source fingerprints, original claim/evidence links, source tool ownership and attempt provenance. Journal tampering after upload prevents artifact adoption and triggers compensation. The Markdown publication envelope remains final-report-v1, selected by frozen workflow; v4 adds original conclusions, verified revisions, source excerpts/conditions, queries, reason and gaps. Historical artifact Claim associations still refer to originals; the API's separate conflictInvestigation field and report appendix carry corrected conclusions. Existing edited-report persistence is untouched.

## Migration and deployment

- `p0d1e2f3a4b5` now installs the checked-in v3 JSON release data using reflected SQL tables, independent of runtime publisher defaults. It keeps v3 five-role/autonomy semantics.
- `r2f3a4b5c6d7` follows q1, creates the journal and installs frozen v4 six-role release data. Downgrade is forward-only to avoid losing investigative history.
- Deploy #28/#29 dependencies first, run migrations through r2, then deploy matching API/Worker/Web together. Do not deploy a Worker lacking the v4 prompt/IO contract against a new default v4 run.
- SQLite migration-slice tests compare p0/q1/r2 applied together with p0 followed by q1/r2 in a new process. They compare actual workflow/prompt/hash/schema rows and prohibit invoking the runtime publisher. This does not establish full production PostgreSQL-chain compatibility.

## Verification ledger (2026-09-23)

The deterministic suites use own-worktree PYTHONPATH with the existing Worker virtualenv interpreter; no paid provider or credential files were used. Supplemental retrieval tests inject a local embedding/retrieval fixture, while exercising real frozen-evidence services and ledger writes. Publication tests use production service functions with SQLite and an in-memory object store.

Commands from the worktree:

```powershell
$root=(Get-Location).Path
$env:PYTHONPATH=(@("$root/apps/api/src","$root/apps/worker/src") + (Get-ChildItem packages -Directory | ForEach-Object { "$($_.FullName)/src" })) -join ';'
$env:PYTHONDONTWRITEBYTECODE='1'
$tests=Get-ChildItem apps/api/tests/test_research*.py | ForEach-Object FullName
& D:/Code/citeframe/apps/worker/.venv/Scripts/python.exe -m pytest @tests apps/api/tests/test_persistence_boundary.py -q
$tests=Get-ChildItem apps/worker/tests/test_research*.py | ForEach-Object FullName
& D:/Code/citeframe/apps/worker/.venv/Scripts/python.exe -m pytest @tests -q
pnpm --dir apps/web test
pnpm --dir apps/web exec tsc --noEmit
pnpm --dir apps/web lint
pnpm --dir apps/web build
```

Final broad results: API Research/persistence boundary 275 passed, 1 skipped; Worker Research 107 passed; Web unit tests 140 passed; TypeScript, lint and production build passed. The final rerun includes source-provenance, tamper-compensation and targeted-search ledger cases. Logs are retained locally under `.local-issue25/`; see `docs/evals/issue25-conflict-investigation-20260923.md` for the evidence map.

Browser command: `pnpm --dir apps/web exec playwright test --config ../../.local-issue25/playwright.config.mts --grep Investigation`. Local configuration starts only this worktree on unused port 3305 and launches installed Chrome with an isolated profile. Four mocked-API scenarios passed: resolved source lineage, unresolved gaps, cancelled state, historical no-journal run; reload preserves returned state. Screenshots were visually inspected for source conditions and gaps. This is frontend regression coverage, not real-service or retrieval-quality acceptance. Mock session avatar warnings remain outside #25.

## Acceptance gates

- PASS (deterministic scope): bounded orchestration, source-backed condition checks, verifier/critic requirement, no-new/repeated-query stop, budget stop, replay/ambiguous-outcome behavior, cancellation/permission checkpoint guards, frozen source/tool lineage, migration-slice restart, report adoption and post-upload tamper compensation.
- PASS (frontend fixture scope): sources, original/corrected conclusions, queries, unknown conditions, gaps, historical absence and reload; tsc/lint/build.
- BLOCKED: no local PostgreSQL/docker/psql/pg_ctl available and no live API/Worker/object-store services configured for this lane. Full database migration chain, service process restart and a visible service-backed end-to-end walkthrough remain unverified.
- BLOCKED: real provider/retrieval-quality acceptance has no service/fee authorization. Deterministic fixtures do not demonstrate quality improvement.
- PENDING: remote CI, independent Hubble Critical review and any further upstream #29 delta regression.

The PR stays draft. No merge, release acceptance or completion of issue #25 is claimed. Subsequent #29 changes must be merged normally with the feature delta preserved.


## Hubble P1 follow-up: nullable live-gate input

Independent review found that lease creation permits a null Step input and stores SHA256(step.id) on its Attempt, while the investigation live-gate source validator compared against raw null. The correction uses the exact lease hash rule and retains wrong-hash rejection. Source validation also checks tool workspace and evidence run/workspace/capture ownership explicitly.

A 14-case null/explicit-input matrix covers valid current attempts and wrong attempt hash, changed Step hash, tool workspace/snapshot, handle run and evidence run. Before the fix, the nullable positive and two scope-negative cases failed; after the fix all pass. The frozen search/load service integration now covers both null and explicit Step input and invokes source validation on the newly retrieved handles. Targeted investigation/publication/adoption tests: 41 passed. Broad API Research plus boundary: 290 passed, 1 skipped. These results use local deterministic/SQLite fixtures.

The dependency base remains #29 `5bfee6a`; nullable **finished-attempt replay** still depends on Franklin's pending #29 integration of #28's adoption fix. This local live-gate repair does not establish that pending combined path.

CI at prior HEAD `d619d719` passed all Worker jobs and both Web jobs. API reported 837 passed, 2 skipped, 3 failures: two existing A2 pending-human-plan assumptions are handed back to Franklin; the third was the asset migration test expecting q1's downgrade error while r2 now rejects first. The latter test now expects r2's forward-only message. That PostgreSQL assertion needs a new CI run; no local PostgreSQL run is claimed. PR remains draft and the real-service acceptance gates stay open.


## Explicit v4 feature oracle and upstream integration

Normally merged #29 `b1f7423e5595d81d408d89de4ca565825e5c4e3b` in `ab704253d63c89ef95af287239a71eeffd79a850`. Both appended browser-test groups and SSoT sections were retained when resolving the two append conflicts. The R2 difference whitelist and F1 historical comparator remain unchanged.

Issue #25 adds `a2a_conflict_feature_oracle.py` as an explicit F2 projection before F1/R2: historical investigation table schema must be exact and its rows empty in all snapshots; only a null investigation field on a recognized historical run DTO may be removed; the current default must be v4/Agent IO v3 before projecting the default-version observation for the v3-era comparator. Existing historical responses and events retain their original handling. R2 still rejects unapproved changes.

The current-default B scenario now executes actual POST creation, production scheduling, investigator, real frozen evidence service with scripted retrieval, durable no-new-evidence termination and final publication. Its separate feature assertions check v4 prompt identities, journal hashes/phases/snapshot/attempt lineage, source linkage, original claims and unresolved report gaps. A and AStored continue to restore historical v2 state and idempotency records. C restores an original persisted v3 creation state exported by the fixed #29 b1f7423 runner, installs v4 beside it, and completes with the original v3 manifest/prompts/IO and no investigation journal. This C evidence starts before approval; it does not claim recovery of a pre-existing approved v3 snapshot.

The exploratory dirty-worktree runner passed A/AStored/B/C and five real serialized-SSE→Web-parser checks. Its report is `.local-issue25/v4-feature-integration.json`; it is not same-HEAD acceptance. On that raw report, all 33 R2, 6 F1 and 10 F2 negative controls reject; nullable running/completed-attempt source plus publication/migration targeted suite: 64 passed. A clean committed-head rerun is required for delivery. PostgreSQL/object-store/process/UI production acceptance remains open.


## Dependency cfc0e728 integration and bounded local regression

Verified the public #29 HEAD `cfc0e728fb3dca82a097088a0dc5038cd833b926` with `gh pr view 29`; normal merge commit `f185aa521fd051f25edb3805198a8eedb89d013c` retains the #25 delta. The prerequisite is #28 `ae3fd6fbccb260c9e5851cbb4a57e2c549f6702f`. The cfc increment only strengthens replay request-body rejection and the unchanged Research/human-decision database projection. No R2 whitelist, R2 publication oracle or F1 historical comparator changes were introduced by #25. V4 changes remain in the explicit F2 oracle. Historical artifacts were not rewritten.

At f185aa5, with lane-owned environments and no paid provider:

- `PGCONNECT_TIMEOUT=2; apps/api/.venv/Scripts/python.exe -u -m pytest apps/api/tests -q -ra`: **844 passed, 27 failed, 7 skipped** (`.local-issue25/cfc-api-bounded.log`). The three A2 executable/facade/plugin-pollution tests pass, including the 33 R2 / 6 F1 / 10 F2 rejection controls. Six skips require PostgreSQL; the seventh is the runner-only probe. The earlier unbounded-connection run was stopped and is not counted as complete.
- The 27 API failures comprise 22 historical M402 hash/provenance checks, two R100 taxonomy-hash checks and three storage subprocess timeout/lifecycle checks on Windows. `windows-hash-diagnostic.json` confirms CRLF worktree bytes for the sampled M402 harness/artifact and R100 taxonomy normalize exactly to unchanged cfc Git blobs; the artifact/taxonomy LF hashes match their recorded hashes. These files are outside the feature delta. Storage timeouts remain local failures; no portability fix or passing baseline is inferred. No frozen artifact, hash whitelist or unrelated production code was changed to suppress failures.
- `PGCONNECT_TIMEOUT=2; apps/worker/.venv/Scripts/python.exe -m pytest --strict-markers apps/worker/tests -q -ra`: **569 passed, 1 skipped** (`cfc-worker-all.log`), including fast, acceptance and evaluation markers. The skip is the unavailable Windows directory-symlink capability.
- Web unit **140 passed**; TypeScript, lint and production build passed. Installed Chrome on lane-local port 3305: **7 passed**, covering four investigation cases and three upstream initial-failure/retry cases (`cfc-browser.log`). These browser tests use API fixtures, not a service-backed acceptance environment.
- Investigation/source/publication/adoption/migration targeted regression on the merged b1 source: **64 passed** (`b1-affected2.log`). It covers nullable and explicit Step input on running and completed originating attempts.

The delivery also formats the three new F2 oracle/test modules; AST comparisons against f185aa5 are identical. This is a readability-only change. Final clean-commit evidence is generated after the delivery commit with:

```powershell
$env:PYTHONUTF8='1'
& ./apps/api/.venv/Scripts/python.exe infra/scripts/run-a2a-differential.py --root D:/Code/citeframe-conflict-investigation --output .local-issue25/delivery-fixed-head-a2.json
```

The report must identify the public delivery commit, `repairSnapshotDirty=false`, `candidateSemanticDirty=false`, accepted A/AStored/B/C scenarios and five production Web SSE parser results. Its exact SHA/results are recorded in draft PR #30 and the linked dev-workbench delivery checkpoint; exploratory dirty reports do not substitute for it. C remains a restored pre-approval v3 task, not recovery of an already approved v3 snapshot.

Local full-suite failures, the six unavailable PostgreSQL checks, actual object-store/service restart and visible real-service UI acceptance remain open. CI for #29 cfc passed all six jobs; that is prerequisite evidence only. #30 requires its own current-SHA CI and independent Hubble review. All stacked PRs remain draft and unmerged.


## Service rework and review repairs (2026-09-24)

Journal replay and final projection bind origin/current Attempt lineage and frozen inputs. Critic validation requires the complete unchanged supported fact set plus verified revisions. New integrity regressions are red against e27 and green on this delta. The service fixture now upgrades an already-approved v3 snapshot to a default-v4 deployment, finishes it under old bindings, edits and restarts the API, and separately verifies new tasks select v4. Real PostgreSQL fresh/staged migration and actual API-produced resolved/unresolved pages have passed locally.

The crash matrix intentionally uses process exit86 and natural short fixture lease expiry; it does not modify database clocks or synthesize recovery rows. It exposed a prerequisite Step-error lifecycle defect: reclaimed gates succeed on attempt 2 with stale lease_expired, which correctly fails final adoption. Franklin is repairing that R2 transition; recovery acceptance remains open until normal dependency integration and rerun. Original journal rows, original claims and external-call counts are exact recovery oracles. Detailed commands, results and pending gates are in `docs/evals/issue25-conflict-investigation-20260923.md`.


### Integrated prerequisite and acceptance scope

Dependency #29 e607aaeb (including #28 e8f71d8) is normally merged. The recovered-Step error lifecycle repair now allows actual conflict recovery to reach final publication; the exploratory complete PG/S3/process matrix is 19/19 passed. Final fixed-HEAD evidence is emitted per test case by the committed harness and recorded in the PR/workbench ledger. Approved-v3 coverage starts after a researcher has completed, preserves the submitted approval plus snapshot/prompts/assets, and resumes report/edit semantics under the old binding after v4 becomes default. Login fixtures validate HTTP 200 and actor identity before visible-UI handoff. Browser session/UI acceptance is still blocked by frontend process startup policy, and Windows storage timing instability remains explicitly open.


### Same-head service proof and inherited-fixture compatibility

Clean e8b015b passed the full 19-case real-service matrix; per-case source records and the twelve-boundary recovery matrix preserve exact provenance and accounting. The inherited R2/W1 service provider also needs an explicit frozen-v4 investigator branch; its old five-role implementation raises KeyError before publication. The #25 extension returns source-inspected bounded unresolved output, preserving all historical fixture responses and prerequisite recovery/edit assertions. New provider contract RED/GREEN is 1 failed/6 passed versus 7 passed. Final combined CI includes these provider checks and both complete real-service workflows; UI/session remains a separate blocked gate.

### Architecture-integrated delivery (2026-09-24)

The isolated delivery branch normally merges #29 fcaf then ecc, preserving the accepted main5ed layout and the inherited deadline/publication fixes. Investigation/core/handlers/schemas use `ai_pdf_worker.research`; investigator generation and journal outcomes use the split runtime adapters. No flat production module is restored. The p0 frozen historical-v3 installation and r2 v4 migration retain their feature semantics.

Deployment acceptance gains a separate default-v4 oracle with persisted investigation journal and received-wire linkage; unknown releases and foreign approval/run/workspace/revision bindings fail. Existing R2 equality exceptions are unchanged. The142-path fixed product manifest retains source provenance and needs independent review for the new mapped feature/oracle delta. Real archived approved-v3 execution, resumed publication/edit after upgrade, and actual resolved/unresolved API page data pass the exploratory mapped-service run. Final-HEAD complete service matrix, CI and Hubble review are recorded separately in the delivery ledger. Browser-session/visible UI remains pending normal user startup; the frozen7d6 API50606 source and handoff are retained without modification.
