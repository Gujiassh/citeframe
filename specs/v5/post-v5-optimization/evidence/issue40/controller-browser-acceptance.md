# Issue40 controller browser and candidate acceptance

Date: 2026-09-28, Asia/Shanghai. Product candidate: `635bb2b8703ae6c77fee5cb28d08d852bd67b7ae`.
Controller used actual Chrome through `cua_repl`, the normal login form and visible product controls.
No browser storage/session injection, mocked browser routes, external model calls or real-user accounts were used.
The local fixture is explicitly synthetic; this evidence makes no model-quality or real-user-value claim.

## Runtime and identities

- Web: `http://127.0.0.1:18430`; FastAPI: loopback `18400`.
- Actual isolated PostgreSQL17.11 on18432 and MinIO on18410; database and object namespace were created for Issue40.
- Designated owner belongs to A and B; designated member belongs to A and created the synthetic completed report.
- Credentials and private runtime logs remain under ignored `.local-runtime/artifacts/issue40-dev/runtime/` and are not included here.
- API/Web used unchanged candidate product source. The local provider origin is loopback18481 with a fixture-only stored key; no provider request was sent.

## Visible walkthrough results

| Path | Actions and directly observed result | Result |
| --- | --- | --- |
| Owner login and selection | Login form -> workspace list -> A; A/B listed with owner role; A asset, chat, notes and settings loaded | Pass |
| Workspace settings persistence | Changed system prompt to `Synthetic Issue40 browser acceptance. Answer only from supplied evidence.`, saved, reloaded entire page and reopened Configuration; exact value persisted | Pass |
| Notes persistence | Edited existing A note to `Saved through the visible browser permission walkthrough.`, saved, reloaded entire page and reopened Notes; exact body rendered | Pass |
| Empty model-config input | Attempted save with missing API Base URL; visible required-field feedback appeared without silently saving | Pass, client validation only |
| Owner model configuration | After fixture-only local connection setup, changed only model name to `issue40-browser-saved-no-calls`, leaving credential field untouched; Save displayed `已保存` and revision4; Reload configuration retained exact name, revision and loopback URL | Pass |
| Member access | Signed out and logged in with designated member; workspace list contained A only; A note content loaded | Pass |
| Member management restriction | Configuration showed disabled system-prompt/save/sliders, with owner model-management panel absent | Pass; backend denials independently covered by API tests |
| Cross-workspace navigation | While A-only member, navigated to known B workspace URL; returned to home with only A and no B data displayed | Pass; exact backend status established separately |
| Report read and creator save | Member -> A -> AI chat -> Deep Research; original report, hash prefix `fe6708aabac6`, frozen profile and Edit rendered; saved `Synthetic Issue40 browser report` successfully | Pass |
| Report persistence | Opened a second Chrome tab from the real A workspace URL, selected Deep Research then User-edited; exact first-tab saved title/body rendered | Pass |
| Version conflict | Kept first-tab draft `Synthetic Issue40 stale draft / This draft must survive a version conflict.`; second tab saved `Synthetic Issue40 newer version / Second tab saved first.`; first-tab Save showed `Another tab saved a newer version. Your draft is preserved.`, kept draft and disabled Save | Pass |
| Conflict recovery | Selected `Use my draft with latest version`, then Save; original draft title/body rendered successfully | Pass |

The first report attempt correctly failed on a synthetic provenance mismatch. The original developer repaired only the fixture attempt hash, and the unchanged full validator was verified before repeating the successful walkthrough. Production provenance checks were never weakened.

## Independent controller command

From `D:/Code/citeframe`, using a fresh controller temporary directory:

```powershell
$env:PGCONNECT_TIMEOUT='2'
apps/api/.venv/Scripts/python.exe -u -m pytest -c pytest.ini `
  apps/api/tests/test_workspace_access_dependencies.py `
  apps/api/tests/test_workspace_permission_precedence.py `
  apps/api/tests/test_workspace_model_settings.py `
  apps/api/tests/test_research_report_edit.py `
  apps/api/tests/test_research_publication_adoption.py `
  apps/api/tests/test_research_worker_budget_recovery.py `
  -q -p no:cacheprovider --basetemp=.local-runtime/artifacts/issue40-controller-candidate-01
```

Result: **75 passed**, one existing Starlette TestClient/httpx deprecation warning,94.00s.
This command used deterministic test fixtures; actual PostgreSQL lock/CAS and Worker persistence checks are separately recorded in `postgres-safety.json`.

## Scope limits and current gate

- This validates the recorded normal UI paths and error/recovery states, not every UI action or model workflow.
- Synthetic completed Research/ingestion data is engineering acceptance data; no full real-provider research run was claimed.
- Worker/provider revocation, object side effects, hash/CAS and all route guards require their API/persistence evidence in addition to this walkthrough.
- F2 disposition: the two short initial SSE sessions are accepted for this request-boundary design. Independent measurement found the same4 SQL queries and1 membership query. No write transaction or polling revalidation moved. The initial session lifecycle is explicitly different from baseline.
- Initial CI exposed a timezone-dependent test fixture and an unadapted Worker direct-handler test; original developer rework remains required. Service CI is separately blocked by the pinned MinIO registry image returning unauthorized, including one retry.
- This artifact is bounded candidate evidence. Independent final review, final CI and merge are not asserted by this document.
