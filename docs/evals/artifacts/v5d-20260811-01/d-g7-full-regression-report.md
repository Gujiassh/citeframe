# D-G7 Full Regression Report

Date: 2026-08-12  
Lane: D-ACCEPT (main controller full matrix)  
Worktree: `/home/cc/code/citeframe`  
Source SHA baseline: `4f2129cdfc5ba0c73cf854c83add7809c5966b0a`  
Commit/push: **not performed** (policy: only on explicit user request)

## Verdict

**engineeringGate=pass** for D-G7 full API/Worker/Web regression on the current
dirty V5-C/V5-D worktree. Product stage remains `internal_preview`.
`realModelQualityPassed=false`, `userValuePassed=false`.

## Commands and results

| Suite | Command | Result | Exit |
|---|---|---|---|
| API full | `uv run --project apps/api python -m pytest apps/api/tests -q --tb=line` | **562 passed**, 1 warning | 0 |
| Worker full | `uv run --project apps/worker python -m pytest apps/worker/tests -q --tb=line` | **296 passed** | 0 |
| Web unit | `pnpm --dir apps/web test` | **131 passed** | 0 |
| Web lint | `pnpm --dir apps/web lint` | pass | 0 |
| Web tsc | `pnpm --dir apps/web exec tsc --noEmit` | pass | 0 |
| Web build | `pnpm --dir apps/web build` | pass | 0 |
| compileall API | `uv run --project apps/api python -m compileall -q apps/api/src apps/api/tests` | pass | 0 |
| compileall Worker | `uv run --project apps/worker python -m compileall -q apps/worker/src apps/worker/tests` | pass | 0 |
| git diff --check | `git diff --check` | pass | 0 |
| V5-D docs paths + relative links | path existence + link scan | 0 broken | 0 |

Logs: `docs/evals/artifacts/v5d-20260811-01/d-g7/`.

## Prior focused gates retained

- D-G0 pass (gate0-record + state.json)
- D-G1 pass-focused (mixed retrieval tests)
- D-G2 pass-focused (use-chat 7 after F1 rework; full Web unit now 131)
- D-G3 partial-existing-v5c (Research production-start from V5-C acceptance)
- D-G4 pass-production-start (mixed desktop/mobile Playwright)
- D-G5 partial-existing-unit (restart/delete/recovery covered by existing suites)
- D-G6 pass-focused-live-seed-snapshot (mixed live seed/snapshot/self-verify)

## Residuals (explicit, not blockers for engineering internal-preview)

1. D-G6 full empty-target Compose backup/restore loop remains optional residual.
2. F5 live pre-V5-C historical-row bytes/hash deferred until next registry version.
3. R803 / M404 remain `not_evaluable` (V5-E).
4. Worktree remains dirty with uncommitted V5-C/V5-D delivery; no commit/push.
5. D-G3/D-G5 did not add a new dedicated mixed Research Playwright campaign in this D-G7 run; they rely on existing V5-C Research production-start and unit recovery evidence.

## Non-goals confirmed

- No new modality, locator, registry version, provider selector, or save-contract change in this D-G7 execution.
- No claim of model quality or user value.
