# V5-D 端到端整合与工程稳定详细规格

## 1. 文档状态

状态：`implementation-ready; contract-preserving`

本规格是 V5-D 的字段、边界、实现和退出条件。它依赖已接受的 V5-A、V5-B
Markdown-only `document` v1 和 V5-C；不得用高层 `plan.md` 替代本文件。

权威合同仍来自：

- `docs/architecture/modality-extension-contract.md`
- `docs/architecture/api-contracts.md`
- `docs/architecture/research-workflow-runtime.md`
- `specs/v5/multimodal-agent-product/save-contract-checklist.md`
- `specs/v5/multimodal-agent-product/decision-2026-08-11-v5d-scope.md`

## 2. 产品目标

用户在一个 Workspace 中可以：

1. 同时管理 PDF、Image 和 Markdown `document` 资产。
2. 用明确的 Asset scope 发起 Quick Chat 或 Research。
3. 从混合检索结果回到正确的 Citation、NoteSource 和 Evidence Viewer 位置。
4. 在桌面和移动端查看运行状态、证据、失败、审批、重试、取消和恢复。
5. 在 API、Worker、Web 重启和备份恢复后继续使用，不产生跨 Workspace 泄漏、历史来源漂移或已删除资产复活。

## 3. 用户路径和状态不变量

### 3.1 混合资产路径

`upload -> ingest ready -> mixed asset list -> explicit scope -> retrieve ->
citation/note -> viewer`

- 资产列表显示 registry 已启用的 PDF、Image、`document`，未知 kind 显示合同错误，不静默隐藏为其他 kind。
- Scope 只使用现有 DTO 和校验规则；不得以 UI 列表顺序推断语义。
- 检索候选必须通过 Workspace、scope、current generation、current index 和 typed locator 链条校验。
- Viewer 使用 locator kind/version 的专属 renderer；未知或 unavailable locator 显示不可用状态，不跳转到首个可用内容。

### 3.2 Quick Chat 路径

Quick Chat 继续使用现有 Chat API、SSE、消息保存和 public error shape。V5-D 只补齐混合 PDF/Image/Document 的入口和展示，不把 Research status、timeline 或 budget 字段写入 Chat message。

必须保持：

- `assetScope` 快照语义不变；
- Citation immutable snapshot 不变；
- NoteSource 是独立 locator snapshot；
- provider/index mismatch 不产生半保存消息；
- 失败消息的既有重试/继续语义不被 Research UI 分支覆盖。

### 3.3 Research 路径

Research 继续使用 V4 fixed executor 和 V5-C versioned Agent I/O。V5-D 补齐混合 Evidence 的入口、运行详情、Artifact 阅读和恢复体验，不新增 role、step kind、dynamic DAG 或 tool。

- Approved execution snapshot 是 provider/model、limits、retrievalTopK、scope、permissions 和 budget 的唯一 runtime truth。
- Web 只能展示现有 Research DTO 投影；不展示 money/billing 字段。
- `completed | failed | cancelled` 终态和现有 SSE/server-seq 语义不变。
- 历史 Run 使用显式 legacy registry；新 Run 不 fallback 到 legacy contract。

## 4. D001：混合模态资产范围与统一检索入口

### 交付

- 审计 Asset list/detail/upload、Chat scope、Research scope、retrieval、Citation、NoteSource 和 Viewer 的 registry 接入。
- 确认 PDF、Image、Markdown 的 kind/catalog/representation/content-unit/locator 链条在同一 Workspace 可并存。
- 为混合 PDF/Image/Document 增加或补齐 API/Worker/fixture 回归；复用现有 text embedding 和 lexical channel。
- 检查 reprocess/reindex/delete/delete-retry/no-resurrection 在混合范围内的语义。

### 禁止

- 不在 Workspace/Chat shell 增加 `if document`、`if image` 等业务分支。
- 不新建平行 `document_id`、citation 字段、scope 字段或新的 embedding space。
- 不通过 MIME、字段存在性、数组第一个元素或名称猜 kind/locator。

### D001 完成条件

- 混合 scope 的检索只返回 scope 内、当前代际、有效 locator 链条的候选。
- PDF/Image/Document 候选可分别回到正确 Viewer；引用和 NoteSource 的历史 snapshot 不变。
- 外部 Workspace asset、错误 kind、旧 generation、无效 index 和已删除 source 均按既有稳定错误/不可用语义处理。

## 5. D002：桌面/移动端主路径

### 交付

- 桌面（目标视口 `1440x1000`）和移动端（目标视口 `390x844`）完成以下主路径：
  - Workspace 资产列表和混合类型识别；
  - 选择 scope 并发起 Quick Chat；
  - 打开 Citation/NoteSource 的 PDF、Image、Document Evidence；
  - 发起 Research，查看计划/阶段/证据/Artifact；
  - 审批、修改、冲突处理、单分支重试、取消和恢复；
  - 错误、unavailable source 和 loading/empty 状态。
- 继续使用现有 EvidenceViewerShell、Research panel 和静态 Web registry；具体 renderer 负责具体模态。
- 所有固定格式控件使用稳定尺寸；移动端不得出现文字、按钮、viewer、drawer 互相遮挡或溢出。

### 禁止

- 不依赖 dev watcher 作为验收证据。
- 不添加解释性功能说明区或改变既有产品信息架构。
- 不把浏览器 runtime state 写入 API/数据库。

### D002 完成条件

- 生产启动 Web 通过 Playwright 桌面/移动关键路径，输出截图、DOM/state snapshot 和 server readiness 日志。
- Research 与 Quick Chat 的入口、状态和错误语义可区分；移动端可完成允许的控制操作。
- Viewer 在 PDF page/region、Image region、Document block/range 三种已启用 locator 上都能回到目标位置；unknown/unavailable 显示明确不可用。

## 6. D003：重启、删除、备份恢复和部署 profile

### 交付

- API 重启：已保存 Chat/Research 状态可读取；不产生重复消息、重复 Artifact 或错误的当前 profile fallback。
- Worker 重启：lease reclaim、branch retry、cancel reclaim 和 failed ingest/delete retry 遵守现有状态机。
- Web 重启：从 API 重新 hydrate，不依赖内存中的 scope、timeline 或 viewer state。
- 删除：源对象、当前派生链、embedding 和删除任务保持既有清理/幂等/no-resurrection 语义；历史 Citation/NoteSource 仍可显示 snapshot + `sourceAvailable=false`。
- 备份恢复：涉及当前 V5-B/C 表、Document typed rows、Research ledger 或对象时，使用真实 PostgreSQL/MinIO 隔离部署验证 row/object checksum。
- 部署 profile：记录 API/Worker/Web image、Alembic head、环境变量边界、health/readiness、启动命令和 zero-residue teardown。

### 禁止

- 不为“恢复更简单”修改 finished artifact bytes、Research status、generation、locator 或历史 DTO。
- 不用 SQLite-only 结果替代 live PostgreSQL/MinIO 证据。
- 不把 Worker `health=null` 等既有合法运行状态误判为服务失败；以当前 accepted runner 规则为准。

### D003 完成条件

- 重启/lease/recovery/delete/retry/restore 每项都有可重放的测试或 live artifact。
- 恢复前后业务语义 hash、对象 SHA-256、关键 API/DOM 证据一致；容器、卷、网络和临时资源 zero residue。
- 任何不可恢复状态都有稳定错误码、责任边界和 runbook 操作。

## 7. D004：开发者文档、运行手册和诊断

### 交付

- 更新 `docs/architecture/implementation-progress.md`、V5 spec 索引和 V5-D acceptance record。
- 新增运行手册：本地启动、production-start Web、隔离 PostgreSQL/MinIO、backup/restore、常见 readiness/worker/research/document 错误。
- 新增诊断表：平面 grep-friendly 日志 tag、关联 ID、责任服务、可重试性、用户动作和证据路径。
- 文档必须区分 engineering gate、model-quality gate 和 user-value gate；不得把 R800 绿色写成模型质量通过。

### D004 完成条件

- 新会话可只读 V5 README、D 规格、lane、验收矩阵和 runbook 后启动验证。
- 所有新增相对链接存在；命令、端口、server entry、artifact 路径与仓库现状一致。
- 运行手册明确哪些失败必须停工上报，而不是添加 fallback。

## 8. D005：全链路回归与发布判断

D005 是集成控制器的收口，不是单个功能 agent 的私有任务。它必须运行 V5-D 矩阵中的 API、Worker、Web、production-start、live restore 和 Critical review，并生成一份带命令、exit code、测试数量、artifact、审查结论和 residual risk 的 acceptance record。

### D005 完成条件

- 所有现有 V5-A/B/C 合同回归通过；测试数量相对同一基线无未解释下降。
- 混合 Workspace、Quick Chat、Citation/NoteSource、Research、权限、删除、重启和恢复均有正/负路径证据。
- 桌面/移动 Playwright、live PostgreSQL/MinIO、backup/restore、zero-residue 和 docs/link check 完成。
- 独立 Standard/Critical review 按矩阵逐项标记 `pass`、`not applicable` 或 `blocked`。
- 只可宣布 `internal-preview engineering gate`；不得宣布 R803/M404 或模型质量通过。

## 9. 变更停止规则

以下任一变化必须停止当前 lane，提交影响说明并等待 main controller/owner 决策：

- 新增/删除/重命名数据库表列、catalog literal、enum meaning 或迁移；
- 改变 Asset generation/status/delete/retry/restore、Citation、NoteSource、Chat SSE、Research ledger 或 finished artifact bytes；
- 新增 provider selector、model selector、dynamic Agent step/tool、locator kind/version 或 cost/permission 字段；
- 改变公开 HTTP/SSE error shape、scope precedence、历史 source availability 或 backup format；
- 需要 compatibility layer、fallback chain、静默 coercion 或双写。

允许继续的范围是：既有 DTO 的展示、既有 registry 的组合、测试/fixture/runbook/diagnostic 增补，以及不改变持久化意义的 renderer/layout 修正。
