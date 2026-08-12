# V5-B / V5-C Implementation Lanes

## 使用规则

本文件定义 spec gate 通过后的实现分工。当前 B-SPEC 已接受 Markdown-only v1；B-API-DOC、B-WORKER-DOC、B-WEB-DOC、B-RESTORE、B-INT-MIXED 已完成 isolated/canonical implementation 与 Critical review。online migration、live scoped PostgreSQL/MinIO restore、standalone browser 与 B008 formal isolated deployment Critical closure 已通过；accepted B008 artifact 为 `docs/evals/artifacts/v5b-document-deployment-v4/`（v1 历史 early pass，v2 Worker health predicate 失败证据，v3 中断 partial 证据保留）。只读审计可以并行；同一 worktree 同一时间只有一个 writer。实现 worker 必须使用 `grok-4.5`，独立 reviewer 不承担实现。

每个 lane handoff 必须报告：changed files、未完成项、命令和 exit code、fixtures/artifacts、contract impact、残余风险、是否需要 owner decision。任何 schema/API/save-contract 变化必须先停工。

## Gate 0：开始前

- canonical worktree：`/home/cc/code/citeframe`；V5-A 已在 `origin/main`。
- 关闭或 quarantine 旧 V5-A worktrees，避免从旧 SHA 开始。
- 处理当前未提交的 docs/SSoT dirty set，明确哪些进入 specs baseline。
- 写入 `open-decisions.md` 的批准状态。
- 创建本轮 workbench task/checkpoint。

## V5-B lanes

### B-SPEC：Modality brief and contract

状态：`accepted-for-markdown-v1`; HTML/Audio/Video remain separate gates

专属路径：

```text
specs/v5/multimodal-agent-product/v5b-*
specs/v5/multimodal-agent-product/briefs/*
```

`open-decisions.md` 由 main controller 串行维护；B-SPEC 只能提交 OD-B proposal，不与 C-SPEC 并行写同一文件。

职责：完成 first modality brief、literal、字段/API/locator/migration impact、fixture manifest requirements 和 B-G3 review package。不得改 production code，也不直接写 shared decision log。

验证：文档 link check、cross-reference audit、save-contract checklist、独立 Standard review。

### B-AUDIT：Shared PDF/Image entry audit

状态：`accepted-canonical`

专属路径：

```text
apps/api/tests/test_v5b_shared_entry_audit.py
apps/web/src/lib/evidence/shared-entry-audit.test.ts
specs/v5/multimodal-agent-product/shared-entry-audit.md
```

职责：确认 registry/catalog/upload/Asset detail/evidenceTargets/retrieval/delete/restore 的共享入口，列出最小必要 gap。默认只加测试，不改 shell 业务分支。

验证：existing PDF/Image full focused suite、registry exact-match、mixed workspace oracle。

### B-API-DOC：Document API/data/codec

状态：`accepted-canonical; live-migration-passed`

专属路径，需在 lane assignment 中按实际文件精确锁定：

```text
apps/api/src/ai_pdf_api/modalities/document*.py
apps/api/src/ai_pdf_api/models/*document*.py
apps/api/src/ai_pdf_api/schemas/*document*.py
apps/api/tests/test_document_api_contract.py

Migration files under `apps/api/alembic/versions/` are applied by the main controller after approval; B-API-DOC supplies the migration patch and tests but does not concurrently edit that shared directory.
```

共享文件如 `models/catalog.py`、`modalities/registry.py`、`schemas/chat.py`、Asset router 必须由 main controller 串行合并，B-API-DOC 不得自行占用。

职责：typed catalog rows、locator detail table/codec、DTO discriminator、migration/restore impact。若 schema change 未获批准，lane 只写 contract tests，不写 migration。

验证：API focused tests、Alembic upgrade/check、compileall、OpenAPI/discriminator fixture、locator clone/retrieval-key tests。

### B-RESTORE：Document backup/restore extension

状态：`accepted-canonical; formal-isolated-deployment-accepted-v4`

专属路径：

```text
apps/worker/tests/test_v5b_restore_*.py
docs/evals/artifacts/v5b-document-*/
infra/scripts/*  # only if the approved restore harness needs a narrowly assigned change
```

职责：把已批准的 Document catalog/representation/content-unit/locator tables、objects、Citation/NoteSource snapshots 加入现有 isolated PostgreSQL/MinIO restore oracle。B-INT-MIXED 提供 fixture manifest；B-RESTORE 负责 live command/artifact/checksum/zero-residue evidence。不得以 SQLite 或 generic R800 fixture 代替新增 Document rows/objects 的恢复证据。

验证：`infra/scripts/run-r800-acceptance.sh` 或仓库实际 restore harness 的明确参数、DB row checksum、object SHA-256、API/Viewer replay 和 teardown。

### B-WORKER-DOC：Document adapter

状态：`accepted-canonical`

专属路径：

```text
apps/worker/tests/test_document*.py
```

职责：source decode、normalize、structure blocks、typed row persistence through the existing `IngestionAdapter`/`IngestionResult` seam、GeneratedObject manifest、cleanup 和 capability/error mapping。不得访问 Chat/Research ORM，不得改共享 ingestion orchestrator；如果 seam 必须改变，交给 main controller 的 serial seam lane。

验证：valid Markdown；HTML 只有在 OD-B1/B5 批准后才加入 valid HTML；invalid encoding/MIME、determinism、partial cleanup、retry/no resurrect、compileall、Worker focused suite。

### B-WEB-DOC：Document Evidence renderer

状态：`accepted-canonical; standalone-browser-passed`

专属路径：

```text
apps/web/src/components/evidence/document*
apps/web/e2e/document*.spec.ts
```

职责：upload accept、detail parser、locator renderer、heading/block jump、unavailable/unknown locator state、responsive layout。不得在 Workspace/Chat shell 增加 `if document` 分支。

验证：Web unit、TypeScript、lint、production build、Playwright production-start locator jump。

### B-INT-MIXED：Mixed workspace and recovery

状态：`accepted-canonical; live-focused-passed; formal-isolated-deployment-passed`

专属路径：

```text
apps/worker/tests/test_v5b_mixed_workspace.py
apps/worker/tests/test_v5b_recovery.py
apps/web/e2e/v5b-mixed-workspace.spec.ts
apps/web/e2e/fixtures/v5b/*
docs/fixtures/document-modality/*
```

职责：PDF+Image+Document mixed retrieval, citation/note clone, generation/reindex, delete/delete-retry, restore, permission and no cross-kind leakage。

验证：B verification matrix 的 full required gates；不得改生产实现来“放宽” oracle。

### B-REVIEW：Enablement review

状态：`critical-rework-closed; formal-isolated-deployment-accepted-v4; final-critical-accept`

职责：Critical review goal/architecture/data contract/save semantics/security/cost/runtime evidence，确认 code registry、catalog、fixtures、restore 和 Web module 同批 enablement。只有 `ACCEPT` 后才允许启用 catalog rows。

## V5-C lanes

### C-SPEC：V4 delta and product freeze

状态：`approved; implementation-ready@2026-08-10`

专属路径：

```text
specs/v5/multimodal-agent-product/v5c-*
```

`open-decisions.md` 已由 main controller 串行维护并批准 OD-C1/C2/C3/C4/C5/C8；后续合同变更仍由 main controller 串行维护。

职责：把 C001-C008 改写成现有 V4 delta，冻结 status/control/timeline/branch/artifact/role I/O/permission/budget acceptance。不得重写 V4 runtime。

### C-API-WORKER：Research contract, usage and context

状态：`implemented; focused/full gates and live PostgreSQL round-trip passed; independent Critical review ACCEPT`

专属路径：由 main controller 针对真实缺口逐文件分配 `apps/api/src/ai_pdf_api/models/research_*.py、apps/api/src/ai_pdf_api/schemas/research.py、apps/api/src/ai_pdf_api/services/research_worker_*.py；以及由 main controller 串行合并的 migration。Worker ownership 为 apps/worker/src/ai_pdf_worker/research_agent_schemas.py、research_runtime_agents.py、research_runtime_ports.py 及对应 focused tests。

职责：实现批准的 strict production role-I/O registry、snapshot version fields、legacy reader、usage-only DTO、optional pricing/unknown state、per-call context/output gates、typed compact/batch contract 和 stable failure mapping。所有 migration/save impact 由 main controller 串行审核并合并；不得写 money UI。

### C-WEB-PRODUCT：Research product surface

状态：`implemented in canonical worktree; production-start gate passed; independent Critical review ACCEPT`

专属路径：

```text
apps/web/src/components/research-run*.tsx
apps/web/src/lib/research/product*.ts
apps/web/e2e/v5c-research-product.spec.ts
```

职责：timeline projection、branch grouping、approval/conflict/retry/cancel/reconnect controls、artifact/evidence drill-down、desktop/mobile states。只消费 API DTO/events，不把 runtime UI state写回 DB。

与 B-WEB-DOC 的边界：B 只拥有 evidence/document module；C 只拥有 research surfaces；共享 i18n 由 main controller 串行处理。

### C-BOUNDARY：Research security/usage/context/recovery audit

状态：`focused boundary coverage and R800 v6 present; independent Critical review ACCEPT; F1/F5 Medium follow-up remains`

专属路径：

```text
apps/api/tests/test_v5c_boundary_*.py
apps/worker/tests/test_v5c_boundary_*.py
specs/v5/multimodal-agent-product/v5c-boundary-review.md
```

职责：workspace/membership/creator-only decisions/tool allowlist/evidence handle scope/provider fingerprint/usage limits/context compact/lease/cancel/recovery/log secret checks，使用 API/Worker boundary test files；不拥有 C-WEB-PRODUCT 的 Web files。

### C-REGRESS：Cross-layer acceptance

状态：`focused, production-start and isolated R800 v6 gates passed; full independent C acceptance ACCEPT`

专属路径：tests/fixtures/docs only, limited to the exact C regression files assigned by main controller；不得写 B-INT-MIXED fixture paths 或 review artifacts。

职责：C008 Quick Chat、Citation、NoteSource、Research old save semantics、A007 Chat HTTP shape、production-start E2E，以及本轮强制的隔离 full R800 acceptance。

### C-REVIEW：Independent Critical review

状态：`ACCEPT@2026-08-10`

专属路径：no production edits。

职责：从 goal alignment、V4 boundary、data/save contract、security/permission、runtime evidence 和 mobile UX 反向审计。已接受 V5-C 工程/发布门；F1 registry mapping 与 F5 historical-row bytes/hash 在引入下一 registry version 前补齐。`R803/M404` 仍不属于本工程 gate。

## 不可并行的共享 ownership

以下路径不能被两个 writer 同时修改：

```text
apps/api/src/ai_pdf_api/modalities/registry.py
apps/api/src/ai_pdf_api/models/catalog.py
apps/api/src/ai_pdf_api/routers/assets.py
apps/api/src/ai_pdf_api/schemas/chat.py
apps/api/src/ai_pdf_api/services/ingestion.py
apps/api/src/ai_pdf_api/services/retrieval.py
apps/web/src/lib/evidence/production-registry.ts
apps/web/src/lib/i18n-context.tsx
specs/v5/multimodal-agent-product/open-decisions.md
apps/api/alembic/versions/*
infra/scripts/*
docs/evals/artifacts/v5b-document-*
Research models/schemas/services and shared Web research presentation files
```

main controller 负责串行合并这些 seam files，并在每次合并后运行最小 gate。

## Recommended launch order

```text
B-SPEC + C-SPEC (read/write docs only, parallel)
  -> independent review + owner decisions
B-AUDIT
  -> B-API-DOC
       -> B-WORKER-DOC + B-WEB-DOC (disjoint, parallel)
            -> B-INT-MIXED
                 -> B-REVIEW
C-API-CONTRACT (only if proven)
  -> C-WEB-PRODUCT + C-BOUNDARY (disjoint where possible)
       -> C-REGRESS
            -> C-REVIEW
```
