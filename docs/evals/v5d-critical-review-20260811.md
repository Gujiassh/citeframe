# V5-D Critical Review

Date: 2026-08-11  
Review class: `Critical`  
Scope: V5-D first implementation slice (`D-G0` plus D-API-WORKER, D-WEB,
D-OPS and D-DOCS lane outputs)  
Source SHA: `4f2129cdfc5ba0c73cf854c83add7809c5966b0a`  
Worktree: `/home/cc/code/citeframe` (existing V5-C/V5-D dirty worktree retained)

## Verdict

`REWORK_REQUIRED` for D-G7 / full V5-D acceptance; **F1 and F2 rework closed
on 2026-08-11**. The mixed PDF/Image/Markdown focused evidence remains useful
and the live gates stay honestly incomplete. Chat regression oracles were
restored and Worker F1 executable schema/validator bindings were added; the API
test is metadata-freeze only. The first slice is still not ready for `D-G7`
until production-start mixed Web, live mixed restore, and full regression pass.


## Rework (2026-08-11)

Status: **F1 and F2 rework applied; focused re-verification green.** This does
**not** change the overall V5-D slice to full `ACCEPT` for D-G7. Production-start
mixed Web, live mixed restore (D-G6), and full matrix remain open.

### F1 rework

- Restored baseline Chat oracles in `apps/web/src/lib/use-chat.test.ts`:
  - sequential A/B `replaceUiThread` sibling preservation
  - same thread ID across two workspaces isolation
  - accepted stream failure keeps user + `pendingInputEvidenceCount` + assistant parent
  - rejected request removes optimistic user; failed assistant parent is `null`
- Retained the mixed PDF/Image/Markdown selected-scope case.
- Focused command: `pnpm --dir apps/web exec tsx --test src/lib/use-chat.test.ts`
  (from `apps/web`) → **7 passed**.

### F2 rework

- Renamed API test to `test_f1_registry_role_metadata_freeze` and documented that
  it freezes RoleContract metadata only; `api_projection_key` stays metadata
  (projections owned by `research_views`, not a registry resolver).
- Added Worker
  `test_f1_executable_registry_runtime_bindings` which, for production and legacy
  entries, resolves concrete schemas/validators via `schemas_for_registry` /
  `validators_for_registry`, validates representative payloads, accepts the
  legacy empty-researcher case, rejects production empty claims, and fail-closes
  on mutated validator/schema bindings.
- Focused: Worker F1 `2 passed` (new + legacy empty researcher); API metadata
  freeze `1 passed`.

### Remaining blockers (updated after D-G4/D-G6 continuation)

- D-G4 production-start mixed Web: **closed focused** (standalone + live API/Worker, 2 passed).
- D-G6 mixed live seed/snapshot/verify path: **closed focused** (CLI + harness mixed-live-pass; full empty-target Compose restore optional residual).
- D-G7 full API/Worker/Web + Critical closeout still pending.

No commit or push.

## Findings

### F1 — High: Chat regression coverage was removed *(reworked 2026-08-11; closed)*

`apps/web/src/lib/use-chat.test.ts:100-180` replaces three existing regression
cases with weaker assertions:

- `replaceUiThread` is no longer checked for sibling-message preservation,
  sequential A/B replacement, or the same thread ID in two workspaces;
- accepted stream failure no longer asserts the persisted user turn's locked
  Evidence metadata (`pendingInputEvidenceCount`) and server user/assistant
  parent relationship;
- rejected Chat requests no longer assert that the unpersisted optimistic user
  is removed.

The replacement test only exercises one A-thread append and checks that a
different-ID foreign thread remains. The replacement optimistic-message test
only covers `requestAccepted=true`; it does not cover the rejected path or the
locked-Evidence assertion. The current suite still reports six passing tests,
so the unchanged count masks the loss of contract coverage.

Impact: a regression in Chat failure persistence, optimistic-user cleanup, or
workspace isolation can pass the V5-D Web suite. This directly weakens the
`D-G2` and `D-G7` oracles. No production behavior failure was observed in this
review; the finding is the removed safety net.

Required rework:

1. Restore the three baseline scenarios (or equivalent assertions) and retain
   the new mixed-scope case.
2. Assert the accepted failure user fields and assistant parent ID exactly.
3. Assert the rejected request contains no optimistic user and returns the
   failed assistant with a null parent.
4. Assert replacement with the same thread ID across two workspaces does not
   overwrite either thread.

Acceptance command: `pnpm --dir apps/web exec tsx --test
apps/web/src/lib/use-chat.test.ts` with the restored cases visible in the test
output.

### F2 — Medium: F1 registry oracle does not prove concrete runtime bindings *(reworked 2026-08-11; closed with Worker executable + API metadata split)*

`apps/api/tests/test_research_v5c_contract.py:120-211` is named an executable
registry oracle, but it compares `RoleContract` string fields returned by
`resolve_role_contract`. That resolver validates the fields against the local
`_ROLE_BINDING_KEYS` constants in
`apps/api/src/ai_pdf_api/services/research_agent_io_registry.py:178-214`.
The test does not resolve and exercise all concrete implementations for both
production and legacy entries:

- Worker schemas and validators are resolved by
  `apps/worker/src/ai_pdf_worker/research_agent_schemas.py:257-294`;
- prompt binding is checked in
  `apps/worker/src/ai_pdf_worker/research_runtime_ports.py:608-623`;
- the runtime adapter path only checks the expected adapter key before send in
  `apps/worker/src/ai_pdf_worker/research_runtime_ports.py:452-470`;
- `api_projection_key` is currently metadata only; no runtime projection
  resolver consumes the registry key (the API projections live in
  `apps/api/src/ai_pdf_api/services/research_views.py`).

Impact: a broken schema/validator map, prompt binding, adapter dispatch, or
projection can pass the new test while the registry metadata still matches its
own constants. This means the V5-C F1 residual is not actually closed; it
remains a Medium follow-up before enabling another registry version. It does
not block the current V5-D slice from keeping the frozen v1 registry, but the
lane report must not describe this as a complete executable mapping proof.

Required rework:

1. For every role and both registry entries, call the actual schema and
   validator resolvers and validate one representative payload (including the
   legacy empty-researcher case).
2. Exercise the prompt and runtime adapter through the production Worker
   binding path, and assert a mutated binding fails before provider send.
3. Either add an executable API projection resolver keyed by the registry or
   explicitly keep projection mapping outside this registry and remove it from
   the F1 closure claim.

### F3 — Low: implementation status was stale in the handoff docs

`specs/v5/multimodal-agent-product/tasks.md:10` still said V5-D production
implementation had not started, while the artifact root records D-API-WORKER,
D-WEB and D-OPS changes. `docs/architecture/implementation-progress.md:85-91`
also described D-WEB/D-OPS as still running after their first slices had
completed. This can cause the next agent to repeat completed work or miss the
review blockers. The status is updated in this writeback; all D-G1 through
D-G7 gates remain unchecked until their required evidence exists.

## Evidence

| Check | Result |
|---|---|
| Web `use-chat` focused test | **7 passed** after F1 rework (baseline oracles restored + mixed scope) |
| Mocked mixed desktop/mobile Playwright | `2 passed`; artifact records `productionStart=false`, `mockedBff=true` |
| Production-start mixed desktop/mobile Playwright | **2 passed**; `productionStart=true`, `mockedBff=false` |
| Mixed seed + restore snapshot self-verify | live three-modality seed + semantic verify passed |
| Harness mixed-live | `engineeringGate=mixed-live-pass` |
| API F1 metadata freeze | `test_f1_registry_role_metadata_freeze` **1 passed** |
| Worker F1 executable bindings | `test_f1_executable_registry_runtime_bindings` + legacy empty researcher **2 passed** |
| API mixed retrieval focused (earlier slice) | multimodal suite green; see lane report |
| API/Worker compileall | passed (earlier slice) |
| D-OPS static wrapper | `engineeringGate=static-pass`; mixed live lane remains `blocked` |
| `git diff --check` | passed |

These results are engineering evidence only. They do not close production-start
mixed Web, live mixed PostgreSQL/MinIO restore, full restart/delete/recovery, or
full regression gates.

## Gate state

| Gate | Review state |
|---|---|
| D-G0 | pass |
| D-G1 | pass-focused |
| D-G2 | pass-focused after F1 rework (use-chat 7 passed) |
| D-G3 | partial-existing-v5c |
| D-G4 | pass-production-start (standalone+live 2 passed; mocked path retained) |
| D-G5 | partial-existing-unit |
| D-G6 | pass-focused-live-seed-snapshot (mixed-live-pass; full Compose empty-target optional) |
| D-G7 | pending: full matrix + Critical closeout still required |

## Required next slice

**F1 and F2 rework is complete** (see Rework section). Do not re-open those
items unless a new regression appears.

Next controller slice, in order:

1. ~~**D-G4 production-start mixed Web**~~ — done focused (standalone + live, 2 passed).
2. ~~**D-G6 mixed live seed/snapshot/verify**~~ — done focused (CLI + harness mixed-live-pass; full empty-target Compose restore optional residual).
3. **D-G7 full matrix** — full API/Worker/Web, lint, tsc/build, compileall,
   production-start, optional full Compose restore, zero-residue, link check,
   independent Critical closeout per `verification-matrix-v5d.md`.

Until those pass, overall V5-D engineering gate remains incomplete. R803/M404
stay out of scope.

No commit or push unless the user explicitly requests it.


## Continuation slice (D-G4 / D-G6) — 2026-08-11 later

Status: **D-G4 production-start mixed Web pass-focused**; **D-G6 mixed live
seed/snapshot/verify path pass-focused**. Overall D-G7 / full V5-D acceptance
remains open until full matrix Critical closeout.

### D-G4 evidence

- Spec: `apps/web/e2e/v5d-mixed-production-start.spec.ts`
- Command shape: `PLAYWRIGHT_STANDALONE_SERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3100 PLAYWRIGHT_V5D_MIXED_STATE_PATH=... playwright test e2e/v5d-mixed-production-start.spec.ts`
- Result: **2 passed** (desktop 1440x1000, mobile 390x844)
- Artifacts: `docs/evals/artifacts/v5d-20260811-01/v5d-mixed-production-{desktop,mobile}.{json,png}` with `productionStart=true`, `mockedBff=false`

### D-G6 evidence

- Seed CLI: `apps/worker/scripts/v5d_mixed_deployment_seed.py` (live API/Worker ingest of PDF+Image+Markdown + historical citations)
- Restore CLI: `apps/worker/scripts/v5d_mixed_restore_acceptance.py` snapshot/verify
- Harness: `infra/scripts/run-v5d-mixed-acceptance.sh --mode mixed-live` → `engineeringGate=mixed-live-pass`
- Live snapshot semantic self-verify passed for three modalities

### Remaining for D-G7

1. Full API/Worker/Web matrix (lint/tsc/build/compileall + broader suites)
2. Optional: full empty-target Compose backup/restore using the new mixed CLIs
3. Independent Critical closeout per `verification-matrix-v5d.md`
4. No claim of R803 model quality or M404 user value

No commit or push unless explicitly requested.


## D-G7 closeout (2026-08-12)

Status: **ACCEPT for engineering / internal-preview D-G7 full regression**.

Controller re-ran the full matrix on worktree `/home/cc/code/citeframe` at
source SHA `4f2129cdfc5ba0c73cf854c83add7809c5966b0a` with retained dirty
V5-C/V5-D delivery:

| Suite | Result |
|---|---|
| API full | 562 passed, 1 warning |
| Worker full | 296 passed |
| Web unit | 131 passed |
| lint / tsc / build | pass |
| compileall API+Worker | pass |
| git diff --check | pass |
| V5-D docs relative links | 0 broken |

Evidence: `docs/evals/artifacts/v5d-20260811-01/d-g7/` and
`docs/evals/artifacts/v5d-20260811-01/d-g7-full-regression-report.md`.

### Checklist

| Area | Verdict |
|---|---|
| goal alignment | pass — closes D-G7 engineering matrix without scope expansion |
| user-visible flow / timing | pass — no new UI path; prior D-G4 production-start retained |
| architecture / boundaries | pass — no new registry/modality/selector |
| data contracts / save | pass — no schema/API/save change in D-G7 run |
| implementation quality | pass — full suites green on dirty delivery tree |
| verification / evolution | pass-with-residuals — see residual list in D-G7 report |

### Residual risks (recorded, not rework blockers for engineering gate)

- optional full empty-target Compose restore for D-G6
- F5 historical-row Medium residual
- R803/M404 not_evaluable
- uncommitted dirty tree pending explicit user commit request
- no new mixed Research Playwright campaign in this D-G7 run (V5-C Research evidence retained)

Overall Critical verdict for V5-D engineering slice: **ACCEPT** with residuals.
Product remains `internal_preview`. Do not claim Beta/release or model quality.
