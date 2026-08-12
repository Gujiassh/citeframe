# V5 多模态 AI 知识工作台与 Agent 协作任务

## 状态

- [x] 完成 capability-first 方向裁决
- [x] 创建 V5 主规格、实施计划和任务清单
- [x] V5-A Provider 与模型能力层（A002-A007 已完成；A007 跨层回归已验收）
- [x] V5-B 多模态资料扩展（Markdown-only `document` v1：isolated/canonical implementation、前序 Critical review、online migration、live scoped PostgreSQL/MinIO restore、standalone browser `4 passed` 与 B008 formal isolated deployment Critical closure 已通过；accepted deployment artifact=`docs/evals/artifacts/v5b-document-deployment-v4/`；HTML/Audio/Video 仍受 OD-B5/B6/B7 独立 gate 阻塞）
- [x] V5-C 多 Agent 协作产品化（2026-08-10 工程/发布门 `ACCEPT`；严格版本化 production Agent I/O、usage/context、Web projection、production-start Research、online migration 与 R800 v6 已通过；F1/F5 为 Medium 后续风险）
- [x] V5-D 端到端整合与工程稳定（2026-08-12 D-G7 全量回归通过：API 562 / Worker 296 / Web 131；Critical `ACCEPT` with residuals；internal-preview；R803/M404 仍后置；未 commit/push）
- [ ] V5-E 模型质量与用户价值

### V5-B/C 详细规格状态

- [x] B-G1 first modality brief and priority approval
- [x] B-G2 shared PDF/Image entry audit
- [x] B-G3 document locator/API/catalog contract approval
- [x] C-G1 V4 productization delta + usage-first/context contract approval
- [x] C-G2 Quick/Research status and control projection approval
- [x] C-G3 strict production role-I/O v1, join, Evidence/Claim/Artifact contract approval
- [x] B/C implementation lanes and verification matrix drafted; Markdown-only V5-B gates are frozen and implemented. V5-C C-G1/C-G2/C-G3 are approved; implementation spans and acceptance are frozen in [`decision-2026-08-10-v5c-product-contract.md`](decision-2026-08-10-v5c-product-contract.md).

V5-C implementation status (2026-08-10): `C-API-WORKER`, `C-BOUNDARY` and Web usage projection are implemented in the canonical worktree. API `561 passed, 1 warning`, Worker `295 passed`, Web `130 passed`, production-start Research `5 passed`, online migration and R800 v6 `engineeringGate=pass`/`releaseGatePassed=true` are recorded in [`v5c-implementation-acceptance-2026-08-10.md`](v5c-implementation-acceptance-2026-08-10.md) and [`v5c-critical-review-20260810.md`](../../../docs/evals/v5c-critical-review-20260810.md). Independent Critical review is `ACCEPT`; F1 registry mapping and F5 historical-row bytes/hash remain Medium follow-up risks. No commit or push has been performed.

## V5-A Provider 与模型能力层

- [x] A001 盘点 generation、embedding、vision、ASR 的现有 provider 接口和调用点
- [x] A002 冻结 capability registry、provider profile 和非机密配置指纹边界（合同见 [`decision-2026-08-04-provider-capability-contract.md`](decision-2026-08-04-provider-capability-contract.md)；server-side registry/profile/fingerprint 已实现）
- [x] A003 接入第二套生成 provider/model，并补齐切换、超时、错误和配置漂移测试
- [x] A004 统一 Embedding provider 配置、维度/版本校验和重建索引提示
- [x] A005 为视觉理解和 ASR 增加 capability 校验与明确缺失能力错误
- [x] A006 在 Web 设置和 Research 运行信息中展示当前 profile/model
- [x] A007 回归 Quick Chat、Citation、NoteSource、Research 和旧保存语义

### A003 已交付子切片：DeepSeek generation

- 已实现 `DeepSeekGenerationProvider`，支持 Anthropic Messages API 的同步/流式文本生成、保留多模态消息 parts、明确错误码和 provider metrics。
- 已增加 `AI_PDF_GENERATION_PROVIDER=deepseek`、`AI_PDF_DEEPSEEK_API_KEY`、`AI_PDF_DEEPSEEK_API_BASE` 配置；当前 Run 仍保持一个 server-resolved provider/model 快照，不改变数据库或保存合同。
- 官方当前 Anthropic base 为 `https://api.deepseek.com/anthropic`，适配器统一请求 `/anthropic/v1/messages`；官方 `/models` 当前返回 `deepseek-v4-flash` 与 `deepseek-v4-pro`。
- 验证：API 全量 `431 passed, 4 skipped`；真实同步/流式调用已通过；DeepSeek Chat-shaped system/text/image 消息映射、unsupported 输入 fail-closed 和 capability drift 均有回归。以上属于接入与工程证据，不代表模型质量或用户价值通过。
- A003 完成；后续多 provider 的用户可见展示和跨层回归分别进入 A006/A007。


### A002 已交付子切片：capability registry/profile

- Fingerprint cutover: new revisions write v2; historical frozen fingerprints dual-read (legacy preimage or current v2) without rewrite; v2 still fail-closed on endpoint/secret/adapter/limit drift.
- Ingestion fingerprint fields are mandatory non-empty matches when present; worker image-caption validation mirrors the same rule.
- Research evidence.search real provider path fail-closes on execution fingerprint drift; injected test providers remain an explicit bypass.
- Secret marker pepper is `AI_PDF_CAPABILITY_FINGERPRINT_PEPPER` (API/Worker must match).

- 已实现 `services/capabilities.py`：generation/embedding/vision 的 typed profile、规范化 endpoint、非机密 config fingerprint、secret 单向 marker。
- ASR 在 registry 中明确为 unavailable，无隐式 fallback。
- `get_generation_provider` / `get_embedding_provider` / `get_image_caption_provider` 附带 `config_fingerprint` 与 capability profile 元数据。
- Research `provider_config_fingerprint` 现包含 generation/embedding profile fingerprint，并在存在 workspace top-k 时纳入 retrieval top-k；历史 terminal 字段语义不变。
- Ingestion job snapshot 增加 embedding/image-caption profile fingerprint，worker 校验失败时 fail-closed。
- 验证：API 全量 `431 passed, 4 skipped`，Worker 全量 `236 passed`，compileall 与 `git diff --check` 通过；独立复审 `ACCEPT`。`tests/test_capabilities.py` 覆盖 registry 元数据、endpoint 规范化、secret/endpoint/model/limit 漂移、无 raw secret 泄漏、ASR unavailable、provider factory attachment、ingestion snapshot 校验和 Research actual-profile drift。
### A004 已交付子切片：Embedding index contract

- 已实现 `services/embedding_index.py`：active embedding provider/model/dimensions/version/config_fingerprint 作为 index contract；fingerprint 解析 fail-closed，不写空值。
- retrieval 在 dense 检索前 fail-closed：scope 内仅有不匹配 current vectors 时返回稳定 `embedding_index_mismatch`（`ModelProviderError`）；无 ready asset / 无 current vectors 仍为空结果；matching 与 mismatch 共存时 matching wins。
- 当 ready Asset 的 latest successful ingest/reindex job snapshot 含 `embeddingProfileFingerprint` 时，要求与 active contract 一致；legacy 缺字段兼容；job 存在但 asset/workspace 越界时 fail-closed。
- Research `search_frozen_evidence` 将 `embedding_index_mismatch` 映射为 stable non-retryable `ResearchError(409)`，tool call `error_code` 保留 reindex 语义；Chat 仍走既有 provider/`ChatError` 内部码，不改 public HTTP detail shape（A007 residual）。
- reindex 继续是显式 operator action；job snapshot 通过 `embedding_index_job_snapshot_fields` 冻结 profile fields，不自动 rebuild/fallback，不改 DB schema/index_version/save 语义。
- 验证：`test_embedding_index_contract.py`、`test_research_worker_evidence_publication.py` mapping regression、policy non-retryable assertion + 既有 embedding/reindex focused tests；compileall 与 `git diff --check`；无 commit/push。
- 下一轮：Wave 3 A007。

### A005 已交付子切片：Vision + ASR capability fail-closed errors

- 新增 `services/capability_errors.py`：`require_configured_vision_profile`、`require_asr_capability`、`vision_readiness_status` / `asr_capability_status`。
- `get_image_caption_provider` 在构造 provider 前 fail-closed：缺失 vision 配置返回稳定 `image_caption_provider_not_configured`，不发起 provider HTTP；`OpenAIImageCaptionProvider.caption` 同样在 HTTP 前校验 key。
- ASR 仅通过 `capability_unavailable` 暴露，无 adapter、无 fallback；`main.capability_status()` 返回 informational `vision/asr` 状态，不改变 `/health/ready` 历史 body shape，也不因 ASR unavailable 硬失败。
- OpenAI/DeepSeek generation 与 embedding provider 及 readiness 对 `None`、空字符串、纯空白 key 统一 fail-closed，避免空白 secret 进入 HTTP。
- 保留 worker `image_caption_configuration_mismatch` 与 snapshot fingerprint 校验码；错误/状态面不暴露 key、endpoint 或 fingerprint preimage。
- 验证：API focused `76 passed`，Worker image `8 passed`，compileall 与 `git diff --check` 通过；Ruff 因环境缺失为 `not-run`；无 commit/push。

### A006 已交付子切片：Web frozen Research profile display

- Settings 保留当前 server-selected provider/model 展示，并明确标记为 live/current profile；不新增 selector。
- Research run detail 对 approved run 只展示 `researchExecution.execution.provider`，对未批准 proposed plan 只展示 `plan.inputSnapshot.proposedResearchExecution.provider`，并区分 run execution 与 proposed revision 来源标签。
- 已选 frozen source 结构不完整时直接显示 unavailable，不 fallback 到另一 frozen layer、`planningExecution` 或当前 Workspace profile。
- 未改 API、数据库、Research action/save 语义；Web focused `10 passed`、全量 `113 passed`，TypeScript、lint、production build、`git diff --check` 通过；独立复审 `ACCEPT`。
- Playwright Research spec 已补两种 source fixture/assertion；production-start 直接运行五个 Research 用例 `5 passed`，dev Turbopack file-watch limit 仅保留为开发环境 residual。

### A007 已交付子切片：Cross-layer regression

- 新增 API production-path regression：真实 `search_frozen_evidence` provider drift 在 factory/reservation 前返回 `research_provider_config_drift`；embedding mismatch 保留 Research `409`、tool error code 和 non-retryable 语义。
- 冻结 Chat 旧 public shape：embedding mismatch 穿过 `/chat/stream` 仍为 `502` + `{"detail": message}`，不引入 Research error envelope，不产生半保存消息。
- Embedding index 覆盖多个 successful index jobs 的 newest-wins、错误 Asset latest pointer、finalize ingest snapshot 与 active contract 全字段一致；修复旧 dense retrieval unit double 以显式提供 SQL scalar stub。
- Worker Image ingestion 覆盖非空 mismatched `imageCaptionProfileFingerprint` 在 representation/content unit 持久化前 fail-closed；不新增 ASR 假 adapter。
- Web Research fixture 对齐完整 Planning/Approved execution DTO；保留 proposed/execution/malformed frozen profile 断言。
- 验证：API 全量 `480 passed, 4 skipped`；Worker 全量 `238 passed`；Web 全量 `113 passed`；TypeScript、lint、production build、compileall、`git diff --check` 通过；production-start Research E2E `5 passed`；Ruff 因环境缺失为 `not-run`；独立 API/Worker 与 Web 复审 `ACCEPT`。
- A007 不改 API、数据库、migration、provider selector、Citation/NoteSource/Chat/Research save semantics；无 commit/push。

### V5-B Markdown v1 slice（2026-08-06）

- [x] B001 Markdown modality brief、locator/save-contract 和 verification matrix 冻结
- [x] B002 shared Asset/Evidence/retrieval/delete entry audit covered by registry, mixed workspace and production upload tests
- [x] B003 Markdown `document` adapter、normalized structure、typed `document_anchor` locator、retrieval and renderer implemented
- [x] B006 Markdown retrieval/Citation/NoteSource/Viewer path implemented without changing existing save columns
- [x] B007 Markdown mixed Workspace upload/processing/retry/delete/recovery integration suite and scoped restore oracle implemented
- [x] B008 formal isolated deployment gate: one project records built API/Worker/Web image IDs, dual-Document PostgreSQL/MinIO backup/restore oracles, live API/DOM replay and teardown/zero residue; accepted artifact is `docs/evals/artifacts/v5b-document-deployment-v4/` (v1 historical early pass, v2 Worker-health-predicate failure evidence, v3 interrupted partial evidence retained)
- [ ] HTML/Office/Audio/Video extensions remain outside this slice and require their own owner decisions/gates


- [x] B002 收口 PDF/Image 共用 Asset/Evidence、检索和 Viewer 入口
- [x] B003 接入 Markdown 文档类资料并实现结构化来源定位
- [ ] B004 设计并实现 Audio Representation、转写 ContentUnit、`audio_range` locator 和时间轴查看
- [ ] B005 设计并实现 Video Representation、字幕/关键帧 ContentUnit、时间或 frame locator 和查看
- [x] B006 为 Markdown 模态接入 retrieval channel、Chat target、Citation 和 NoteSource
- [x] B007 覆盖 PDF/Image/Document 混合 Workspace 的上传、处理、检索、引用、删除、重试和 scoped 恢复
- [x] B008 final independent Critical review and release closure；accepted `v4` report/raw manifests/logs 对 image binding、双资产 restore identity、browser replay 与 zero-residue cleanup 复核为 `ACCEPT`；scripted provider 仅作工程证据，不证明模型质量

## V5-C 多 Agent 协作产品化

- [x] C001 明确 Quick/Research 用户入口和运行状态模型
- [x] C002 冻结 Planner、Researcher、Verifier、Critic、Synthesizer 的 typed input/output
- [x] C003 将 provider capability/profile 快照接入每个 Research Run
- [x] C004 实现共享 Evidence bundle、Claim provenance 和分支 join 语义
- [x] C005 实现有界并行、单分支重试、取消、审批和恢复的 Web 状态
- [x] C006 展示 timeline、Evidence、冲突、失败原因和最终 Artifact
- [x] C007 验证所有 Agent 分支的 Workspace、预算、工具和 provider 权限边界
- [x] C008 保持 Quick Chat 独立并完成 Research/Chat 回归

## V5-D 端到端整合与工程稳定

- [x] D001 完成混合模态资产范围和统一检索入口
- [x] D002 完成多模型、多模态、多 Agent 的桌面/移动端主路径（D-G4 production-start mixed desktop/mobile）
- [x] D003 完成 API/Worker/Web 重启、删除、备份恢复和部署 profile（D-G5 partial-existing unit + D-G6 focused live；empty-target Compose residual）
- [x] D004 完成开发者文档、运行手册和故障诊断
- [x] D005 完成全链路静态、单元、集成和 Playwright 回归（D-G7 2026-08-12）

### V5-D implementation gates

- [x] D-G0 baseline/contract gate：记录源 SHA、dirty disposition、F1/F5、lane ownership 和 artifact 根目录（2026-08-11, artifact v5d-20260811-01）
- [x] D-G1 mixed asset/scope/retrieval：PDF/Image/Markdown 混合范围、当前代际、index、typed locator 和权限边界（focused API/Worker green 2026-08-11）
- [x] D-G2 Quick Chat/Citation/NoteSource：旧 SSE、public error、保存和历史 snapshot 语义回归（use-chat 7 passed after F1 rework 2026-08-11）
- [x] D-G3 Research integration：固定 executor、frozen snapshot、branch/retry/cancel/recovery 和 Artifact 回归（partial-existing-v5c production-start + unit suites retained for D-G7）
- [x] D-G4 desktop/mobile：production-start `1440x1000` 与 `390x844` Playwright、截图和 DOM/state evidence（live standalone 2 passed 2026-08-11）
- [x] D-G5 restart/delete/recovery：API/Worker/Web 重启、lease reclaim、delete retry、no-resurrection 和幂等（partial-existing-unit suites; no dedicated new mixed campaign in D-G7）
- [x] D-G6 live deployment/restore：mixed seed/snapshot/verify CLI + harness mixed-live-pass（focused 2026-08-11；full empty-target Compose restore optional residual）
- [x] D-G7 full regression/review：API 562 / Worker 296 / Web 131 + lint/tsc/build/compileall/diff-check；Critical `ACCEPT` with residuals（2026-08-12）

评审状态（2026-08-12）：[`docs/evals/v5d-critical-review-20260811.md`](../../../docs/evals/v5d-critical-review-20260811.md) 初始 `REWORK_REQUIRED`（F1/F2）已关闭；D-G4/D-G6 focused live 已通过；D-G7 全量回归 `ACCEPT` with residuals（API 562 / Worker 296 / Web 131）。产品仍为 `internal_preview`；R803/M404 后置；empty-target Compose restore 为 residual；未 commit/push。

详细字段、lane 和命令见 [`decision-2026-08-11-v5d-scope.md`](decision-2026-08-11-v5d-scope.md)、[`v5d-detailed-spec.md`](v5d-detailed-spec.md)、[`implementation-lanes-v5d.md`](implementation-lanes-v5d.md)、[`verification-matrix-v5d.md`](verification-matrix-v5d.md) 和 [`grok-handoff-v5d.md`](grok-handoff-v5d.md)。

## V5-E 模型质量与用户价值

- [ ] E001 重新规划 R803 或后续模型质量套件，按模态、任务和 provider/model 分层
- [ ] E002 保留历史 R803 artifact，不覆盖或续跑冻结的 v1 campaign
- [ ] E003 完成 M404 真实用户任务、重复使用和结论采用验证
- [ ] E004 根据功能、工程、模型质量和用户价值四类证据决定 Beta/公开发布
