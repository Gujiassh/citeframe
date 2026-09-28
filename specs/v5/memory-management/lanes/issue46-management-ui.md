# Issue #46 — private management UI/BFF implementation lane

Status: **C1 REWORK PARTIAL — R1/R3/R4 corrected for recheck; R2 awaits the narrowly named lifetime ownership approval below. No acceptance.**
Date: 2026-09-28. Parent #46 and #41 remain open.

## Authority and fixed identity

- Workspace: `D:/Code/citeframe-lanes/issue46-management-ui`.
- Branch: `work/issue46-memory-management-ui`; starting/current HEAD (no Git writes): `9cd93ec1aa70ea803401a88c55834de1593f0aeb`.
- Governing spec v4, final A1, and exact `lanes/issue42-management.md` consumer contract at this commit (SHA-256 `2EBF5D6BD9A9C298D21253C50A9ECAA869AD9AC2A437BFEDF354BF0A961F2802`). The C2 disposition in `reviews/issue42-management.md` authorizes bounded authoring, while admission integration and API runtime remain separate gates.
- #47/#48 remain unmerged prerequisites; `32bb676` and `9cd93ec` are candidate bases, not release/merge evidence.
- Private records are managed only by their authenticated owner, including workspace owners managing their own records. Nothing here registers private content with chat, Research, tools, context, summaries, checkpoints or providers. No new audience/private mode, search/index control, reactivation, pin-only or expiry-only operation is introduced.

## Actual implementation files

Paths below are relative to `apps/web/src/`.

| Boundary | Files / behavior |
|---|---|
| Native entry | `components/settings-panel.tsx`: narrow Memory tab for members and owners; owner-only Evaluation remains gated. Memory remains mounted across Settings sub-tabs so pending identity and unsent draft survive those switches. Existing design/fonts/layout remain unchanged. |
| Feature UI | `components/memory/memory-panel.tsx`, `memory-detail.tsx`, `memory-form.tsx`, `memory-record.tsx`, `memory-source.tsx`: first empty/list, status filter, bounded next page/refresh, mandatory subject/applicability/kind/content, current detail, exact original instruction/provenance/hash/version, history pages, successor selection after correction, deactivate, irreversible delete and unavailable/tombstone display. |
| Feature state | `lib/memory/use-memory-management.ts`: session-local list/detail/mutation orchestration, original immutable request triple, content-free request polling, explicit same-pair retry, no automatic mutation resend, separate operation-result/current version. `use-pending-navigation.ts` keeps workspace view-tab switches from unmounting an unresolved request and asks the browser to warn before document unload. Settings sub-tabs remain usable. Logout/scope changes clear the feature. |
| Client protocol | `lib/memory/{types,client,errors,validation,response}.ts`: strict local DTOs, outgoing allowlists/bounds, fixed error matrix, output discriminator/owner/workspace validation, content-free poll validation, no raw upstream diagnostics. Source response references must match the exact requested tuple. |
| Server-only integration | `lib/memory/server-route.ts` uses existing signed-session and API-header helpers; `proxy.ts` forwards only selected endpoint/method/query/body/Idempotency-Key, with server-owned actor/internal token. Incoming actor/token/authorization/cookies never become forwarded authority. URL identifiers are canonical UUIDs, redirects refused, JSON size bounded, mutation cross-origin requests refused, upstream and browser caches disabled. |
| Admission activation | `lib/memory/activation.ts` deliberately exports `memoryAdmissionEnabled = false`. Both UI submission and BFF create/correct dispatch remain closed. Draft forms are available; no placeholder success or admission clone exists. Controller may change this only after recording the exact independently accepted shared predicate/command/API integration. |
| BFF routes | New `app/api/workspaces/[workspaceId]/memories/route.ts`; `[memoryId]/route.ts`; `[memoryId]/corrections/route.ts`; `[memoryId]/revisions/route.ts`; `requests/[requestId]/route.ts`; `operations/[operationId]/route.ts`; and `sources/read/route.ts`. Next16 promise params are awaited. |
| Copy | `lib/i18n-context.tsx`: memory-prefixed Chinese/English key additions only. One privacy helper, necessary admission/pending/conflict/deletion feedback, and character bounds without token claims. |
| Dedicated tests | `lib/memory/{client,proxy,response,validation}.test.ts`; `apps/web/e2e/memory-management.spec.ts`. All synthetic/route-intercepted tests are fixture evidence. |

No backend, provider, core contract, workspace context/page or sidebar file was modified. The independent reviewer owns `reviews/issue46-management-ui.md`; that concurrent file was read and left untouched. No Git index/config/commit/push/PR write, paid model call, production database action or old-worktree write occurred.

## Recovery and privacy semantics

- New manual mutation gets one UUID request ID and one key; its serialized body is frozen before dispatch. While unresolved, form/action edits are locked. Timeout, network/response failure, `outcome_unknown`, `temporarily_unavailable` and `operation_in_progress` preserve the original request. A request lookup 404 does not release it or create a new identity. Polling is automatic; resending is explicit and preserves exact method/path/body/key.
- Successful receipts select the current authorized resource (correction successor) and distinguish committed `resultVersion` from current resource version. Malformed successes never become an empty list or saved receipt. BFF uncertain mutation failures remain outcome-unknown.
- CAS/terminal conflicts preserve the local form. Refresh reads current authorized state alongside that draft. Adopting a newer version is a separate explicit comparison action; it does not replace typed content. A new conflict resets comparison acknowledgement.
- Owner current/history 410 clears protected detail/history/source/draft for that target; list tombstones contain no invented blank body. Source 410 removes source/body views, with no newest-version fallback. Delete UI promises no undo and explicitly excludes raw archive, backup and provider retention from its erasure claim.
- User/workspace keys fence runtime component state before rendering the new scope. Requests abort on teardown; list/read generations and aborted-signal checks ignore late responses. Authentication/workspace denial unmounts and clears all feature views/drafts. No localStorage, sessionStorage, module-singleton private body cache, persisted Workspace field or shared model-input dependency is added.
- Drafts and unresolved bodies are runtime-only. Forced document unload or explicit logout/scope change discards them; no body is reconstructed or automatically resubmitted afterward. Beforeunload is a browser warning, not durable recovery. Real refresh/restart and authorization-race behavior still need the integration walkthrough below.
- Local BFF structural/session/admission errors are local responses; they do not claim the backend's fresh-membership/error-precedence execution. The backend remains responsible for membership locks, owner authorization, signed cursor validation, deterministic admission, command CAS/erasure and transactions.

## Executed verification and evidence limits

Evidence directory: `specs/v5/memory-management/evidence/issue46/`.

| Check | Actual result | Scope |
|---|---|---|
| Strict TypeScript | exit 0, `typecheck.txt` | Entire web tsconfig, including tests and generated Next route types; strict unresolved identifier/import checks, not only bundling. |
| ESLint | exit 0, `lint.txt` | All `src`, `e2e`, `scripts`, Next/Playwright/ESLint/PostCSS configuration. Generated scratch output excluded. |
| Dedicated unit fixtures | 18 passed, `unit-fixtures.txt` | DTO/bounds/query/key, forged authority, fixed error matrix, no-store, outgoing DELETE CAS/key/body, transport uncertainty, closed admission gate, malformed success, unavailable suppression, owner/workspace and content-free operation validation. Session/fetch doubles do not verify signed cookies or real API authorization. |
| Browser fixtures | 8 passed, `browser-fixtures.txt` | Headless Chromium with intercepted session/workspace/memory/source responses: member/owner native entry, empty/gated form, exact source/history/list cursors, conflict draft comparison, unknown result same-pair replay/poll/tombstone, revocation, mobile width and delayed source after logout. This bypasses BFF/API for data. |
| Mobile fixture screenshot | `fixture-mobile-memory.png`, inspected | Existing shell at 390×844 with synthetic data, dev fallback fonts. Supporting fixture layout evidence only; no actual-API or production-font visual acceptance. |
| Actual Next HTTP, no authenticated API | three 401/no-store checks, `next-unauthenticated-http.txt` | Live Next list/history/request routes without session. Fixed safe body and no-store observed. Does not exercise an authenticated backend request. |
| Production build | **BLOCKED**, `build.txt` | Next16 Turbopack cannot fetch existing Geist/Geist Mono from Google Fonts. No font/layout replacement or mocked build success was introduced. |
| Full existing web unit suite | Not completed | The first direct tsx attempt failed in tooling with `uv_os_get_passwd ENOMEM`. Dedicated fixtures were instead strictly compiled to CommonJS then executed by Node's test runner. Do not report a full-suite pass. |
| Real integrated management API | **NOT RUN** | Backend lane/core activation not integrated at a recorded exact commit. |
| Real visible browser through actual API | **NOT RUN; mandatory before feature acceptance** | No fixture, screenshot or count in this ledger closes this gate. |
| Independent implementation review | Pending assigned reviewer | No self-approval or replacement review. |

An initial fixture run had five selector failures (workspace-tab label and Next's additional alert element); selectors were corrected and all eight final tests passed. These were test-locator failures, with no fabricated API pass.

### Reproducible commands

From repository root:

```powershell
node apps/web/node_modules/typescript/bin/tsc --noEmit --incremental false -p apps/web/tsconfig.json
node apps/web/node_modules/typescript/bin/tsc --target es2022 --module commonjs --moduleResolution node --esModuleInterop --skipLibCheck --strict --types node --typeRoots apps/web/node_modules/@types --outDir apps/web/.next/memory-fixture-tests apps/web/src/lib/memory/validation.test.ts apps/web/src/lib/memory/proxy.test.ts apps/web/src/lib/memory/client.test.ts apps/web/src/lib/memory/response.test.ts
node --test apps/web/.next/memory-fixture-tests/*.test.js
```

From `apps/web`:

```powershell
node node_modules/eslint/bin/eslint.js src e2e scripts next.config.ts playwright.config.ts eslint.config.mjs postcss.config.mjs
node scripts/copy-pdfjs.mjs
node node_modules/next/dist/bin/next build
node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3046
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:3046'
node node_modules/@playwright/test/cli.js test e2e/memory-management.spec.ts --workers=1 --reporter=list
```

`pnpm install --frozen-lockfile --store-dir .pnpm-store` initially returned `fetch failed`. Lane-local Next16.2.10/dependencies subsequently became available via the controller's install (documented by the reviewer); their junction targets were verified inside this lane. No dependency manifests/lockfiles changed. If the controller needs to repeat installation, the exact command is the one above, run at the lane root. No credential request is needed.

Initial generated CommonJS scratch remains at `apps/web/.memory-tests/`; a cleanup command was rejected by execution policy. It is **not product source and must not be included in the controller commit**. Current reproducible compilation writes under ignored `.next/memory-fixture-tests/`. Controller may remove the old generated scratch. Existing old trees/node_modules were not changed.

## Integration/acceptance handoff — still open

1. Record exact approved admission/core/API commits and review evidence; integrate the real owner-management API. Keep the activation flag false until those gates are satisfied. No arbitrary already-running backend or candidate-base claim substitutes for this handoff.
2. Re-run strict type/lint/unit/full-suite/build with normal dependencies/network. Retain the actual build font result; do not change the product typography to make automation green.
3. Connect this actual Next BFF to a disposable actual API database using the unchanged signed-session and server-only internal-auth infrastructure. Use two authorized synthetic members plus an owner, each with own records; never log cookies/internal tokens.
4. Run a **visible browser**, starting at the ordinary sign-in/workspace selection → workspace → Settings → Memory path. Capture bounded screenshots, state, sanitized method/path/status and request-body assertions for empty → create → refresh/current/exact source → correction successor → revision history → deactivate → delete → 410/tombstone. Confirm both members and owners can manage only their own records.
5. Exercise real stale CAS with an unsent draft, same-pair retry after response loss, accepted-request polling including transient 404, distinct result/current versions, all status/list/history pages and refresh, exact-source 410, actor/workspace switches and delayed read/mutation/poll responses, logout and revoked membership. Verify no deleted/unavailable/private old response flashes and no shared prompt/tool/context/log injection.
6. Assigned independent reviewer validates the actual candidate and these evidence boundaries in their own file. Controller owns staging/commit/PR and downstream integration.

Later #46 work remains outside this slice: in-task compaction status, automatic continuation, authorized task resume/retry/cancel, refresh/disconnect/restart recovery and actual chat/Research end-to-end/quality evidence. #46/#41 stay open.

## Bootstrap/write-back

Read applicable profile/workspace/web instructions, SOUL/IDENTITY, MEMORY-POLICY and frontend-design skill. Private MEMORY and dated private memory were not read. `prepare_session` succeeded; project/state/task artifacts were read. GitHub remote and local/global identity were inspected read-only and match. Actual installed Next16 docs were read before framework code (read-only existing installation first, then controller-installed lane-local docs): route handlers/promise params, server/client boundaries, BFF, cookies and server-only imports. Existing design remains the visual authority.

Durable lane state and verified evidence are recorded here; private/shared profile and workbench writes are outside this writable boundary. Controller can checkpoint `memory46-management-ui` with this candidate, the fixture/strict-check results and the pending independent/API/visible/build gates.


## C1 rework handoff — R1/R3/R4 corrected; R2 ownership decision pending

Read the entire original Critical C1 review. Reviewer artifact and all `.memory-tests/` scratch remain untouched. This rework used no Git commands/writes or model calls. Activation remains false. The review relays accepted admission `893de95` integrated in API `7d47607`; that is controller-reported dependency progress, not an independently verified accepted API in this lane. The disabled-feature copy now accurately waits for accepted API integration.

### Actual fixes

- **M46-R1:** feature-owned `invalidate(id, reason)` removes the target's cached list projection, clears receipt metadata and unmounts current/history/source/editor projections. A 200 unavailable DTO from current/list and unavailable history propagate to that same boundary. Current/history missing/erased and exact-source missing/unavailable paths propagate safe, distinct reasons. A source failure is not labeled an erased record. In-flight list generations are fenced; detached detail/source/history reads abort and cannot restore the old projection. Explicit refresh/new target read may obtain newly authorized state. Genuine 409 retains the typed form and requires the existing explicit comparison action.
- **M46-R3:** BFF successful response validation receives the endpoint target ID. Current/revision/deactivate/delete IDs, request lookup requestId, operation lookup operationId and correction supersededMemoryId are bound to it. Correction successor must be distinct from its predecessor. Mutation receipt requestId is deliberately not equated to a replay alias: the original stored identity remains valid under the approved alternate-pair contract. Wrong mutation acknowledgements remain `outcome_unknown`; malformed reads/polls fail safely. Missing targeted endpoint IDs are rejected before forwarding.
- **M46-R4:** enum membership requires `typeof value === "string"`; no String(value) coercion remains in the DTO validator. Tests cover container/primitive substitutions, reason, confirmation, status, kind and operation enums alongside unavailable-body suppression.

### R2: narrow named ownership request (not applied)

Requested approval through the user-input channel for **one import and one `MemorySessionProvider` wrapper in `apps/web/src/app/layout.tsx`, inside the existing AuthProvider/WorkspaceProvider composition**. Implementation would live in new feature-owned `components/memory/` / `lib/memory/` files; the layout would contain composition only.

The provider would retain only the unresolved mutation triple in React runtime memory across same-user/workspace Home → Back and Settings unmounts. It would observe authenticated user and explicit workspace navigation, clear on logout/user change/workspace change/revocation, and reject late setters from older scope generations. Home itself would not count as a new workspace. Lists, sources and copied editors would remain view-local; no private body would be written to localStorage/sessionStorage, a module-global cache, server storage or a new DB/durability contract. No workspace context/page/sidebar, chat, Research, auth implementation or backend change is requested.

This boundary is needed because the current Settings subtree is unmounted during ordinary SPA navigation. Extending document-wide click special cases would leave other navigation paths unresolved. Until approval, the existing R2 defect remains present. The exact Home/Back regression is retained as a failing test; it is not skipped or relabeled as a pass. On approval, also extend it to assert the full body/key/request identity on retry, then cover logout and explicit workspace/actor changes with late responses before returning to this same reviewer.

### Executed checks at this partial candidate

Evidence: `evidence/issue46/c1/`.

- `typecheck.txt`: strict whole-web TypeScript exit 0.
- `lint.txt`: all source/E2E/scripts/config ESLint exit 0.
- `unit.txt`: **25 passed**: 21 feature fixture tests plus the reviewer's four original adverse assertions. The review assertions were copied to ignored `.next/memory-c1-tests/original-review-assertions.cjs` with only the require prefix changed from `./reviewer-compiled/` to `./`; assertion bodies and original scratch were unchanged.
- `browser.txt`: **13 passed / 1 failed**. All original eight fixtures pass. Both exact original R1 adverse browser cases pass. Added exact-source 404/410 suppression and late-list/erasure regressions pass. The sole remaining failure is the exact same-workspace Home/Back R2 reproduction.
- All browser checks used real candidate components in headless Chromium with intercepted data. They do not establish authenticated API or visible-browser acceptance. Production build and full existing web-suite limitations from the prior entry remain open; no new build pass is claimed.

Commands use the previous lane commands with unit output at `.next/memory-c1-tests`, evidence at `evidence/issue46/c1/`, and browser output `.next/memory-c1-browser-results`. The full browser invocation from root was:

```powershell
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:3046'
node apps/web/node_modules/@playwright/test/cli.js test --config apps/web/playwright.config.ts e2e/memory-management.spec.ts --workers=1 --reporter=list --output=apps/web/.next/memory-c1-browser-results
```

### Exact candidate identity

- Product/test manifest: `785E16AD7C5A0706CA95C8B771DA4383FB8BB324DED65115E821D3C7E25DAA72` (29 files).
- Manifest file: `evidence/issue46/c1/candidate-manifest.sha256`. Each line is POSIX workspace-relative path, one space, uppercase file SHA-256; sorted by path; LF joined with no trailing LF. Hash above is SHA-256 of those UTF-8 manifest bytes.
- Original review file observed SHA-256: `E07AD5EC282DBE1B8E1DF3C6803F8F29FF80AEAF93765F89F75184B8CA0B96EF`; unchanged by this developer.

The manifest identifies actual bytes and grants no approval. R1/R3/R4 are ready for the original reviewer's targeted recheck; full current-code approval remains blocked on R2 and its ownership decision. Real accepted API integration and the mandatory visible sign-in/workspace → Settings → Memory walkthrough remain open; #46/#41 and later compaction/continuation UI remain open.

Write-back: this lane artifact and bounded evidence are the durable handoff. No private-memory/workbench write is appropriate in this restricted lane. The layout is unchanged pending the named decision.

## C2 revised candidate — approved R2 lifetime boundary implemented

This entry supersedes the C1 pending-ownership disposition above. The user approved the exact layout composition boundary: one import and MemorySessionProvider inside existing AuthProvider/WorkspaceProvider, retaining all original provider ordering. No additional ownership decision is required for this candidate.

### Runtime behavior and changed scope

- Added `components/memory/memory-session-provider.tsx` and `lib/memory/session-context.ts`, `session-state.ts`, `session-state.test.ts`. The layout only composes the feature provider. Auth/workspace providers, workspace page/sidebar, backend, shared chat and Research are unchanged by this rework.
- The feature provider retains the unresolved method/path/body/requestId/Idempotency-Key in React runtime state across ordinary Home → Back and Settings unmount. Re-entry resumes original-request polling; it does not resend automatically. Explicit Retry uses the identical original command. No private-body storage or new durability contract was added.
- Actor/logout and explicit workspace navigation align the feature scope during provider rendering, clear pending state and advance its epoch before consumers render. Revocation clears pending and leaves a denied scope. Epoch-bound setters reject late mutation/poll updates; scope-keyed private views unmount and abort their reads. Home itself retains the same workspace scope. Returning after a workspace switch does not restore the discarded operation.
- Removed the former document-wide tab interception. A beforeunload warning remains for a pending operation; this does not promise recovery after a full document restart.
- R1 target suppression, R3 response binding and legitimate replay/successor semantics, and R4 strict string enums remain in this complete candidate. Ordinary 409 preserves the genuine typed draft. Source missing/unavailable is distinguished from erasure.

### Executed verification

Evidence directory: `evidence/issue46/c2/`.

| Check | Actual result |
|---|---|
| Strict whole-web TypeScript | exit 0, `typecheck.txt`; separate no-emit check includes identifier/import checking |
| Whole source/E2E/scripts/config ESLint | exit 0, `lint.txt` |
| Unit fixtures | 30/30 pass, `unit.txt`: 26 feature tests plus the four unchanged original reviewer assertions |
| Intercepted browser fixtures | 18/18 pass, `browser.txt`; headless Chromium against lane-local Next dev at 127.0.0.1:3046 |
| Production build rerun | failed before compilation with ENOTEMPTY removing `.next/memory-c2-browser-results`, `build.txt`; generated test artifacts were placed under Next's output directory. This invocation is a harness/output-directory collision, not a product build result. Earlier Google Geist font-fetch block remains unresolved. No build pass is claimed. |
| Actual accepted API / visible browser | not exercised; acceptance remains blocked |

Browser suite includes original eight scenarios; both original R1 reproductions; exact Home → Back with full original method/path/body/key comparison and no automatic mutation; source 404/410; delayed list after erasure; explicit workspace switches with held mutation and held accepted poll; logout/login as another actor with held accepted poll; revocation followed by Home/Back with a held poll. It preserves the original 409 draft/explicit-compare test and delayed source/logout test. These are intercepted-data frontend tests and bypass actual authenticated BFF/API integration.

Commands from repository root:

```powershell
node apps/web/node_modules/typescript/bin/tsc --noEmit --incremental false -p apps/web/tsconfig.json
node apps/web/node_modules/typescript/bin/tsc --target es2022 --module commonjs --moduleResolution node --esModuleInterop --skipLibCheck --strict --types node --typeRoots apps/web/node_modules/@types --outDir apps/web/.next/memory-c2-tests apps/web/src/lib/memory/validation.test.ts apps/web/src/lib/memory/proxy.test.ts apps/web/src/lib/memory/client.test.ts apps/web/src/lib/memory/response.test.ts apps/web/src/lib/memory/session-state.test.ts
node --test apps/web/.next/memory-c2-tests/*.test.js apps/web/.next/memory-c2-tests/original-review-assertions.cjs
```

The original reviewer unit assertion copy changes only the require prefix from `./reviewer-compiled/` to `./`; original scratch remains untouched. Build cleanup removed generated `.next` test compilation after the completed unit run; regenerate it before rerunning. Do not use Next's output directory for evidence that must survive a build.

Commands from `apps/web`:

```powershell
node node_modules/eslint/bin/eslint.js src e2e scripts next.config.ts playwright.config.ts eslint.config.mjs postcss.config.mjs
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:3046'
node node_modules/@playwright/test/cli.js test e2e/memory-management.spec.ts --workers=1 --reporter=list --output=.next/memory-c2-browser-results
node node_modules/next/dist/bin/next build
```

### Candidate and original-reviewer handoff

- Fixed source base remains `9cd93ec1aa70ea803401a88c55834de1593f0aeb`, branch `work/issue46-memory-management-ui`; no Git commands, writes, commits, PRs or model calls during rework.
- Complete 34-file product/test manifest: `evidence/issue46/c2/candidate-manifest.sha256`.
- Manifest SHA-256: **F3097CAE91BCFA8A3B3EAC623AB9E90F6EE52840E0117787CB0ABA717C59EDC2**. Sorted workspace-relative POSIX path + space + uppercase file SHA256; UTF-8 LF joined without trailing LF. Includes layout and all new session files.
- Original review artifact SHA-256 remains **E07AD5EC282DBE1B8E1DF3C6803F8F29FF80AEAF93765F89F75184B8CA0B96EF**; reviewer file and `.memory-tests/` were not edited.
- Governing API consumer contract SHA-256 remains **2EBF5D6BD9A9C298D21253C50A9ECAA869AD9AC2A437BFEDF354BF0A961F2802**.

Complete revised candidate is ready for the original reviewer's recheck of R1–R4, including approved layout composition and race tests. Collaboration inventory exposes only this root; direct delivery to the original reviewer is unavailable. Controller must relay this manifest, the lane ledger and C2 evidence to the same reviewer. No replacement reviewer was spawned and no independent approval is claimed.

`memoryAdmissionEnabled=false` remains unchanged. Accepted API integration, exact integration commit evidence, production build and the real visible normal workspace → Settings → Memory workflow with actual API screenshots/state/requests remain gates. Full existing web-suite regression acceptance is not claimed. #46/#41 remain open; later compaction status and continuation/recovery UI remain outside this slice.

Write-back check: this lane ledger and bounded evidence contain the durable verified result. No private MEMORY, profile/workbench writes or old-worktree changes were made.

## C3 revised candidate — unavailable lifecycle management

Original C2 review closes R1–R4 at its bounded static/fixture scope and requests R5. This candidate restores permitted management of owned content-unavailable records while retaining semantic suppression. Original reviewer approval of this C3 candidate is pending.

### Changed product/test files

- `apps/web/src/lib/memory/body-free.ts` (new): explicit field-only projection retains id/version/intent/validity/displayStatus and unavailable reason; excludes body, conditions, source references/hashes and other semantic fields.
- `apps/web/src/lib/memory/body-free.test.ts` (new): metadata preservation, semantic-field exclusion and per-revision intent/version/reason tests.
- `apps/web/src/lib/memory/use-memory-management.ts`: replace matching cached rows with body-free current metadata; preserve filter semantics; retain suppression across refresh/reselection; keep late-list and terminal denial fencing.
- `apps/web/src/components/memory/memory-panel.tsx`: valid body-free records continue through the feature detail; erased/not-found terminal outcomes retain their separate unavailable display.
- `apps/web/src/components/memory/memory-detail.tsx`: permit Delete for a nondeleted authorized current record and Deactivate for active intent; retain History and opaque paging. Source/history-only suppression removes copied editor, current body, sources and semantic history immediately, then obtains fresh current metadata before lifecycle actions. Historical version never becomes mutation CAS version. A readable fresh response during this suppression lifetime is projected body-free, without restoring its semantic bytes. True erased410 unmounts management controls.
- `apps/web/e2e/memory-management.spec.ts`: retains original18 cases, includes both original R5 adverse assertions, plus pending-control lock, inactive mixed-history paging/current CAS, source-failure fresh-metadata/erased/scope races and historical-unavailable/current-version separation.

Only these six feature/test files changed relative to C2 (four modified, two new). No layout, shared container, auth, permissions, backend, BFF, DTO contract, activation or i18n changes in R5. No further ownership decision is needed. `memoryAdmissionEnabled=false` remains unchanged: unavailable lifecycle management does not enable create/correct. Correct/source controls remain absent for unavailable records; the existing readable correction form still has its disabled admission-gated Save.

### Independently executed evidence

Evidence directory: `evidence/issue46/c3/`. Browser tests use intercepted synthetic responses against lane-local Next16 at `127.0.0.1:3146`; they do not establish authenticated real-API or visible-browser acceptance.

| Check | Actual result / log |
|---|---|
| Unchanged original R5 tests, before rework | 2/2 fail at missing Delete, `original-r5-before.txt` |
| Unchanged original R5 tests, after rework | 2/2 pass, `original-r5-after.txt`; active/inactive Delete expectedVersion2 |
| Unchanged original R1/R2 browser tests | 3/3 pass, `original-r1-r2.txt` |
| Complete owned browser suite | 26/26 pass, `browser.txt` (39.6s); includes all prior privacy/conflict/pending/race tests |
| Dedicated units plus original reviewer assertions | 32/32 pass, `unit.txt` (28 feature + original4) |
| Whole-web strict TypeScript | exit0, `typecheck.txt`; standalone no-emit check |
| Whole source/E2E/scripts/config ESLint | exit0, `lint.txt` |
| Production build | exit1, `build.txt`; reaches production compilation but cannot fetch existing Google Geist/Geist Mono fonts. No font replacement or build pass claimed. |
| Reviewer scratch preservation | zero hash mismatches, `preservation.txt`; `reviewer-scratch-before.sha256` records original scratch inventory |

All new runtime artifacts are under ignored `apps/web/test-results/memory-c3-*` or `.local-validation/memory-c3-unit`, outside reviewer scratch and Next output. Lane-owned dev server was stopped before the build. Original reviewer file and scratch were preserved.

Reproduction commands from repository root:

```powershell
node apps/web/node_modules/typescript/bin/tsc --noEmit --incremental false -p apps/web/tsconfig.json
node apps/web/node_modules/typescript/bin/tsc --target es2022 --module commonjs --moduleResolution node --esModuleInterop --skipLibCheck --strict --types node --typeRoots apps/web/node_modules/@types --outDir .local-validation/memory-c3-unit apps/web/src/lib/memory/validation.test.ts apps/web/src/lib/memory/proxy.test.ts apps/web/src/lib/memory/client.test.ts apps/web/src/lib/memory/response.test.ts apps/web/src/lib/memory/session-state.test.ts apps/web/src/lib/memory/body-free.test.ts
node --test .local-validation/memory-c3-unit/*.test.js .local-validation/memory-c3-unit/original-review-assertions.cjs
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:3146'
node apps/web/node_modules/@playwright/test/cli.js test --config apps/web/playwright.config.ts e2e/memory-management.spec.ts --workers=1 --reporter=list --output=apps/web/test-results/memory-c3-independent
node apps/web/node_modules/@playwright/test/cli.js test --config apps/web/.memory-tests/reviewer-c2-extra.config.ts --output=apps/web/test-results/memory-c3-original-r5
node apps/web/node_modules/@playwright/test/cli.js test --config apps/web/.memory-tests/reviewer-playwright.config.ts --output=apps/web/test-results/memory-c3-original-r1-r2
```

The copied unit reviewer assertions change only `./reviewer-compiled/` requires to `./`, with assertions unchanged. From `apps/web`, full lint is `node node_modules/eslint/bin/eslint.js src e2e scripts next.config.ts playwright.config.ts eslint.config.mjs postcss.config.mjs`; production build is `node node_modules/next/dist/bin/next build`.

### Exact candidate / original-reviewer relay

- Complete36-file manifest: `evidence/issue46/c3/candidate-manifest.sha256`.
- SHA256: **F22DBC12D98C4CC1D6022B1A5428D898019D1BCD9921AAE31590F607575C8CE8**. Same sorted POSIX path + space + uppercase SHA256, UTF-8 LF/no-trailing-LF convention as C2.
- Unchanged original review SHA256: **92ABDA8449469E3DDAF9009063C29D6145282F185217B04BFE17D77455E16581**.
- Governing contract remains **2EBF5D6BD9A9C298D21253C50A9ECAA869AD9AC2A437BFEDF354BF0A961F2802**.
- Base/branch remain the recorded `9cd93ec1aa70ea803401a88c55834de1593f0aeb` / `work/issue46-memory-management-ui`; no Git commands or writes during rework. No product inference/model endpoints or external model tools were invoked. A bounded implementation subagent was used under the mandatory profile implementation-delegation rule; this was not a replacement independent reviewer.

Controller must relay this complete candidate and evidence to the same original reviewer; that reviewer is not exposed in this collaboration tree. No C3 independent approval is claimed. Accepted API integration, exact integration commit evidence and real visible normal workspace → Settings → Memory workflow with actual API screenshots/state/requests remain pending; full web-suite acceptance and successful production build are not claimed. #46/#41 remain open; later compaction/continuation/recovery UI remains outside this slice.

Write-back check: durable verified changes, limits and relay state are recorded here. No private MEMORY/profile/workbench writes, backend ownership expansion or old-worktree changes.

## C4 activation and isolated-runtime checkpoint — real integration blocked

Controller integrated accepted PR50 at exact **6ccd8d8a1de7afeb2c8edb0f3f07d0b9cf0a38e8** by safe fast-forward with frontend changes retained. The current branch ref file was read and matches that SHA. User explicitly authorizes activation after original API/controller real PostgreSQL/HTTP acceptance and hosted six-core CI. Those upstream review/CI results are controller-reported acceptance; this lane does not relabel them as its own execution. Original C3 reviewer PASS closes R1–R5 at code/static/fixture scope.

### Activation changes and checks

- `lib/memory/activation.ts`: enabled true; exact accepted integration SHA recorded in comment.
- `lib/memory/proxy.test.ts`: strict create/correct forwarding, identity/body/receipt checks replace closed-gate assertion.
- `e2e/memory-management.spec.ts`: enabled create for both roles and correction409→refresh/explicit comparison→successor fixture; prior privacy/pending/unavailable lifecycle tests retained.
- New `e2e/memory-management-live.spec.ts`: no intercepted responses; gated by `MEMORY_LIVE=1`, loads synthetic credentials from ignored local file. Auth trace/video/automatic screenshots disabled; explicit post-auth screenshots only. Auth/workspace/lifecycle/source/history/concurrent409/isolation paths are authored but **not executed**. Live UI unknown Home/Back and revocation-race scenarios remain to be added.

Main verification: **33/33 unit/helper tests**, whole-web strict TypeScript and full source/E2E/scripts/config ESLint pass. Logs: `evidence/issue46/c4/{unit,typecheck,lint}.txt`. Activation worker's intercepted browser suite **27/27 pass**,39.4s, before the browser denial; scratch `apps/web/test-results/memory-c4-fixture`. This fixture count is not actual API evidence.

### Actual runtime setup and precise blocker

Full setup/network observations are in `evidence/issue46/c4/runtime-status.txt`.

- New isolated PostgreSQL17.11: loopback **56846**, database `citeframe_memory46_ui`, data `.local-runtime/issue46-management-ui/pgdata`. Full Alembic migration completed through `t4b5c6d7e8f9`. Existing clusters/data untouched.
- Actual API: **http://127.0.0.1:5846**, full `ai_pdf_api.main:app`, lane imports with bytecode disabled; existing Python environment used read-only. No dependency/auth overrides or model calls.
- Actual HTTP setup registered three synthetic accounts and created workspace `Memory46 isolated runtime`; two member memberships were inserted into this isolated database. Account passwords and server tokens are generated locally and stored only in ignored runtime files. No memory lifecycle request through Next was completed in this lane.
- Next16: **http://127.0.0.1:3246**, points at planned transport proxy **5847 → actual API5846**. API and Next were launched hidden; PG direct hidden process was used after pg_ctl's restricted-token startup failed.
- Visible browser open of localhost3246 was **explicitly denied by the browser security policy/user permission**. No alternative browser/CDP/Playwright live execution followed that denial.
- The subsequent hidden proxy launch + raw HTTP readiness command was **rejected by exec policy**. Proxy5847 remains unstarted. No alternate tool/syntax was used to execute the rejected operation.

**The signed-cookie → Next memory BFF → API → PostgreSQL chain is therefore not yet verified, and Next is not presently ready for signed-in use because its configured5847 upstream is down.** No actual-memory transcript, visible screenshot or external-controller UI acceptance is claimed. Real409 draft handling, unknown outcome UI recovery, member isolation/revocation and normal lifecycle acceptance remain pending despite the fixture passes.

### Controller handoff: local access and continuation

Runtime directory, relative to this worktree: `.local-runtime/issue46-management-ui/`.

- `access.json`: locally generated owner/member/other synthetic accounts and workspace identity. Controller reads this file locally and uses owner or member credentials in the normal sign-in form; do not paste its values into Git, reports or screenshots. All three accounts belong to the same isolated workspace; owner has no authority over another member's private records.
- `environment.json`: server-only local environment. Do not publish or display its values.
- `api.pid`, `web.pid`, `postgres.pid`: recorded process wrappers; observed running PIDs62496,10296,54900 respectively. API child startup logged57624. `process-identities.json` records executable/start-time identity for safe shutdown.
- Planned ordinary browser URL: **http://127.0.0.1:3246/**. After proxy launch, sign in → `Memory46 isolated runtime` → Settings → Memory. Workspace ID is `6c370beb-6038-478c-be9c-28219fc7831f`. No direct hidden-mode or private-chat entry exists.
- Hidden proxy startup command for the controller **after runtime execution is authorized**:

```powershell
& ./.local-runtime/issue46-management-ui/start-proxy.ps1
```

- The proxy is a test transport only, exact loopback passthrough. Optional `fault.json` causes it to consume a real successful upstream mutation response and close the downstream connection; it never fabricates API success. Fault controls default disarmed. Its operation and the HTTP smoke remain unexecuted.
- HTTP-only smoke command after authorization and proxy readiness:

```powershell
$env:MEMORY_RUNTIME_PYTHON='D:/Code/citeframe/apps/api/.venv/Scripts/python.exe'
node .local-runtime/issue46-management-ui/live-bff.mjs
```

This would produce sanitized method/path/status/protocol assertions at `evidence/issue46/live/bff-http.json`. It would not prove UI drafts/navigation or external visible acceptance. It expects an empty active owner state; a partial failed run requires deliberate disposable-state handling before rerun.

- Visible/browser test command must wait for renewed browser access authorization; do not use it to bypass the denied UI action:

```powershell
$env:MEMORY_LIVE='1'
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:3246'
node apps/web/node_modules/@playwright/test/cli.js test --config apps/web/playwright.config.ts e2e/memory-management-live.spec.ts --workers=1 --output=apps/web/test-results/memory-live
```

- Safe shutdown helper (authored, unexecuted), validates recorded process identity and targets only this lane plus exact PG data path:

```powershell
& ./.local-runtime/issue46-management-ui/stop-runtime.ps1 -PgCtl D:/Code/citeframe/.local-runtime/postgresql/pgsql/bin/pg_ctl.exe
```

Runtime helpers are ignored local artifacts; they are not production backend/BFF changes. Logs remain local. No paid models, new audiences/modes, shared-output injection, old-tree writes, commits or pushes occurred.

### Checkpoint identity and remaining gates

This is an **activation checkpoint, not the requested final real-integration freeze**. Complete37-file product/test checkpoint manifest is `evidence/issue46/c4/checkpoint-manifest.sha256`, SHA256 **78280352E9AF9FD58D594DA2F31E69C2C2BD9C573F5DA5243CC96BC0174493BB**. Same sorted UTF-8 path/hash LF/no-trailing-LF convention. Current integrated contract artifact hash is **AF82373EB17AE00C5EC24D0BBEB9E19ED40297205263A699DC5BE4D96804AAC7** (includes later API lane records); original operative approved contract hash remains historical provenance. Original UI review artifact currently hashes **30E4570523B0007CE4136974FB70DDABA9A14522E969F0D9CEAF6483DAC49998** and was not edited.

Build was not rerun while preserving the live Next process. Existing C3 production build remains blocked on Google Geist/Geist Mono fetching; no typography change or build pass. Original reviewer recheck, real BFF lifecycle/network evidence, visible browser/controller acceptance, live unknown-navigation/revocation cases and final integration manifest remain pending. #46/#41 and later compaction/continuation UI remain open.

Write-back check: this ledger and C4 evidence record verified state and precise limits. No private-memory/shared-workbench write is appropriate. Controller must authorize/resume blocked runtime/browser execution before this lane can deliver final actual-API acceptance evidence.

## C4 offline continuation — live tests authored; runtime shutdown denied

Only `apps/web/e2e/memory-management-live.spec.ts` changed relative to the C4 product/test checkpoint. Production bytes and the existing reviewed checkpoint manifest remain unchanged. New test SHA256: **5C09271BF3704224CBD3F211B90677D69616CC4C2B7B815A0555CD38BF82F01D**; recorded separately in `evidence/issue46/c4-offline/tests.sha256`. C4 manifest remains **78280352E9AF9FD58D594DA2F31E69C2C2BD9C573F5DA5243CC96BC0174493BB** and describes its historical test bytes; it was not regenerated.

Added offline test oracles:

- Real upstream committed mutation with lost acknowledgement, ordinary Home → actual browser Back (`page.goBack`) → Settings → Memory, no automatic resend, explicit retry preserving exact method/path/serialized body/requestId/key, accepted operation reconciliation and no second version advance.
- Actual member revocation while a genuine accepted Next BFF/API poll response is held in test RAM. `route.fetch()` must return actual200 with the original request identity before revocation. Release uses the unchanged APIResponse; no invented DTO/status. The test records whether the route accepted release or the request was canceled, without claiming browser delivery. Private body, unsent draft and pending identity must stay cleared, including Home/Back. Actual membership restore, held-response release and transport fault disarm are cleanup obligations. Python helper uses -B/no-bytecode.

**Static only:** main independently reran whole-web strict TypeScript and focused live-spec ESLint, both exit0. Logs: `evidence/issue46/c4-offline/{typecheck,lint}.txt`. No browser/network/helper/live execution, proxy launch, font change, Git write or release conclusion. These authored oracles are unexecuted and add no runtime acceptance evidence.

### Original refusals and attribution correction

`evidence/issue46/c4-offline/tool-errors-and-stop.md` preserves the original browser tool name/action/full return and execution tool name/short raw excerpts. Browser tool was `mcp__cua_repl.js`; original message begins `Browser Use rejected this action due to browser security policy. Reason: The user declined permission for this action.` The mention of a user is the tool's wording, not this lane's independent identification of the rejecting actor. Execution tool was `functions.exec` invoking `tools.exec_command`; original short excerpts are `exec_command failed: CreateProcess` and `rejected: blocked by policy`. Prior shorthand attribution in C4 must be read with this qualification. Neither rejected action was retried or reached through another tool/syntax.

### Authorized shutdown attempt and current state

Read-only checks matched web10296/API62496/PG54900 PID, executable path and exact UTC start time against recorded identities. PowerShell's default JSON date conversion caused false mismatches; supplying the existing `ConvertFrom-Json:DateKind=String` default preserved original timestamps, with no identity edit or weaker check.

The existing stop script was then invoked once. Its first web process-tree termination returned **`ERROR: Access denied`**, followed by **`Process-tree shutdown failed for web; inspect lane status`**, exit1 at stop-runtime.ps1:29. API and PG shutdown stages were not reached. No alternative termination/privilege escalation was attempted. Follow-up read-only process inspection found all three recorded processes still running; PG data and postmaster.pid remain. Controller-side permitted shutdown is still required. The exact attempted command and raw errors are in the tool-errors artifact; data was not deleted.

Original reviewer can inspect this test-only delta with its separate hash. UI acceptance, actual memory BFF integration and final runtime freeze remain pending; no publishing/readiness conclusion is made. Durable write-back is confined to this lane ledger/evidence, with no private memory or shared-workbench write.

## C5 static live-spec candidate — exact correction/history semantics; resave oracle unresolved

Only `apps/web/e2e/memory-management-live.spec.ts` changed. Original C4 review was read, including the pure-unit39-pass bounded disposition and its live evidence limitations. No production/helper/reviewer/old-manifest edits, runtime/network/browser/helper/shutdown executions, font changes or Git writes occurred in this slice.

Authored live assertions now use concurrent actual correction POST201 producing a distinct successor and superseding the predecessor. The stale UI correction POST at the old CAS must return409 version_conflict; its genuine draft must remain intact through explicit refresh. The refreshed predecessor is superseded, with disabled Save and no active-version adoption control. The prior stale Deactivate PATCH409 substitution was removed from this conflict scenario. The intercepted fixture remains separate mechanics evidence and is not presented as an actual concurrent-correction model.

Predecessor fidelity checks assert versions1 active and2 superseded, unchanged original body/conditions/exact sourceRefs, and original tuple/content/authenticated owner provenance from the historical-source UI action. Deleting this predecessor must clear displayed body/history/source and make owner current/history return410 erased and the exact source return410 source_version_unavailable. The independent live Home→actual browser Back original-triple recovery and held-real-upstream revocation test definitions remain.

### Remaining requested recovery definition

**The requested successful resave after terminal-predecessor correction conflict is not yet authored.** Static core/UI inspection shows concurrent correction creates a NEW successor and terminal superseded predecessor; the present UI's explicit Use current version button requires the selected record to remain active. No real supported mutation supplies the fake same-ID active version2 with changed wording used by the earlier mechanics fixture. Test-only work cannot create a missing successor-retarget UI path.

A targeted user question is pending: explicitly compare predecessor/successor and manually transfer the retained draft to a deliberately selected successor for another correction, or retain direct compare/resave as an unmet expected path requiring separate product authorization. Neither manual transfer acceptance nor an existing direct resave capability was assumed. This is a static evidence/definition limitation, not an invented executed UI failure. The full requested recovery-test completion remains open.

### Frozen static bytes and checks

- All37 current product/test paths are recorded in new `evidence/issue46/c5-static/candidate-manifest.sha256`; SHA256 **FC9D6CF10AA26DA589AC2428E41BEF00F6A66ED2CB2A0485954A9474D3E89C7F**. Sorted UTF-8 POSIX path + space + uppercase SHA256, LF joined without trailing LF.
- Live test SHA256 **E5AD96616DD1FEE2C13D0F87A9AEF1F1577A1BAD39D19F075B68E614B12B3C7C**, separately in `c5-static/tests.sha256`.
- C4 historical manifest remains unchanged at **78280352E9AF9FD58D594DA2F31E69C2C2BD9C573F5DA5243CC96BC0174493BB**.
- Main independently ran whole-web `tsc --noEmit --incremental false -p apps/web/tsconfig.json` and focused `eslint e2e/memory-management-live.spec.ts`, both exit0. Logs are `c5-static/typecheck.txt` and `lint.txt`.
- Production bytes remain identical to C4; base remains6ccd8d8a1de7afeb2c8edb0f3f07d0b9cf0a38e8. No test runner/live invocation was used for this static handoff.

This manifest freezes the current static candidate for original-reviewer/controller inspection, including the explicitly incomplete resave coverage; it does not assert complete live-test coverage, actual UI integration, release readiness or permission to run denied operations. Prior browser/exec/shutdown denial reports remain controlling and were not retried. #46/#41 remain open. Durable write-back is this owned ledger/evidence only; no private memory/shared-workbench write.

## Successor recovery contract R1 — original review pending

The controller resolved the C5 recovery choice: preserve the complete original draft and predecessor identity, explicitly compare/adopt a proven readable active successor, and require a separate Save. The prior pending-question entry is superseded; manual retyping is not the recovery path.

Proposal: `issue46-successor-recovery.md`, SHA256 **7B3E17EBB977CEFF298EAD762C8BCF49111E989075D404CE47603F81D55E8BFA**. It defines feature-local state/ownership, explicit paged candidate selection, bounded backward supersedesId proof (8 edges), adoption rereads, recurrent conflicts, privacy clearing and unchanged unknown-command identity semantics. No affected product implementation is authorized before the original independent reviewer approves these exact contract bytes.

This slice changes only the proposal and this owned ledger. The C5 37-file candidate is unchanged; historical manifests/reviewer artifacts are preserved. No tests, browser/network, runtime helper or shutdown operations were executed for this documentation handoff. No Git/model calls or private-memory writes. Original reviewer is outside the exposed collaboration inventory; controller relay is required, and direct reviewer delivery/approval is not claimed. Implementation waits at that review gate. Real visible UI acceptance, #46/#41 and later compaction status UI remain open.
## Successor recovery implementation authorized — 2026-09-29

Original reviewer approved exact contract **7B3E17EBB977CEFF298EAD762C8BCF49111E989075D404CE47603F81D55E8BFA**; controller authorized implementation within §5. M46-SR1 is closed: candidate validation permits at most9 actual GETs/9 distinct records/8 edges; explicit adoption permits at most10 actual GETs, with only the final fresh candidate read repeated. Contract bytes remain unchanged; its historical PROPOSED header is superseded by the original review approval and this entry.

Implementation and dedicated test definitions are assigned to the existing product/test owners. Runtime/network/browser/fixture-browser/shutdown execution remains prohibited; only standalone TS, lint and pure units may run. New recovery behavior needs its own candidate evidence and independent implementation review. Prior C3/C4 approval is not extended to it. No layout/provider/BFF/backend/API or private-memory/shared-workbench ownership expansion.
## C6 successor recovery implementation — frozen static candidate, 2026-09-29

Implemented the exact approved successor recovery contract within feature ownership. Four new files: `lib/memory/correction-recovery.ts`, its pure test, `use-correction-recovery.ts`, and `components/memory/memory-recovery.tsx`. Narrow updates: panel/detail/form, correlated results and target invalidation in `use-memory-management.ts`, minimal i18n, and both dedicated E2E definitions. No layout/provider/Workspace/auth/BFF/backend/API changes; existing unknown-command identity protocol remains unchanged.

Recovery retains the complete Statement and original predecessor, explicitly selects/proves/compares an authorized successor, then adopts only its fresh ID/CAS before separate Save. Selection is bounded to9 actual GETs/9 records/8 edges; adoption to10 actual GETs including final fresh candidate read. No automatic mutation/identity/pagination/latest inference. Original/candidate history/source reuse checked projections. Recurrent conflicts repeat explicit bounded recovery to original P. List/current/history/source participant denial aborts and clears protected recovery; definitive correction target denial also suppresses the target. Privacy clearing after candidate selection clears the selected comparison to prevent an extra automatic GET; body-free records remain explicitly selectable for permitted lifecycle/history. Final-read relationship changes invalidate proof and require re-selection rather than displaying an unproven chain.

Frozen41-file manifest: `evidence/issue46/c6-successor/candidate-manifest.sha256`, SHA256 **60E1DFC70C24E47538C59424E2210F80B7E3B7A156C8957CDF06ED28839D06AC**. All9 test source hashes: `c6-successor/tests.sha256`, SHA256 **F0E353842678423A342D84EFFDE802CB9575889737B897BC017F70914CCC7367**. Eleven files differ from C5 (9 product/pure-test files plus2 E2Es); C4/C5 manifests and exact approved contract remain unchanged. Base/branch unchanged, no commit/push.

Developer-lane root verification: this development lane's `/root` executed whole-web strictTS and focused feature/i18n/E2E lint, both exit0; strict pure-unit compilation exit0 and Node40/40 tests pass (29 retained +11 recovery tests). Initial tsx runner failed before tests with uv_os_get_passwd ENOMEM; raw error retained separately. Successful pure execution used standalone tsc + Node, with no browser or real network. These C6 logs are developer-lane verification; no external-controller or designated independent reviewer execution is attributed to them. Exact commands/results and limits: `c6-successor/README.md`, `typecheck.txt`, `lint.txt`, `unit-compile.txt`, `units.txt`, `units-tsx-startup-error.txt`.

Browser definitions now cover genuine distinct-successor POST409 comparison/adoption/resave, complete optional-field preservation, exact predecessor history/source/delete denial, existing unknown HomeBack and revocation, plus bounded/privacy adversaries. They were not executed. Hook lifecycle/visible controls remain static/authored evidence; no new real API/BFF/UI/build acceptance or publishing conclusion. All denied runtime/browser/network/shutdown actions remained untouched. Original independent implementation review awaits controller relay; reviewer is not exposed in this collaboration tree. #46/#41 and later compaction/continuation UI remain open. Write-back is confined to this owned ledger/evidence; no private-memory/shared-workbench writes.