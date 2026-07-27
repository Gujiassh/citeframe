# V3 PDF + Image 目标架构

## 1. 状态与边界

- 状态：Approved；Phase 1-2 与 Phase 3 M301-M305 已完成并通过最终 Critical 复审
- V3 注册 Asset 类型：`pdf`、`image`；M403B 后两者均已启用生产摄取
- V3 启用 Locator 类型：`pdf_page`、`pdf_region`、`image_region`
- 扩展目标：后续 Audio/Video/文本办公文件/结构化记录通过注册模块与类型化 locator 接入
- 不包含：V3 音视频产品功能、Omnilabel 业务模型、通用任意 JSON locator

本设计已经替代 Document-only 运行时。当前生产代码使用 `assets / asset_representations / pdf_pages / content_units / evidence_locators / message_citations / note_sources`，旧 `/documents` 与 Document 业务模型已移除。

## 2. 目标职责

### Asset

拥有 Workspace 归属、类型、源对象身份、文件元数据、生命周期和当前处理代际。PDF 与图片共享 Asset 生命周期，但不共享具体解析规则。

### Representation

记录不可变且可版本化的派生表示：PDF layout/OCR、图片 OCR/caption/region analysis。一次处理的多个 Representation 共享 `processingGeneration`；Parser 或模型变化创建新 generation，不原位改写历史表示。

### ContentUnit

检索和回答使用的可寻址单元。公共字段只保存资产、representation、unit kind、文本和顺序；PDF 页/区域和图片区域几何进入类型化子表。

### Embedding

ContentUnit 的可重建投影，独立记录 provider、model、dimensions、version 和 vector。文本、caption 和视觉向量不强行共用一个空间。

### EvidenceLocator

回答生成时冻结的源定位值。数据库使用 locator kind/version 与类型化子表，不使用任意 JSONB 作为唯一真相源。

### Citation / NoteSource

Citation 冻结 asset、locator、标题、excerpt、representation/parser/index 版本与消息内编号。NoteSource 从 Citation 复制完整快照，保持源删除和重处理后的历史语义。

### ModalityModule

每个启用模态提供 MIME/字节验证、Worker adapter、Representation/ContentUnit 类型、locator codec、检索通道、清理策略和 Web renderer。稳定内核只通过注册表调度，不判断 PDF 页码、图片 bbox、音频时间段或视频帧。

## 3. 目标数据结构

建议目标表：

```text
assets
asset_types
asset_representations
representation_types
pdf_pages
content_units
content_unit_types
content_unit_embeddings
embedding_spaces
asset_tags
ingestion_jobs

evidence_locators
locator_types
pdf_locator_details
image_locator_details
spatial_locator_regions

message_retrieval_scopes
message_retrieval_scope_assets

message_citations

note_sources
```

关键约束：

- `assets.asset_kind` 引用部署期启用的 `asset_types`；V3 目录只启用 `pdf | image`。
- 代码 ModalityRegistry 与数据库启用目录不一致时 readiness 失败。
- PDF 才能拥有 `pdf_pages` 和 PDF region；图片不能伪造 page 1。
- 所有 region 使用类型对应的明确 coordinate space，并约束在 `0..1`。
- 同一 locator 的多区域必须属于同一 PDF 页或同一图片，按 `region_order` 排序。
- ContentUnit、EvidenceLocator、Citation 和 NoteSource 的 Workspace 必须与 Asset 一致。
- Embedding 可删除重建；Citation/NoteSource 快照不能随重建改写。
- 每条用户消息的 retrieval scope 保存 `all_ready | selected` 模式和解析后的 Asset 快照；后续上传或删除不能改变历史问题的范围语义。

## 4. Locator 联合类型

### `pdf_page`

```json
{
  "kind": "pdf_page",
  "version": 1,
  "pageNumber": 8
}
```

### `pdf_region`

```json
{
  "kind": "pdf_region",
  "version": 1,
  "pageNumber": 8,
  "coordinateSpace": "pdf_crop_box_normalized_top_left_v1",
  "pageGeometry": {
    "cropBoxPoints": [0, 0, 612, 792],
    "rotationDegrees": 0,
    "displayWidthPoints": 612,
    "displayHeightPoints": 792
  },
  "regions": [
    { "x": 0.12, "y": 0.31, "width": 0.48, "height": 0.08 }
  ]
}
```

### `image_region`

```json
{
  "kind": "image_region",
  "version": 1,
  "coordinateSpace": "image_normalized_top_left_v1",
  "widthPixels": 2400,
  "heightPixels": 1600,
  "orientationApplied": true,
  "regions": [
    { "x": 0.18, "y": 0.2, "width": 0.42, "height": 0.3 }
  ]
}
```

整图证据使用覆盖全图的 `image_region`，不引入没有实际定位语义的 `pageNumber=1`。图片 EXIF orientation 在生成 representation 时应用，locator 针对已定向显示空间冻结几何快照。locator 与 `sourceVersions.representationId` 指向实际支持结论的 `image_ocr` 或 `image_caption` Evidence Representation；Viewer 按冻结的 `processingGeneration` 精确选择同代 `image_oriented` 作为显示对象。

## 5. 处理管线

```text
upload
  -> MIME/bytes validation
  -> source Asset + source Representation
  -> modality adapter
     -> PDF: page geometry, native text, OCR, layout, table/figure regions
     -> Image: orientation, dimensions, OCR, caption, detected regions
  -> ContentUnits
  -> text/caption embeddings
  -> optional visual embeddings after a measured retrieval gap
  -> ready
```

PDF 和图片 adapter 只能产出标准 Asset/Representation/ContentUnit/locator 输入及 generated object manifest，不能把具体模态分支堆进 ingestion 或 Chat orchestrator。共享 orchestrator 统一上传/回收 manifest 对象；后续模态遵守同一协议，Chat 只消费统一 EvidenceCandidate 和类型化 Evidence。

## 6. 检索与回答

- 请求使用 `{ mode: "all_ready" } | { mode: "selected", assetIds: [...] }` 的 discriminated `assetScope`。
- API 在检索前验证 Workspace/ready 状态，将 `all_ready` 解析为当时的明确 Asset 集合，并把模式与实际 Asset 快照保存到本次用户消息。
- lexical 与文本 Dense 覆盖 PDF 文本、OCR、表格文本、图片 OCR/caption。
- 元数据过滤先于候选融合，不能检索后再隐藏未选资产。
- 不同向量空间分别召回，再用有界 RRF/融合；不因“多模态”默认引入统一向量或 reranker。
- 聚合、计数和分布问题不由少量召回样本推断。

## 7. API 目标面

正式版本应以 Asset 资源组织：

```text
GET    /workspaces/:workspaceId/assets
POST   /workspaces/:workspaceId/assets/upload-session
POST   /workspaces/:workspaceId/assets/:assetId/finalize-upload
GET    /workspaces/:workspaceId/assets/:assetId
GET    /workspaces/:workspaceId/assets/:assetId/file
DELETE /workspaces/:workspaceId/assets/:assetId
POST   /workspaces/:workspaceId/assets/:assetId/retry
```

Chat 请求已使用 discriminated `assetScope`；Citation 和 NoteSource 已使用 discriminated locator union。以上破坏性 API/保存合同变更已在 Phase 1 通过一次受控切换落地，并由历史 payload 与迁移恢复 oracle 验证。

## 8. 迁移原则

- 当前每个 Document 机械迁移为 `asset_kind=pdf` 的 Asset，不根据文件名或 MIME fallback 猜类型。
- `document_pages` 迁移为 PDF page；`document_chunks` 迁移为文本 ContentUnit 与 embedding。
- 旧 Citation/NoteSource 只能机械映射成 `pdf_page`，不得从当前 chunk/OCR 猜历史区域。
- Document tag 关系迁移为 Asset tag 关系；标签语义不变。
- 新 API、Web 类型和 Worker adapter 在一次受控版本切换中落地，不保留无期限双模型业务层。
- 迁移前后必须比较 Workspace、资产数、页数、chunk/unit 数、历史 citation、note source、标签、对象 SHA-256 和备份恢复结果。

## 9. 审批与实施状态

用户已经确认：V3 首个范围为多模态 PDF + 独立图片，Audio/Video 不进入。

以下六项已批准：

1. 是否接受从 Document 领域迁移到 Asset/Representation/ContentUnit/Embedding 目标结构。
2. 是否接受 `pdf_page/pdf_region/image_region` 及两个 normalized top-left 坐标定义。
3. 是否接受多区域限制为同一页或同一图片、有序、联合支持语义。
4. 是否接受统一 immutable locator 头、模态类型化扩展表和封闭注册协议，不采用通用 JSONB。
5. 是否接受 Chat `assetScope`、消息范围快照与 Asset/Citation/NoteSource 新 API 版本的一次受控切换。
6. 是否接受旧 citation 只机械迁移为 `pdf_page`，以及源删除后只保留快照、不再打开 Viewer。

Phase 1 已完成 Asset/Evidence 内核、PDF 运行时、Chat 范围、Citation/NoteSource 和 Evidence Viewer 切换。M301-M304 已完成 Image 格式与方向归一化、OCR/caption、区域 ContentUnit、text embedding、Citation/NoteSource 与消息输入 Evidence 历史快照、图片框选 Chat/Note 和 Viewer。M305 已实现注册表驱动的 PDF/Image text channel、模态无关候选、有界 RRF、limit 前唯一 locator 补足、批量 fail-closed Evidence 校验与 SQL 前置 Asset scope/current generation/current index/链条一致性过滤；混合 Chat/Citation、PostgreSQL oracle 和最终 Critical 复审均通过。M403B 已把 `asset_types.image.enabled`、上传入口和生产 Worker 摄取同步启用，且未改变 Citation、NoteSource、Chat 或保存语义。
