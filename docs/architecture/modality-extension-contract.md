# 模态扩展协议

## 0. Onboarding checklist

Adding a modality: follow [`modality-onboarding-checklist.md`](modality-onboarding-checklist.md) (architecture hardening). Shared Chat/retrieval must stay free of kind-specific business branches.

## 1. 目标

V3 只交付多模态 PDF 与独立图片，但核心架构必须允许后续加入音频、视频、Markdown/HTML/Office 和结构化记录，而不再次重做 Workspace、Asset、Chat、Citation、NoteSource、检索融合或 Evidence Viewer 外壳。

“可扩展”不表示运行时接受任意类型或任意 JSON。每个应用版本仍有一个封闭、可验证的模态注册表；新增模态需要代码模块、类型化合同、数据库迁移、fixture 和验收，只是不修改现有核心职责与历史数据。

## 2. 稳定内核

以下核心结构在 PDF/Image 迁移后保持模态无关：

- `assets`：源资产身份、Workspace、生命周期和当前处理代际
- `asset_representations`：不可变派生表示
- `content_units`：检索和分析单元
- `content_unit_embeddings`：可重建索引投影
- `message_retrieval_scopes`：问题范围模式与实际 Asset 快照
- `evidence_locators`：不可变 locator 公共头
- `message_citations`：消息内编号、Asset/展示/版本快照与 locator 关联
- `note_sources`：独立复制的 Asset/展示/版本快照与 locator 关联
- Asset API、Chat `assetScope`、Citation/NoteSource DTO envelope
- Chat 检索、融合、回答、历史回放和 citation -> note 主链
- Web Asset list、Chat scope 和 Evidence Viewer shell

新增模态不得给这些模块增加具体业务分支。共享层只按注册协议调度模块，并对未知或未启用的 kind 抛出明确错误。

## 3. 部署期模态注册表

后端在应用启动时构建封闭的 `ModalityRegistry`。V3 只注册 `pdf` 和 `image`：

```text
ModalityModule
├─ assetKind
├─ supportedMimeTypes
├─ byteInspector
├─ ingestionAdapter
├─ ingestionConfigSnapshot
├─ representationKinds
├─ contentUnitKinds
├─ locatorCodecs
├─ retrievalChannels
├─ cleanupPolicy
└─ metricsNamespace
```

`byteInspector` 返回从头部实际识别出的 canonical MIME 或空值，Registry 再与声明 MIME 比较。一个模块拥有多个 MIME 时不能只返回“属于这个 Asset kind”；例如 PNG bytes 声明为 JPEG 必须在同步上传阶段 fail closed，完整解码仍由 Worker 二次验证。

数据库使用引用目录而不是封闭 enum：

```text
asset_types(kind, contract_version, enabled)
representation_types(asset_kind, kind, contract_version)
content_unit_types(asset_kind, kind, contract_version)
locator_types(kind, contract_version)
```

应用启动时必须验证代码注册表与数据库启用目录完全一致；缺少模块、未知启用类型或 contract version 不一致都使 readiness 失败。数据库行不能自行启用一个没有代码模块的模态。

这不是热插拔插件系统。新增模态仍随一个经过测试的应用版本部署，只是不修改稳定内核表或主链。

## 4. Worker 扩展协议

Worker 根据已验证的 `asset_kind` 从注册表取得 adapter。Adapter 输入和输出保持稳定：

```text
input
  asset identity
  source Representation
  processing generation
  Workspace processing settings

output
  immutable Representations
  typed ContentUnits
  typed source locators
  text/visual/audio embedding requests
  generated object manifest
```

Adapter 只负责具体模态解析：

- PDF：页面几何、文本、OCR、layout、表格、图表和页内图片
- Image：方向归一化、OCR、caption 和区域
- Audio（后续）：ASR、说话人、时间片段
- Video（后续）：镜头、关键帧、字幕、ASR 和时间片段
- Structured record（后续）：记录 ID、字段路径和结构化值

Ingestion orchestrator 只负责 job claim、状态流转、事务边界、generation 激活、失败记录和清理，不理解页面、bbox、时间段或字段路径。

Adapter 的 generated object manifest 包含 representation namespace 内的对象键、bytes、Content-Type 和 SHA-256。共享 orchestrator 校验 manifest 后负责上传；上传后的 embedding 或数据库 commit 失败时按已上传键回收，Asset 删除时幂等删除源对象与所有非空 Representation object key。Adapter 不直接改写源对象，也不自行决定事务提交。

M301-M304 已用 Image adapter、共享 Evidence 主链、evidence-target resolver 和独立 renderer 验证 ingestion、locator、Citation/NoteSource、消息输入 Evidence 与 Web 区域闭环。M305 进一步将共享候选收敛为模态无关结构，由注册表声明精确的 text channel 类型签名，并在 Dense/lexical 排序前应用 scope/current generation/current index/链条一致性约束；limit 按唯一 locator 位置补足，typed detail/regions 使用批量 fail-closed 校验。SQLite、PostgreSQL 混合 oracle 和最终 Critical 复审均通过。M403B 已把 PNG/JPEG/WebP Image adapter、类型目录、caption 配置和上传入口同步启用并通过真实 Worker、浏览器与备份恢复门禁。

## 5. Locator 扩展协议

所有 locator 共享不可变公共头：

```text
evidence_locators
  id, workspace_id, asset_id
  locator_kind, locator_version
  processing_generation_snapshot
  representation_id_snapshot
  created_at
```

具体定位值放入类型化扩展表：

```text
PDF/Image V3
  pdf_locator_details
  image_locator_details
  spatial_locator_regions

Future
  audio_locator_details
  video_locator_details
  temporal_locator_ranges
  record_path_locator_details
```

Citation、NoteSource 和 ContentUnit 都只关联 `evidence_locator_id`。创建 NoteSource 时复制一个新的 immutable locator snapshot 及其类型化明细，不依赖 Citation 或当前 ContentUnit 才能解释来源。

新增 locator kind 只增加 codec 与类型化扩展表，不给 `message_citations`、`note_sources` 或 Chat SSE 增加新列。未知 kind 不能猜测成整页、整图或纯文本。

## 6. 检索扩展协议

每个模块可以注册一个或多个 retrieval channel，但输出统一为：

```text
EvidenceCandidate
  workspaceId
  assetId
  contentUnitId
  evidenceLocatorId
  channel
  score
  contextText
  sourceVersions
```

核心 retrieval service 负责：

1. 在检索前应用 Workspace 与 `assetScope`。
2. 调度当前启用模态的 channel。
3. 在 channel 内归一化排序，在 channel 间执行有界融合。
4. 去重并返回 EvidenceCandidate。

Chat orchestrator 不读取 PDF 页码、图片 bbox、音频时间或视频帧。它只使用候选上下文和可序列化 Evidence locator。

## 7. API 扩展协议

以下 envelope 保持稳定：

- `AssetSummary` 的公共字段和 `kind`
- Chat request 的 discriminated `assetScope`
- Citation/NoteSource 的 Asset snapshot、excerpt、sourceVersions 和 `locator`
- `/workspaces/:workspaceId/assets/*` 生命周期 endpoint

每个模态模块贡献：

- Asset detail schema
- locator schema/serializer/parser
- 处理状态的模态专用 detail（如有）

OpenAPI 在构建时从封闭注册表组装 discriminated locator union。新增模态会扩充 union，但不替换 envelope 或 endpoint。未知 kind 返回合同错误，不静默忽略 payload。

## 8. Web 扩展协议

前端使用静态构建期注册表，不在 `WorkspacePage`、`WorkspaceContext`、Chat 或 Viewer shell 中按模态分支：

```text
EvidenceModule
├─ assetKind
├─ assetDetailParser
├─ locatorParsers
├─ icon
├─ label
├─ uploadAccept
├─ EvidenceRenderer
└─ optional SelectionTool
```

`EvidenceViewerShell` 负责标题、来源可用性、宽度、全屏、关闭、错误边界和响应式行为。Renderer 只负责具体媒体：

- PDF renderer：页码、目录、文本/OCR 层、region overlay
- Image renderer：缩放、平移、region overlay
- Audio renderer（后续）：波形、播放、时间段高亮
- Video renderer（后续）：播放、时间轴、关键帧/片段高亮
- Record renderer（后续）：记录与字段路径聚焦

新增模块只向注册表增加一个明确 import/entry。共享 shell 不通过 MIME、字段存在性或名称猜 renderer。

## 9. 新模态接入门禁

每个新模态必须提供：

1. `asset_types`、Representation/ContentUnit/locator type 注册与版本。
2. MIME 与实际字节验证。
3. Worker adapter、生成对象 manifest 和删除/重处理语义。
4. 类型化 locator 表、API codec 和当前/候选 fixture。
5. 至少一个 retrieval channel 与分层黄金集。
6. Web renderer、选择工具（如需要）和响应式交互。
7. Citation/NoteSource 历史、源删除和恢复测试。
8. 备份 format、指标、成本与安全边界评审。

接入新模态允许新增模块和类型化表；不允许修改已有 locator 含义、重写历史数据、给共享模型加任意 JSON payload，或把具体模态逻辑堆入 Chat/Workspace shell。

## 10. V3 实施边界

V3 必须把上述稳定内核和注册协议实现到能真实承载 PDF 与图片。Audio、Video 和结构化记录只保留契约测试用的未注册示例，不创建上传入口、DB 启用行、Worker adapter 或 Viewer renderer。

因此，V3 不承诺全模态功能，但完成后新增模态是“加模块 + 加类型化表 + 加测试”，不是再次迁移 Asset/Citation/NoteSource 或重做页面主结构。
