# V3 PDF + Image 数据与 API Contract v1

> 文档状态：V3 历史 Contract Draft，已批准并完成实施。当前运行时事实以 `docs/architecture/api-contracts.md`、`docs/architecture/database-design.md`、`docs/ssot/system-architecture.md` 和 `specs/v3/multimodal-workspace/` 为准；本文保留字段级迁移推导，不应把旧的“待进入 Phase 3”描述当作当前状态。

## 1. 状态

- 状态：Approved；六项裁决已于 2026-07-17 明确批准
- 当前影响：Phase 1-3 ORM、类型目录、模态注册表、migration、router、SSE 与 Web 已完成受控切换；M403B 已同步启用 PNG/JPEG/WebP Image 生产目录、Worker adapter、caption 配置和上传入口
- 切换方式：同一仓库中的 Web/BFF/API/Worker 一次受控切换，不长期维护 `/documents` 与 `/assets` 两套业务接口

## 2. 目标数据库职责

以下是字段级目标，不是已执行 DDL。所有 ID 使用当前 UUID string 约定，所有业务主表带 `workspace_id`。类型目录由 migration 写入，代码注册表必须与启用目录一致；目录行不能自行提供解析能力。

### 类型目录

```text
asset_types(kind, contract_version, enabled)
representation_types(asset_kind, kind, contract_version)
content_unit_types(asset_kind, kind, contract_version)
locator_types(kind, contract_version, detail_family)
embedding_spaces(kind, contract_version)
```

V3 只启用 `pdf`、`image` 及其 Representation/ContentUnit/locator；后续模态通过新增目录行、代码模块和类型化明细表接入，不修改稳定核心表。应用 readiness 验证启用目录与后端注册表完全一致。

### `assets`

```text
id, workspace_id, created_by_user_id
asset_kind -> asset_types.kind
title, source_filename, object_key, mime_type, byte_size, source_sha256
status, current_processing_generation, current_index_version
latest_ingestion_job_id, last_error_code, last_error_message
deleted_at, created_at, updated_at
```

Asset 软删除保留身份与历史关联，只删除源对象和可重建派生物。V3 仅注册 `pdf | image`。`asset_kind` 由 upload-session 调用已注册模块的 MIME 与实际字节校验共同确定，不能由文件扩展名或 UI 传值单独决定。

### `asset_representations`

```text
id, workspace_id, asset_id
representation_kind -> representation_types.kind
processing_generation
generator_provider, generator_model, generator_version
object_key, content_sha256, created_at
```

Representation 不可变。一次处理产生的 layout/OCR/caption 等 Representation 共享 `processing_generation`；重处理创建新 generation，`assets.current_processing_generation` 只指向当前完整处理代际。

### `pdf_pages`

```text
id, workspace_id, asset_id, representation_id, page_number
media_x0_points, media_y0_points, media_x1_points, media_y1_points
crop_x0_points, crop_y0_points, crop_x1_points, crop_y1_points
rotation_degrees, display_width_points, display_height_points
extracted_text, char_count, created_at
```

约束：`(asset_id, representation_id, page_number)` 唯一；只有 PDF Asset 可以关联。

### `image_representation_geometry`

```text
representation_id, workspace_id, asset_id
width_pixels, height_pixels, orientation_applied
```

约束：只有 Image Asset 的 `image_oriented` Representation 可以关联。

### `content_units`

```text
id, workspace_id, asset_id, representation_id, source_locator_id
unit_kind -> content_unit_types.kind
unit_order, text_content, token_count, index_version, created_at
```

ContentUnit 只保存公共检索文本与顺序，并通过 `source_locator_id` 关联不可变定位值。页码、区域、时间段和记录路径不放入任意 JSON。

### `evidence_locators`

```text
id, workspace_id, asset_id
locator_kind -> locator_types.kind
locator_version
processing_generation_snapshot, representation_id_snapshot
created_at
```

ContentUnit、Citation 和 NoteSource 都关联该公共 locator 头。Citation 生成时复制候选 locator，NoteSource 生成时再复制 Citation locator，三者不共享一个会被级联删除的 owner row。

### V3 locator 明细

```text
pdf_locator_details(
  locator_id, page_id?, page_number,
  coordinate_space?, crop/display/rotation geometry snapshot?
)
image_locator_details(
  locator_id, coordinate_space,
  width_pixels, height_pixels, orientation_applied
)
spatial_locator_regions(locator_id, region_order, x, y, width, height)
```

`pdf_page` 使用 `pdf_locator_details` 且没有 region；`pdf_region` 和 `image_region` 必须有 region。所有 region 坐标约束在 `0..1` 且 `x + width <= 1`、`y + height <= 1`。整图使用 `[0,0,1,1]`。

### 后续 locator 明细

```text
audio_locator_details(locator_id, duration_ms, timeline_version)
video_locator_details(locator_id, duration_ms, timeline_version, frame_rate_snapshot)
temporal_locator_ranges(locator_id, range_order, start_ms, end_ms, frame_number?)
record_path_locator_details(locator_id, record_id_snapshot, field_path)
```

这些未来表不在 V3 migration 中创建。新增模态时增加明细表和 locator codec，不修改 `evidence_locators`、`message_citations` 或 `note_sources`。

### `content_unit_embeddings`

```text
id, workspace_id, content_unit_id
embedding_space -> embedding_spaces.kind
provider, model, dimensions, version, embedding, created_at
```

同一个 ContentUnit 可有多个空间和版本。V3 第一实现只启用 text；visual 必须由检索实验单独批准，后续 audio 等空间通过目录与 retrieval channel 注册。

### `message_retrieval_scopes`

```text
message_id, workspace_id
scope_mode: all_ready | selected
created_at
```

### `message_retrieval_scope_assets`

```text
message_id, asset_id, asset_order
asset_kind_snapshot, asset_title_snapshot
```

API 在创建用户消息时把 `all_ready` 解析为当时全部 ready Asset，并保存实际集合。历史问题的范围不会因后续上传、删除或重新选择而改变。

### Citation locator

`message_citations` 保留消息、Workspace、编号和展示/版本快照，资源关联改为 Asset：

```text
id, workspace_id, message_id, citation_index, evidence_locator_id
asset_id, asset_kind_snapshot, asset_title_snapshot, excerpt_snapshot
processing_generation_snapshot, representation_id_snapshot, parser_version_snapshot, index_version_snapshot
created_at
```

Citation DTO 从关联的 immutable `evidence_locator` 与类型化明细序列化 discriminated locator。新增模态不会给 `message_citations` 增加列。

### NoteSource locator

`note_sources` 独立复制 Citation 快照：

```text
id, workspace_id, note_id, source_order, message_citation_id, evidence_locator_id
asset_id, asset_kind_snapshot, asset_title_snapshot, excerpt_snapshot
processing_generation_snapshot, representation_id_snapshot, parser_version_snapshot, index_version_snapshot
created_at
```

NoteSource 的 `evidence_locator_id` 指向创建 Note 时复制出的独立 locator row。新增模态不会给 `note_sources` 增加列。

## 3. 目标 API DTO

### Asset summary

```json
{
  "id": "asset_xxx",
  "workspaceId": "ws_xxx",
  "kind": "image",
  "title": "latency-chart.png",
  "sourceFilename": "latency-chart.png",
  "mimeType": "image/png",
  "byteSize": 428312,
  "status": "ready",
  "currentProcessingGeneration": 1,
  "currentIndexVersion": 1,
  "lastErrorCode": null,
  "lastErrorMessage": null,
  "createdAt": "2026-07-17T00:00:00Z",
  "updatedAt": "2026-07-17T00:00:00Z"
}
```

Asset detail 使用稳定 envelope 与构建期 discriminated `detail` union。PDF detail 返回页列表与页面几何；图片 detail 返回方向归一化后的 geometry。新增模态只扩充 union 变体，不替换 endpoint 或公共 Asset 字段。客户端根据 `kind` 调度已注册 parser，不使用可选字段组合猜模态。

### Chat request

```json
{
  "threadId": "thread_xxx",
  "question": "Compare these two sources.",
  "assetScope": {
    "mode": "selected",
    "assetIds": ["asset_pdf", "asset_image"]
  }
}
```

`all_ready` 形式不接受 `assetIds`；`selected` 形式至少一个且不得重复。API 在任何检索/模型调用前完成 membership、Workspace、ready 和删除状态校验。

### Citation

```json
{
  "id": "cit_xxx",
  "messageId": "msg_xxx",
  "citationIndex": 0,
  "assetId": "asset_image",
  "assetKind": "image",
  "assetTitle": "latency-chart.png",
  "sourceAvailable": true,
  "excerpt": "Release 4 begins the sustained drop.",
  "locator": {
    "kind": "image_region",
    "version": 1,
    "coordinateSpace": "image_normalized_top_left_v1",
    "widthPixels": 1200,
    "heightPixels": 800,
    "orientationApplied": true,
    "regions": [
      {"x": 0.683333, "y": 0.275, "width": 0.25, "height": 0.375}
    ]
  },
  "sourceVersions": {
    "parserVersion": "image-parser-v1",
    "processingGeneration": 1,
    "representationId": "rep_image_caption_v1",
    "indexVersion": 1
  }
}
```

NoteSource 使用同一 Asset snapshot、locator 和 sourceVersions envelope，并增加 `messageCitationId` 与 `createdAt`。新增 locator kind 只扩充 discriminated locator union，不改变 Citation/NoteSource envelope 或 Chat SSE 事件名。

## 4. Endpoint 切换

目标资源路径：

```text
GET    /workspaces/:workspaceId/assets
POST   /workspaces/:workspaceId/assets/upload-session
POST   /workspaces/:workspaceId/assets/:assetId/finalize-upload
GET    /workspaces/:workspaceId/assets/:assetId
GET    /workspaces/:workspaceId/assets/:assetId/file
DELETE /workspaces/:workspaceId/assets/:assetId
POST   /workspaces/:workspaceId/assets/:assetId/retry
POST   /workspaces/:workspaceId/assets/:assetId/delete-retry
```

切换版本同时：

- Web/BFF 改用 `/assets`。
- API 删除 `/documents` router 注册，不保留代理或字段 fallback。
- Chat SSE `citations` 事件、历史 Message、NoteSource 和 Tag binding 切换到 Asset DTO。
- `document_tags` 迁移为 `asset_tags`，endpoint 切换到 `/assets/:assetId/tags`。
- 当前 Web 与 API 同版本部署，Caddy 在停写和 migration gate 后放行。

## 5. 旧数据机械映射

| 当前字段/表 | 目标 | 规则 |
| --- | --- | --- |
| `documents` | `assets` | 每条固定映射为 `asset_kind=pdf` |
| `document_pages` | `pdf_pages + legacy pdf_ocr Representation` | 页码、文本和 OCR blocks 原样迁移到 generation 1；OCR block JSON 仅作为 legacy artifact，不自动成为新 locator |
| `document_chunks` | `content_units + embeddings` | 文本、顺序、字符范围来源和版本保持 |
| `document_tags` | `asset_tags` | Asset ID 使用对应 Document 映射，不改标签 |
| `message_citations` | Asset citation + `pdf_page` | 只使用 `page_number_snapshot`，不推断 region |
| `note_sources` | Asset NoteSource + `pdf_page` | 使用自身快照，不重新读取 Citation |

当前 OCR block 的 JSON 必须原样保留在不可变 legacy OCR artifact 中，但不直接成为新 locator 真相。只有新 parser 在新 generation 中通过坐标 fixture 后才能产出 region ContentUnit，不能用旧 block 回填历史 citation。

## 6. 需要批准的破坏性影响

- 数据库主领域从 Document 迁移到 Asset，并新增不可变 Representation、ContentUnit、Embedding、scope 与 locator 类型表。
- `/documents`、当前 Citation/NoteSource DTO 和 Chat request/SSE 被协调替换。
- Worker job 输入从 `document_id` 迁移为 `asset_id`，ingestion orchestrator 通过封闭 `ModalityRegistry` 调度 adapter，不理解具体模态。
- 当前 Web `Document`、`activeDocumentId`、`PdfViewer` 和 Note/Citation 类型必须整体迁移，不能局部 alias。
- 备份 format version、恢复 oracle、指标 label 和运行手册同步变化。
- V3 同时实现后端/前端模态注册协议与测试模块，证明新增模态不修改稳定核心表和 Workspace/Chat/Citation/NoteSource/Viewer shell。
