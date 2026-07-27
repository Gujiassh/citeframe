# API 契约设计

## 1. 当前状态

- 运行时版本：V3 Asset/Evidence
- FastAPI 前缀：`/v1`
- 浏览器接口：同路径语义的 Next.js `/api` BFF
- 已移除：`/documents`、`documentId` 和 Document 业务 DTO
- 当前可用摄取闭环：PDF、PNG、JPEG、WebP Image
- Image 生产合同：精确 MIME/签名校验、完整解码、EXIF 方向归一化、`image_oriented` geometry、RapidOCR、Responses API caption、`image_ocr/image_caption` Representation、区域 ContentUnit 与 text embedding。Image adapter 已进入生产 Worker registry，数据库目录、API registry 与 Web 上传入口同步启用；未知、空或不匹配 MIME 均 fail closed

本文件描述当前代码合同。目标态设计参见：

- `docs/architecture/multimodal-api-data-contract-draft.md`
- `docs/architecture/modality-extension-contract.md`
- `docs/architecture/evidence-contract-rfc.md`

## 2. 接口边界

### 2.1 浏览器 -> BFF

浏览器只访问 `/api/...`。BFF 从 httpOnly session 解析用户身份，向 FastAPI 透传：

- `x-user-id`
- `x-ai-pdf-internal-token`

浏览器不得在 body 中自报 `userId` 或 `role`。

### 2.2 BFF -> FastAPI

FastAPI 业务接口使用 `/v1/...`，不直接暴露给公网浏览器。所有 Workspace 子资源必须同时验证：

- 用户存在
- 用户属于 URL 中的 Workspace
- 资源的 `workspace_id` 与 URL 一致
- owner-only 操作的成员角色

### 2.3 错误

当前 FastAPI 业务错误返回：

```json
{
  "detail": "Asset not found."
}
```

请求校验错误由 FastAPI 返回字段级 detail 数组。BFF 保留上游状态码和错误 body；前端不得把 4xx 当作空列表或静默成功。

## 3. 通用约定

- 核心 ID 使用 UUID 字符串。
- 时间使用 ISO 8601 字符串。
- 列表响应统一为 `{ "items": [], "nextCursor": null }`。
- 当前列表尚未启用真实 cursor，但保留响应外形。
- 所有页码为 1-based。
- 空间区域使用归一化坐标，必须满足 `0 <= x,y <= 1`、`0 < width,height <= 1`、`x + width <= 1`、`y + height <= 1`。
- `citationIndex` 在单条 assistant message 内从 0 开始；正文 `[n]` 映射到 `citationIndex = n - 1`。

## 4. Workspace

### 4.1 WorkspaceSummary

```json
{
  "id": "workspace-uuid",
  "name": "论文研究",
  "description": null,
  "systemPrompt": "Answer from evidence.",
  "retrievalTopK": 6,
  "chunkSize": 1200,
  "embeddingProvider": "ollama",
  "embeddingModel": "qwen3-embedding:0.6b",
  "embeddingDimensions": 1024,
  "embeddingVersion": "embedding-v1",
  "generationProvider": "openai",
  "generationModel": "gpt-5.5",
  "role": "owner",
  "assetCount": 2,
  "noteCount": 3,
  "threadCount": 4,
  "createdAt": "2026-07-17T00:00:00Z",
  "updatedAt": "2026-07-17T00:00:00Z"
}
```

`assetCount` 只统计 `deleted_at IS NULL` 的 Asset。

### 4.2 Workspace endpoints

| Method | Path | 语义 |
| --- | --- | --- |
| GET | `/v1/workspaces` | 当前用户可见 Workspace |
| POST | `/v1/workspaces` | 创建 Workspace |
| GET | `/v1/workspaces/{workspaceId}` | Workspace 详情 |
| PATCH | `/v1/workspaces/{workspaceId}/settings` | owner 更新 prompt/retrieval/chunk 设置 |
| DELETE | `/v1/workspaces/{workspaceId}` | owner 归档 Workspace |

## 5. Asset

### 5.1 AssetSummary

```json
{
  "id": "asset-uuid",
  "workspaceId": "workspace-uuid",
  "kind": "pdf",
  "title": "System Design",
  "sourceFilename": "system-design.pdf",
  "mimeType": "application/pdf",
  "byteSize": 12345,
  "status": "ready",
  "currentProcessingGeneration": 1,
  "currentIndexVersion": 7,
  "lastErrorCode": null,
  "lastErrorMessage": null,
  "createdAt": "2026-07-17T00:00:00Z",
  "updatedAt": "2026-07-17T00:00:00Z"
}
```

运行时状态：

- `pending_upload`
- `uploaded`
- `parsing`
- `chunking`
- `embedding`
- `ready`
- `failed`
- `deleting`
- `deleted`

列表不返回 `deleted_at IS NOT NULL` 的记录；`deleting` 仍可见，便于显示任务进度和重试。

### 5.2 AssetDetailResponse

PDF detail：

```json
{
  "asset": {},
  "detail": {
    "kind": "pdf",
    "pageCount": 84,
    "pages": [
      {
        "pageNumber": 29,
        "text": "...",
        "charCount": 1200,
        "ocrBlocks": [
          { "text": "...", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1 }
        ]
      }
    ]
  }
}
```

图片 detail 类型已经冻结，并严格取 `asset.currentProcessingGeneration` 的 `image_oriented` geometry；geometry 非正或 `orientationApplied=false` 时服务端 fail closed。M301-M302 已形成该数据；M403B 后生产 Web/Worker 图片纵向闭环已开放：

```json
{
  "asset": {},
  "detail": {
    "kind": "image",
    "widthPixels": 1200,
    "heightPixels": 800,
    "orientationApplied": true
  }
}
```

共享层必须按 `detail.kind` 分派，不通过 MIME、字段缺失或文件名猜类型。

### 5.3 Asset endpoints

| Method | Path | 语义 |
| --- | --- | --- |
| GET | `/v1/workspaces/{workspaceId}/assets` | 非 deleted Asset 列表 |
| GET | `/v1/workspaces/{workspaceId}/assets/{assetId}?pageNumber=1` | Asset detail；PDF 每次取指定页 |
| GET | `/v1/workspaces/{workspaceId}/assets/{assetId}/file` | 原始文件流 |
| POST | `/v1/workspaces/{workspaceId}/assets/upload-session` | 创建 Asset 与上传描述 |
| PUT | `/v1/workspaces/{workspaceId}/assets/{assetId}/upload?objectKey=...` | 上传二进制 |
| POST | `/v1/workspaces/{workspaceId}/assets/{assetId}/finalize-upload` | 建立 ingest job |
| POST | `/v1/workspaces/{workspaceId}/assets/{assetId}/retry` | 重试失败摄取 |
| POST | `/v1/workspaces/{workspaceId}/assets/{assetId}/reindex` | 对现有 ContentUnit 重建 embedding |
| DELETE | `/v1/workspaces/{workspaceId}/assets/{assetId}` | owner 创建 delete_cleanup job，返回 202 |
| POST | `/v1/workspaces/{workspaceId}/assets/{assetId}/delete-retry` | owner 重试失败删除 |

`/file` 始终返回 immutable 原始上传对象。图片 locator 与 `sourceVersions.representationId` 冻结的是实际支持结论的 `image_ocr` 或 `image_caption` Evidence Representation，不是显示对象。Image Viewer 使用两条权限保护的 oriented Representation 文件流：历史 Evidence 请求同时提交 frozen `processingGeneration` 与 Evidence `representationId`，服务端验证同 Workspace、同 Asset、同 generation 和允许的 OCR/caption kind 后解析 `image_oriented`；detail 与文件流查询的 Representation/geometry 连接也必须显式约束相同 Workspace 和 Asset，不能只依赖关系 ID。资产行预览先重新读取 Asset detail，再提交该响应的 `currentProcessingGeneration`，服务端与当前 Asset 代次精确对照，漂移时返回 409，Web 重试必须重新读取 detail，不能重复旧 generation。两者都不能直接渲染原图，也不能把 Evidence Representation、任意 UUID 或列表第一条当作显示对象，否则 EXIF 原始像素与 locator 坐标会错位。M304B 前图片框选只作为 Web runtime 草稿；该阶段已获批并实现，当前 Chat/Note API 以以下区域目标合同为准。

M304B 后端已实现区域目标合同。Chat 和 Note 创建请求可增加默认空数组 `evidenceTargets`；当前唯一 variant 为 `image_region`，只包含 `assetId`、`processingGeneration`、固定 `coordinateSpace=image_normalized_top_left_v1` 和规范化 `regions`。服务端严格拒绝客户端提供 `representationId`、excerpt、width/height、orientation 或任意额外字段，重新解析同 Workspace/Asset/generation 的 OCR/caption Evidence，并为本次目标创建独立 locator。Chat 将快照保存在 user message 的 `inputEvidence` 数组并把 canonical oriented 区域作为当前请求的视觉输入；旧消息返回空数组，历史输入不隐式重新发送给模型。直接 NoteSource 的 `messageCitationId=null`。现有 `selectionText`、`assetScope`、`sourceCitationIds`、Citation 和历史保存语义不变。

### 5.4 上传不变量

1. `upload-session` 将 MIME 规范为 lowercase，再根据注册表生成 `asset.kind` 与 MinIO object key。
2. `upload` 要求请求 `Content-Type` 与 session MIME 一致，写入 MinIO 时始终使用已经验证的 canonical MIME。
3. `upload` 流式计算 SHA-256，校验声明字节数、100 MB 上限和魔数签名；Image inspector 返回实际 PNG/JPEG/WebP MIME，不能只判断“任意图片”。
4. MIME 与文件签名不匹配返回 422，不把扩展名当证据；Worker 完整解码后再次核对实际格式并拒绝截断、尾随数据、动画和超限像素。
5. `finalize-upload` 只接受 `pending_upload` 且对象确实存在的 Asset。
6. 只有 finalize 成功后才进入异步摄取状态机。

## 6. Job

```json
{
  "id": "job-uuid",
  "workspaceId": "workspace-uuid",
  "assetId": "asset-uuid",
  "jobType": "ingest",
  "status": "queued",
  "attemptCount": 1,
  "queuedAt": "2026-07-17T00:00:00Z",
  "startedAt": null,
  "finishedAt": null,
  "errorCode": null,
  "errorMessage": null
}
```

当前 job type：`ingest`、`embed_chunks`、`delete_cleanup`。

当前 job status：`queued`、`running`、`succeeded`、`failed`、`cancelled`。

读取接口：`GET /v1/workspaces/{workspaceId}/jobs/{jobId}`。

## 7. Evidence

### 7.1 Locator discriminated union

`pdf_page`：

```json
{ "kind": "pdf_page", "version": 1, "pageNumber": 29 }
```

`pdf_region`：

```json
{
  "kind": "pdf_region",
  "version": 1,
  "pageNumber": 29,
  "coordinateSpace": "pdf_crop_box_normalized_top_left_v1",
  "pageGeometry": {
    "cropBoxPoints": [0, 0, 612, 792],
    "rotationDegrees": 0,
    "displayWidthPoints": 612,
    "displayHeightPoints": 792
  },
  "regions": [
    { "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1 }
  ]
}
```

`image_region`：

```json
{
  "kind": "image_region",
  "version": 1,
  "coordinateSpace": "image_normalized_top_left_v1",
  "widthPixels": 1200,
  "heightPixels": 800,
  "orientationApplied": true,
  "regions": [
    { "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1 }
  ]
}
```

未知 `kind`、未知版本或缺少类型字段必须合同失败，不能降级为整页或选择第一个 renderer。

### 7.2 Citation

```json
{
  "id": "citation-uuid",
  "messageId": "message-uuid",
  "citationIndex": 0,
  "assetId": "asset-uuid",
  "assetKind": "pdf",
  "assetTitle": "System Design",
  "sourceAvailable": true,
  "excerpt": "Evidence excerpt.",
  "locator": { "kind": "pdf_page", "version": 1, "pageNumber": 29 },
  "sourceVersions": {
    "parserVersion": "legacy-pdf-v1",
    "processingGeneration": 1,
    "representationId": "representation-uuid",
    "indexVersion": 7
  }
}
```

Citation 是生成时快照。重索引、重处理和源删除不得改写 `assetTitle/excerpt/locator/sourceVersions`。对图片，`sourceVersions.representationId` 指向实际 OCR/caption Evidence Representation；Viewer 仍按该快照的 `processingGeneration` 选择 `image_oriented` 显示表示。`sourceAvailable=false` 时仍可展示快照，但 Viewer 打开操作必须禁用。

## 8. Chat

### 8.1 Asset scope

默认全部可用资产：

```json
{ "mode": "all_ready" }
```

显式选择：

```json
{
  "mode": "selected",
  "assetIds": ["asset-uuid"]
}
```

`selected.assetIds` 必须非空、无重复、属于当前 Workspace 且状态为 `ready`。服务端在检索前解析范围，并把本次消息的 scope mode、Asset 顺序、kind/title 快照写入消息范围表。

### 8.2 Chat request

`POST /v1/workspaces/{workspaceId}/chat/stream`

```json
{
  "threadId": "thread-uuid",
  "question": "请比较两份报告的结论。",
  "assetScope": { "mode": "selected", "assetIds": ["asset-uuid"] },
  "selectionText": null,
  "parentMessageId": "message-uuid",
  "editMessageId": null
}
```

### 8.3 SSE

事件顺序：

1. `meta`：`threadId/userMessageId/assistantMessageId`
2. 多个 `delta`：`{ "text": "..." }`
3. `citations`：`{ "items": Citation[] }`
4. `done`：`threadId/assistantMessageId`

失败可发送 `error`：`{ "code": "...", "message": "..." }`。

约束：

- citation 在 `done` 前完成持久化。
- 浏览器允许忽略未知事件名，以便协议增加非破坏性事件。
- 浏览器必须拒绝畸形 citation/locator/sourceVersions，不能过滤坏项后继续接受 `done`。
- 流在 `done/error` 前中断视为失败。

### 8.4 Thread endpoints

| Method | Path | 语义 |
| --- | --- | --- |
| GET | `/v1/workspaces/{workspaceId}/threads` | thread 列表 |
| POST | `/v1/workspaces/{workspaceId}/threads` | 创建 thread |
| GET | `/v1/workspaces/{workspaceId}/threads/{threadId}/messages` | 活动分支消息与 citation |
| DELETE | `/v1/workspaces/{workspaceId}/threads/{threadId}` | 归档 thread |

## 9. Notes 与 Tags

### 9.1 NoteSource

NoteSource 与 Citation 使用同一 Evidence envelope：

```json
{
  "id": "note-source-uuid",
  "messageCitationId": "citation-uuid",
  "assetId": "asset-uuid",
  "assetKind": "pdf",
  "assetTitle": "System Design",
  "sourceAvailable": true,
  "excerpt": "Evidence excerpt.",
  "locator": { "kind": "pdf_page", "version": 1, "pageNumber": 29 },
  "sourceVersions": {
    "parserVersion": "legacy-pdf-v1",
    "processingGeneration": 1,
    "representationId": "representation-uuid",
    "indexVersion": 7
  },
  "createdAt": "2026-07-17T00:00:00Z"
}
```

创建带来源笔记时只接受当前 Workspace 的真实 `sourceCitationIds`。服务端复制快照；普通自由笔记的来源数组为空。PDF 划词创建普通笔记时不得伪造 NoteSource。

### 9.2 Endpoints

| Method | Path | 语义 |
| --- | --- | --- |
| GET/POST | `/v1/workspaces/{workspaceId}/notes` | 列表/创建 Note |
| GET/PATCH/DELETE | `/v1/workspaces/{workspaceId}/notes/{noteId}` | 读取/更新/归档 Note |
| GET/POST | `/v1/workspaces/{workspaceId}/tags` | 列表/创建 Tag |
| GET/PATCH/DELETE | `/v1/workspaces/{workspaceId}/tags/{tagId}` | 读取/更新/删除 Tag |
| POST | `/v1/workspaces/{workspaceId}/assets/{assetId}/tags` | 替换 Asset tag 集合 |
| POST | `/v1/workspaces/{workspaceId}/notes/{noteId}/tags` | 替换 Note tag 集合 |

## 10. 合同门禁

以下变化属于破坏性合同变化，实施前必须同步 schema、调用方、测试、fixtures、迁移与本文档：

- 增删 locator kind 或修改既有 locator 含义
- 修改 Citation/NoteSource 快照字段或保存语义
- 修改 Chat `assetScope` 解析或消息范围持久化
- 修改 Asset 删除、重索引或 `sourceAvailable` 语义
- 修改上传 MIME/签名校验或开放新的生产摄取模态
- 修改 Workspace 隔离或 owner 权限边界
