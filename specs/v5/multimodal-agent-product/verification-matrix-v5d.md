# V5-D Verification Matrix

## 0. Evidence policy

每个 gate 必须记录命令、exit code、测试数量、源 SHA、fixture/artifact 路径、
关键日志/网络/DOM/state 证据、review verdict 和 residual risk。不能以 agent
口头报告或单一 `coveragePassed=true` 代替证据。

本矩阵区分四类证据：工程回归、live deployment/restore、R803 模型质量和
M404 用户价值。V5-D 只能宣布工程/internal-preview gate 通过。

## 1. Baseline and mandatory commands

### API

```bash
uv run --project apps/api python -m pytest apps/api/tests -q --tb=short
uv run --project apps/api python -m compileall -q apps/api/src apps/api/tests
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api alembic -c apps/api/alembic.ini check
```

### Worker

```bash
uv run --project apps/worker python -m pytest apps/worker/tests -q --tb=short
uv run --project apps/worker python -m compileall -q apps/worker/src apps/worker/tests
```

### Web

```bash
pnpm --dir apps/web test
pnpm --dir apps/web lint
pnpm --dir apps/web exec tsc --noEmit
pnpm --dir apps/web build
```

涉及用户路径时必须使用 production-start standalone server，而不是 dev
watcher。桌面和移动目标视口分别是 `1440x1000` 与 `390x844`：

```bash
pnpm --dir apps/web build
HOSTNAME=127.0.0.1 PORT=3100 node apps/web/.next/standalone/apps/web/server.js
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3100 pnpm --dir apps/web exec playwright test e2e/<focused>.spec.ts
```

### Repository and docs

```bash
git diff --check
git diff --cached --check
git status --short
```

检查以下文档和所有新增相对链接：

```bash
for path in \
  specs/v5/multimodal-agent-product/README.md \
  specs/v5/multimodal-agent-product/decision-2026-08-11-v5d-scope.md \
  specs/v5/multimodal-agent-product/v5d-detailed-spec.md \
  specs/v5/multimodal-agent-product/implementation-lanes-v5d.md \
  specs/v5/multimodal-agent-product/verification-matrix-v5d.md \
  specs/v5/multimodal-agent-product/grok-handoff-v5d.md \
  specs/v5/multimodal-agent-product/save-contract-checklist.md; do
  test -f "$path" || exit 1
done
```

## 2. Gate table

| Gate | Scope | Required evidence | Pass condition |
|---|---|---|---|
| D-G0 | baseline/contract | source SHA/status, dirty disposition, F1/F5 record, lane map, artifact root | no unknown owner; no unapproved contract change; no new registry version |
| D-G1 | mixed asset/scope/retrieval | API/Worker focused tests, mixed PDF/Image/Document fixture, candidate trace | scope, Workspace, generation, index and typed locator filters are exact; no leakage |
| D-G2 | Quick Chat/Citation/NoteSource | API contract tests, Chat SSE/error tests, historical snapshot comparison | old public shape and save semantics unchanged; no half-save; source unavailable semantics preserved |
| D-G3 | Research integration | Research mixed-Evidence fixture, production-start Research, role/snapshot/recovery tests | fixed executor, frozen snapshot, branch/join, retry/cancel/recovery and Artifact semantics pass |
| D-G4 | desktop/mobile UX | production-start Playwright at both target viewports, screenshots, DOM/state snapshots | all primary flows pass; no overlap/overflow; unknown locator/provider/source is explicit unavailable |
| D-G5 | restart/delete/recovery | API/Worker/Web restart/reclaim/retry tests, delete/no-resurrection tests, logs | no duplicate final Artifact/message, no resurrection, stable error and idempotency behavior |
| D-G6 | live deployment/restore | isolated PostgreSQL/MinIO run, backup/restore, row/object checksums, API/DOM replay, cleanup | before/after semantic identity and object SHA match; Alembic/image/readiness/zero residue pass |
| D-G7 | full regression/review | full API/Worker/Web, compileall, lint/tsc/build, docs/link check, independent review | all required suites pass; Critical review `ACCEPT`; residuals explicitly recorded |

## 3. D-G0 preflight oracle

- The tested SHA and worktree status are recorded before and after every lane.
- V5-C dirty changes are classified as owner work, not silently overwritten.
- F1 executable mapping test proves each role/version resolves the exact schema,
  validator, prompt binding, runtime adapter, and Web projection.
- F5 live historical-row fixture records finished artifact bytes/hashes before and
  after legacy retry/recovery; if deferred, the acceptance report says why and
  confirms no new registry version is enabled.
- Any API/database/save/replay/permission/cost/locator change has a decision ID or
  is rejected before implementation.

## 4. Functional test cases

### Mixed Workspace and retrieval

1. Seed one PDF, one Image, and one Markdown Document in one Workspace.
2. Verify all three appear with exact registry kind/catalog metadata.
3. Run selected-scope retrieval and assert every candidate belongs to the frozen
   scope, current generation, current index contract, and valid typed locator.
4. Run all-eligible-scope retrieval and assert no foreign Workspace candidate.
5. Open PDF page/region, Image region, and Document block/range from candidate,
   Citation and NoteSource; compare target locator payloads.
6. Reprocess one asset, reindex one asset, delete one asset, and retry delete;
   verify historical snapshot, source availability and no-resurrection rules.

### Quick Chat and Research

7. Send mixed-scope Quick Chat and verify the existing SSE, public error shape,
   message persistence, citations and NoteSource clone.
8. Run Research over the same mixed scope; verify plan, branch evidence,
   provider/model/usage projection, Artifact and server-seq timeline.
9. Exercise approval/revise, one branch retry, cancel, lease reclaim and restart;
   verify no duplicate final Artifact and no current-profile fallback.
10. Force provider/index/context/source failures and verify stable error codes,
    retryability and no half-persisted business state.

### Responsive and deployment

11. Run the primary flow at `1440x1000` and `390x844`; record screenshots and DOM/state.
12. Run isolated live backup/restore, replay mixed asset and Research paths, compare
    PostgreSQL semantic hash, MinIO object SHA-256, generated report and cleanup.

## 5. Required artifact manifest

A D acceptance directory such as `docs/evals/artifacts/v5d-YYYYMMDD-N/` must contain,
where applicable:

- `state.json`, `before.json`, `after.json`, `verification.json`;
- source SHA/status and lane manifests;
- API/Worker/Web startup/readiness logs and server PID/close evidence;
- Playwright output, screenshots, DOM/state snapshots and network summary;
- backup manifest, PostgreSQL dump/checksum, MinIO object checksum;
- migration/head output, image/runtime manifest, restore log;
- `report.json` with gate results and `cleanup.json` with zero-residue result;
- review record listing each checklist item as `pass`, `not applicable`, or `blocked`.

## 6. Pass/fail rules

- `pass`: evidence exists and the invariant is directly verified.
- `not applicable`: the gate is genuinely outside this slice and the reason is recorded.
- `blocked`: prerequisite environment or contract decision is missing; never count as pass.
- Any unexplained test decrease, altered old payload, missing live restore evidence,
  unresolved permission leak, fallback path, or unowned dirty change is a release blocker.
- Scripted provider evidence demonstrates engineering plumbing only; it cannot set
  `realModelQualityPassed=true` or `userValuePassed=true`.
