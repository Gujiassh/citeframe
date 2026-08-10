# V5-B / V5-C Verification Matrix

## 0. Evidence policy

每个 gate 必须记录：命令、exit code、测试数量、fixture/artifact 路径、关键日志/网络/DOM 证据、review verdict 和 residual risk。仅“worker 声称通过”不算 verified。

Ruff 当前环境缺少 executable，记录 `not-run`；不能用它替代 API/Worker/Web gates。R803/M404 不是 B/C 功能 gate。

## 1. Canonical commands

### API

```bash
uv run --project apps/api python -m pytest apps/api/tests -q --tb=short
uv run --project apps/api python -m compileall -q apps/api/src apps/api/tests
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api alembic -c apps/api/alembic.ini check
```

涉及迁移、备份或恢复时，必须运行隔离 PostgreSQL/MinIO gate；SQLite 只能作为 unit evidence，不能替代 live runtime。B-G5/C-G7 的 live artifact 至少包括：隔离 project 名、API/Worker/Web image/version、Alembic head、backup/restore command、DB row checksum、object SHA-256、关键 API/DOM 证据和 teardown/zero-residue 结果。复用 `infra/scripts/run-r800-acceptance.sh` 或仓库实际 R800 deployment script，不得只写“restore passed”。

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

涉及用户流程时必须使用 production-start，不依赖 dev watcher。当前 `apps/web/next.config.ts` 使用 standalone output，故使用与 production Dockerfile 等价的 server entry，而不是 `next start`：

```bash
pnpm --dir apps/web build
HOSTNAME=127.0.0.1 PORT=3100 node apps/web/.next/standalone/apps/web/server.js
# in a second shell after HTTP readiness:
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3100 pnpm --dir apps/web exec playwright test e2e/<focused>.spec.ts
```

实际执行记录必须包含：server PID、启动日志/HTTP readiness、Playwright output、截图或 DOM/state evidence、关闭结果。`PLAYWRIGHT_START_WEB=1` 只适用于明确需要 dev-server 的开发调试，不是本矩阵的 production evidence。

### Repository

```bash
git diff --check
git diff --cached --check
git status --short
```

### Docs

```bash
for path in \
  specs/v5/multimodal-agent-product/README.md \
  specs/v5/multimodal-agent-product/open-decisions.md \
  specs/v5/multimodal-agent-product/v5b-detailed-spec.md \
  specs/v5/multimodal-agent-product/v5c-detailed-spec.md \
  specs/v5/multimodal-agent-product/implementation-lanes-v5bc.md \
  specs/v5/multimodal-agent-product/verification-matrix-v5bc.md \
  specs/v5/multimodal-agent-product/save-contract-checklist.md; do
  test -f "$path" || exit 1
done
git diff --check
```

This is the minimum existence/whitespace gate; every relative link introduced by a change must also be manually checked against its target before review.

## 2. V5-B matrix

| Gate | Required evidence | Minimum tests / artifacts | Pass condition |
|---|---|---|---|
| B-G0 | canonical worktree and decision disposition | status snapshot, workbench checkpoint | no stale worker owns canonical; open decisions listed |
| B-G1 | approved brief | brief, cost/privacy/security notes, independent review | first modality and non-goals explicit |
| B-G2 | shared-entry audit | registry/catalog/upload/evidence/retrieval/delete test report | PDF/Image existing tests unchanged; no shell business branch |
| B-G3 | approved contract | decision doc, API JSON fixtures, locator examples, migration impact | literals, fields, state, cleanup and restore are frozen |
| B-G4 | first modality happy path | API/Worker/Web focused suites; fixture SHA manifest | upload→ready→retrieve→cite→note→view passes |
| B-G5 | lifecycle and mixed workspace | mixed PDF/Image/Document, generation/reindex, delete/delete-retry, permission, no-resurrection tests | historical snapshot invariants pass; no fallback |
| B-G6 | Critical review | review artifact + code/catalog/fixture diff | independent `ACCEPT`; only then enable registry/catalog |
| B-G7 | Audio/Video | ASR capability contract, modality brief, temporal fixtures | no Audio/Video production enablement before prerequisites |

B-G5/B-RESTORE 最小 live command（仅在 Document fixture/migration approved 后执行）：

```bash
bash infra/scripts/run-r800-acceptance.sh \
  --output-dir docs/evals/artifacts/v5b-document-YYYYMMDD-N \
  --project citeframe-r800-v5b-document-n
```

如果现有 R800 fixture 不能生成 Document rows/objects，必须由 B-RESTORE 扩展 fixture/restore snapshot 后再执行；不能把 generic R800 的绿色结果当成 Document restore 证据。

### B-G4 focused matrix

1. Registry exact code/catalog/contract version match.
2. Valid bytes + MIME succeeds; extension-only mismatch fails.
3. Invalid encoding/parse/normalization fails before derived persistence.
4. Generated object manifest SHA and content type match; DB failure cleans objects.
5. ContentUnit order and locator payload are deterministic across two runs.
6. Dense/lexical retrieval returns only registered signature and current index.
7. Citation locator serializes and NoteSource clones into an independent locator row.
8. Viewer opens exact block/range; unknown locator/version is unavailable, never first-match.
9. Missing capability fails before provider HTTP and before representation/content-unit persistence.

### B-G5 lifecycle matrix

1. Reprocess increments generation; old citation/note source payload byte/semantic snapshot unchanged.
2. Failed new generation leaves old ready generation active.
3. Reindex remains explicit; mismatched index returns stable error.
4. Delete cleans source/derived objects and current rows; historical snapshot stays readable.
5. Delete retry is idempotent; late ingest cannot resurrect deleted asset.
6. Mixed workspace retrieval cannot leak cross-kind or cross-workspace candidates.
7. Backup/restore preserves catalog rows, representations, content units, locators, snapshots and object SHA.
8. Workspace membership and file/display endpoint checks reject foreign asset IDs.

## 3. V5-C matrix

| Gate | Required evidence | Minimum tests / artifacts | Pass condition |
|---|---|---|---|
| C-G0 | V4 baseline/delta map | delta doc, A006/A007 residual list | no V4 reimplementation scope |
| C-G1 | productization contract | open decisions + non-goals + API/save impact | pure delta or approved additive change |
| C-G2 | entry/status/control projection | DTO fixtures and control matrix | Quick and Research truth remain separate |
| C-G3 | typed I/O/join/evidence contract | schema fixture, malformed output tests, branch scope tests | strict schema and join rules pass |
| C-G4 | control product path | Web unit + focused API action tests | approve/revise/conflict/retry/cancel states correct |
| C-G5 | timeline and comprehension | production-start desktop/mobile E2E, SSE replay fixture | seq/order/reconnect/branch/artifact display correct |
| C-G6 | boundary review | permission/budget/provider/tool/recovery tests + Critical review | no secret leak, cross-workspace access, budget bypass or non-retryable retry |
| C-G7 | full regression | API/Worker/Web full, Quick/Citation/NoteSource, Research production E2E | all existing contracts green; independent `ACCEPT` |

### C-G3 role/branch matrix

1. Planner rejects empty/duplicate/non-contiguous subproblems.
2. Planner cannot select assets outside frozen scope.
3. Researcher handle must belong to same run/snapshot/step/branch.
4. Join waits for all materialized researcher branches and rejects missing/duplicate output.
5. Verifier output claim IDs exactly match researcher claim set.
6. Critic IDs belong to verified set; no new fact claim.
7. Synthesizer cannot publish unsupported or conflicted fact.
8. Publisher creates at most one final report per execution and is idempotent.
9. Unknown/extra schema fields fail closed; raw provider output is not persisted as business truth.

### C-G4 control matrix

| State | Creator | Member | Owner emergency |
|---|---|---|---|
| `awaiting_plan_approval` | approve/revise/cancel | read only | cancel cost/security |
| `running` | cancel | read only | cancel cost/security |
| `awaiting_human_decision` conflict | submit allowed decision/cancel | read only | cancel cost/security |
| `awaiting_retry` | retry eligible failed branch/cancel | read only | cancel cost/security |
| `cancel_requested` | no duplicate cancel | read only | no duplicate cancel |
| terminal | read artifact/history | read artifact/history | no mutation |

Every action test includes creator mismatch, stale state version, wrong decision hash, repeated idempotency key and terminal state.

## 4. Critical review checklist

Reviewer marks every item `pass`, `not applicable`, or `blocked`:

- Goal alignment and user-visible flow/timing
- Asset/Research/module ownership boundaries
- Runtime state vs persistent state
- Provider/profile, secret and fingerprint boundary
- API/schema/catalog/literal alignment
- Citation/NoteSource/Chat/Research save semantics
- Permission, Workspace scope and action idempotency
- Error/retry/fallback/recovery behavior
- Mixed workspace and historical snapshot behavior
- Unit/integration/runtime/browser evidence
- Backup/restore impact
- Production registry enablement gate
- Remaining architecture debt and future end-state fit
