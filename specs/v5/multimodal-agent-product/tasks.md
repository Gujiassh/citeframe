# V5 多模态 AI 知识工作台与 Agent 协作任务

## 状态

- [x] 完成 capability-first 方向裁决
- [x] 创建 V5 主规格、实施计划和任务清单
- [x] V5-A Provider 与模型能力层（A002-A007 已完成；A007 跨层回归已验收）
- [ ] V5-B 多模态资料扩展
- [ ] V5-C 多 Agent 协作产品化
- [ ] V5-D 端到端整合与工程稳定
- [ ] V5-E 模型质量与用户价值

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

## V5-B 多模态资料扩展

- [ ] B001 输出每种新模态的 modality brief 和用户任务边界
- [ ] B002 收口 PDF/Image 共用 Asset/Evidence、检索和 Viewer 入口
- [ ] B003 接入 Markdown/HTML 文档类资料并实现结构化来源定位
- [ ] B004 设计并实现 Audio Representation、转写 ContentUnit、`audio_range` locator 和时间轴查看
- [ ] B005 设计并实现 Video Representation、字幕/关键帧 ContentUnit、时间或 frame locator 和查看
- [ ] B006 为每种模态接入 retrieval channel、Chat target、Citation 和 NoteSource
- [ ] B007 覆盖混合 Workspace 的上传、处理、检索、引用、删除、重试和恢复
- [ ] B008 每种模态独立通过 registry、contract、adapter、geometry/locator 和权限复审后再启用

## V5-C 多 Agent 协作产品化

- [ ] C001 明确 Quick/Research 用户入口和运行状态模型
- [ ] C002 冻结 Planner、Researcher、Verifier、Critic、Synthesizer 的 typed input/output
- [ ] C003 将 provider capability/profile 快照接入每个 Research Run
- [ ] C004 实现共享 Evidence bundle、Claim provenance 和分支 join 语义
- [ ] C005 实现有界并行、单分支重试、取消、审批和恢复的 Web 状态
- [ ] C006 展示 timeline、Evidence、冲突、失败原因和最终 Artifact
- [ ] C007 验证所有 Agent 分支的 Workspace、预算、工具和 provider 权限边界
- [ ] C008 保持 Quick Chat 独立并完成 Research/Chat 回归

## V5-D 端到端整合与工程稳定

- [ ] D001 完成混合模态资产范围和统一检索入口
- [ ] D002 完成多模型、多模态、多 Agent 的桌面/移动端主路径
- [ ] D003 完成 API/Worker/Web 重启、删除、备份恢复和部署 profile
- [ ] D004 完成开发者文档、运行手册和故障诊断
- [ ] D005 完成全链路静态、单元、集成和 Playwright 回归

## V5-E 模型质量与用户价值

- [ ] E001 重新规划 R803 或后续模型质量套件，按模态、任务和 provider/model 分层
- [ ] E002 保留历史 R803 artifact，不覆盖或续跑冻结的 v1 campaign
- [ ] E003 完成 M404 真实用户任务、重复使用和结论采用验证
- [ ] E004 根据功能、工程、模型质量和用户价值四类证据决定 Beta/公开发布
