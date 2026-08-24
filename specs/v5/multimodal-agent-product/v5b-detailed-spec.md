# V5-B 多模态资料扩展详细规格

## 状态与使用范围

状态：`approved-markdown-v1; implemented; formal-isolated-deployment-passed; pending-final-critical-review`。

本文是 B001-B008 的字段级和验收级规格记录。OD-B1/B2/B3/B4 已批准并已实现；B008 formal isolated deployment gate 已通过，durable evidence 位于 `docs/evals/artifacts/v5b-document-deployment-v1/`；OD-B5 明确拒绝 HTML，OD-B6/B7 继续独立阻塞 Audio/Video。本文引用 V3 已完成的 Asset/Evidence kernel，不重新设计 Asset、Citation、NoteSource、Chat scope、embedding index 或删除恢复语义。

## 1. 目标与完成定义

V5-B 的目标不是“支持更多 MIME”，而是让一个新模态完成可回溯的纵向闭环：

```text
upload-session
  -> byte/MIME validation
  -> Asset uploaded
  -> ingest job
  -> immutable Representation + typed ContentUnit + typed EvidenceLocator
  -> current text retrieval
  -> Chat/Research EvidenceCandidate
  -> Citation / NoteSource clone
  -> Web renderer or playback
  -> retry / reprocess / delete / restore
```

每个启用模态必须满足：

- Workspace 隔离、上传字节和声明 MIME 双重校验；
- Asset 状态和 job 状态复用现有 orchestrator；
- representation 和 locator 有不可变 generation snapshot；ContentUnit 通过 representation/locator 链解释 generation；
- retrieval 只返回 ready、未删除、current generation/index 且 locator 链完整的候选；
- Citation 和 NoteSource envelope 不变，只扩充 discriminator；
- 删除后历史 snapshot 可读，`sourceAvailable=false`，Viewer 不再打开源；
- 重处理不改写已有 locator/citation/note source；
- provider/capability 缺失在任何持久化副作用前 fail-closed；
- mixed PDF/Image/Document 回归不改变既有语义。

## 2. 必须复用的稳定 kernel

### 2.1 代码与数据边界

| 责任 | 现有 SSoT | 新模态约束 |
|---|---|---|
| Registry/catalog | `modalities/registry.py`, `models/catalog.py` | 代码 module、catalog rows、contract version 必须同时一致 |
| Ingestion orchestration | `services/ingestion.py` | orchestrator 负责 claim/lease、状态、事务、generation、上传/清理和 embedding；不解析模态内容 |
| Worker adapter seam | `modalities/ingestion.py`, `apps/worker/src/ai_pdf_worker/{pdf,image}_ingestion.py` | 当前 adapter 接收共享 `Session`/`Asset`，在 API orchestrator 提供的会话边界内持久化 typed rows，返回 `IngestionResult.generated_objects`；新 adapter 必须匹配这个实际 seam，不能假定 manifest-only 或已完成的进程隔离事务 |
| Locator | `modalities/evidence.py` | 新增 typed codec/detail table，不写任意 JSON |
| Retrieval | `services/retrieval.py` | 只消费 `EvidenceCandidate` 和 registered channel signature |
| Citation/NoteSource | `schemas/chat.py`, citation/note services | 公共 envelope、clone 和保存语义保持不变 |
| Web | `apps/web/src/lib/evidence/*` | 新模块注册到静态 registry，shell 不按 MIME 猜 renderer |

如果 document 需要改变 `IngestionAdapter`/`IngestionResult`，必须单独分配共享 seam owner、写 migration/save impact 和 contract tests；B-WORKER-DOC 不能在没有 owner 的情况下改变共享接口。

### 2.3 不得改变的公共语义

- `AssetSummary.kind` 仍是 discriminated kind。
- Chat `assetScope` 仍是 `all_ready | selected`，创建消息时保存实际 scope snapshot。
- `EvidenceLocatorDto` 只增加类型化 union variant。
- Citation/NoteSource 的 `assetId/assetKind/assetTitle/excerpt/sourceAvailable/sourceVersions/locator` 含义不变。
- `content_unit_embeddings` 仍是可重建投影；V5-B 不自动补建、不自动换 provider。
- V5-A embedding index contract 继续 fail-closed；只有 mismatched vector 时不能静默返回空结果。
- DB 是业务真相，MinIO/object storage 保存 immutable bytes。**当前运行时事实**：API package 拥有 schema/migration 与 mutation logic **定义**；ingestion adapter 在 orchestrator 提供的**共享 SQLAlchemy Session** 内写 typed rows；Research Worker `_ApiPort` 另在 Worker 进程内创建 Session 并 commit/rollback。V5-B 不得把“Worker 不定义 ORM/migration”误写成“Worker 进程从不 commit”，也不得假定 manifest-only / 进程隔离事务已落地（见 `docs/architecture/api-worker-boundary-follow-up-2026-08-18.md`）。

## 3. 共享接入合同

### 3.1 Asset 与版本

新模态 upload-session 必须得到已注册 `asset_kind`，不能由扩展名或前端传值单独决定。创建后沿用状态：

```text
pending_upload -> uploaded -> parsing -> chunking -> embedding -> ready
                         \-> failed
ready -> deleting -> deleted
failed -> retry -> parsing/...
ready --explicit embed_chunks/reindex job--> ready

`reindex` 是 job/action，不是 Asset status。现有 orchestrator 在部分无 embedding 配置路径中还会出现 `chunked` intermediate status；新模态必须沿用当前 API/Worker 对该 status 的既有解释，不得把它改名或把 reindex 当成新状态。
```

实现必须明确：

- `current_processing_generation` 只在一个完整处理代代成功后激活；
- `current_index_version` 只由 index activation 更新；
- 失败代际不覆盖当前 ready 代际；
- 新 job 会按现有 CAS/lease 规则 supersede 或 cancel 旧 job；
- delete 清理 source/derived objects 和 current derived rows，但不删除历史 Citation/NoteSource locator snapshot；
- delete 后不得因迟到的 ingest job resurrect Asset；
- stale running job 复用现有 15 分钟 lease reclaim，不新增模态专用状态。

### 3.2 Representation

现有 `asset_representations` 持久化字段是 `representation_kind`、`processing_generation`、generator provenance、`object_key`、`content_sha256` 和 `generator_version`。V5-B 不把 `contract_version`、`source_or_derived` 或 `normalization_version` 假定成现有列。

Document 的 parser/normalization/sanitizer 版本必须先映射到现有 generator/config snapshot，或在 OD-B3 批准后增加明确的 typed/additive 字段；worker 不得自行增加列，也不能用未约束 JSON 代替。`representation_kind` 仍然是 catalog literal。展示用媒体 object 与 Evidence 真相 representation 可以不同，但 locator 必须冻结真正支持 Evidence 的 representation snapshot。

### 3.3 ContentUnit

现有 ContentUnit 持久化字段以 `representation_id`、`source_locator_id`、`unit_kind`、`unit_order`、`text_content`、`token_count` 和 `index_version` 为准；V5-B 不假定新增 processing-generation 列。generation 通过 Representation 和 Locator snapshot 链表达，若需直接列出 generation 必须走 OD-B3。

每个 ContentUnit 必须声明：

```text
unit_kind
unit_order                 # stable within asset + representation + generation
text_content               # only public retrieval context
char_start? / char_end?    # only if contract defines a normalized text coordinate
source_locator_id
index_version
```

排序必须可重建、无歧义；相同 source bytes、parser version、normalization version 下必须产生相同顺序和 locator payload。ContentUnit 当前主键默认是 UUID；如果要求 deterministic ContentUnit IDs，必须在 B-G3 单独冻结算法和迁移影响。模态几何、时间、DOM 路径、record path 不放进 `text_content` 或未约束 JSON。

### 3.4 Locator

公共头固定：

```text
evidence_locators(
  id, workspace_id, asset_id,
  locator_kind, locator_version,
  processing_generation_snapshot,
  representation_id_snapshot,
  created_at
)
```

新 detail family 必须是已注册的 `spatial | temporal | record` 之一。codec 必须实现：

- parse/validate；
- serialize DTO；
- clone details；
- retrieval key；
- sourceAvailable/viewer resolution；
- unknown kind/version fail-closed。

### 3.5 Adapter I/O

```text
adapter.ingest(
  db: Session,
  asset,
  payload,
  processing_generation,
  config_snapshot,
  created_at,
) -> IngestionResult

IngestionResult.generated_objects: tuple[GeneratedObject, ...]
adapter.cleanup(db: Session, asset) -> None
```

V5-B 必须匹配当前 `apps/api/src/ai_pdf_api/modalities/ingestion.py` 的实际 seam：adapter 在 orchestrator 提供的 SQLAlchemy transaction 内完成模态专用 Representation/ContentUnit/locator 持久化，并通过 `IngestionResult.generated_objects` 返回待上传/清理的 immutable objects。共享 orchestrator 仍负责 job claim/lease、状态、generation activation、embedding、对象上传回收、delete/retry；adapter 不直接发 provider HTTP、不读取任意 secret、不访问 Chat/Research ORM。若要改成 manifest-only 或把 row persistence 移出 adapter，必须由 serial seam owner 提交独立 contract/migration/save impact，不能由 B-WORKER-DOC 单独改变。

## 4. 第一 document slice 候选合同

本节是 Markdown/HTML 的实现候选，不是批准结果。OD-B1/B2/B3/B4 必须先关闭；若选择 HTML，再关闭 OD-B5。

### 4.1 Asset 与 MIME

推荐第一片只启用 Markdown：

```text
asset_kind: document
MIME: text/markdown
```

如果 OD-B1 同时批准 HTML，HTML 仍然必须使用同一个 typed `document` contract，但增加独立 parser/sanitizer version、fixture 和 enablement review：

```text
MIME: text/html
```

建议限制：

- UTF-8 canonical decode；非法编码 fail-closed；
- source bytes SHA-256 参与 Asset identity/fixture manifest；
- HTML 外链、script、event handler、iframe、form、CSS/URL 资源按 OD-B5 策略处理；
- 原始 source bytes 永远保留为 source object，不把 sanitized output 当原始来源；
- sanitized/normalized output 若持久化，必须是不可变 derived Representation，并记录 sanitizer/normalization version。

### 4.2 Representation kinds

候选 literal：

```text
document_source       # source bytes / immutable source object reference
document_normalized   # canonical text/structure used for parsing and retrieval
document_render       # optional sanitized/renderable HTML or Markdown projection
```

最小 Markdown slice 只需要 `document_source` 与 `document_normalized`；`document_render` 只有 Viewer 需要且输出策略已批准时才能增加。每个 kind 都要进入 `representation_types`，不能只写到 config snapshot。

### 4.3 ContentUnit kinds

候选 literal：

```text
document_block        # heading, paragraph, list item, quote, code, table block
 document_text_chunk  # retrieval-sized projection of one or more blocks
```

`document_block` 保留结构 metadata 在 typed representation/detail 中；`document_text_chunk` 只保存检索文本和 locator 关联。禁止只切成无结构 chunk 后再由 UI 猜 heading/path。

必须冻结：

- block order 是 source traversal order，从零或一开始必须全栈一致；
- heading path 的层级、空 heading 规则、重复 heading 规则；
- code fence、blockquote、list nesting、table 的 block kind 和 text normalization；
- `char_start/end` 相对于哪个 canonical normalized text；
- parser version 与 normalization version 变更时是否创建新 generation。

### 4.4 Document locator 候选

推荐 literal：`document_anchor`，`locator_version=1`，`detail_family=record`。

候选 detail：

```text
document_locator_details(
  locator_id,
  block_id,
  block_kind,
  heading_path_json_or_typed,  # final decision must avoid unconstrained JSON truth
  char_start,
  char_end,
  text_sha256,
  normalization_version,
)
```

其中 `heading_path` 如果保留 JSON，必须是 schema-validated string array；更严格的实现可以拆成 ordered child rows。`block_id` 必须由 source SHA + parser version + canonical block identity 稳定生成，不能依赖 DOM index。`char_end > char_start`；范围必须在 normalized text 长度内；`text_sha256` 用于 view-time integrity check。

不允许把 CSS selector、line number、当前 DOM index 或“整篇 document”作为唯一 Evidence locator。Web 可使用 heading path 和 block ID 找到展示位置，但 Evidence 真相是 typed detail + generation/representation snapshot。

### 4.5 Document API DTO 候选

Asset detail 只扩充 discriminated union：

```json
{
  "kind": "document",
  "document": {
    "format": "markdown",
    "parserVersion": "document-parser-v1",
    "normalizationVersion": "document-normalization-v1",
    "blockCount": 12,
    "headings": [
      {"blockId": "...", "level": 2, "text": "...", "order": 3}
    ]
  }
}
```

Citation locator 只增加：

```json
{
  "kind": "document_anchor",
  "version": 1,
  "blockId": "...",
  "blockKind": "paragraph",
  "headingPath": ["Section", "Subsection"],
  "charStart": 120,
  "charEnd": 260,
  "textSha256": "...",
  "normalizationVersion": "document-normalization-v1"
}
```

字段名、literal 和单 range 约束已由 OD-B2 批准并进入 API implementation。公共 Citation/NoteSource envelope 不增加 document 专用顶层列。

新增 `document_anchor` 不能只改 Citation DTO。B-G3 已同步列出并测试 API `EvidenceLocatorDto`、Worker evidence locator union、Web evidence registry 和 OpenAPI discriminator；Document 已进入 Citation/NoteSource 全链路。Chat `evidenceTargets` selection 仍按 save-contract checklist 保持未扩展。

### 4.6 Document normalized-content access (implemented contract)

The existing `/file` endpoint serves the immutable source object and is not sufficient for generation-scoped block highlighting. The approved first slice exposes the generation/representation-scoped route:

```text
GET /workspaces/{workspaceId}/assets/{assetId}/representations/{representationId}/content
```

or an equivalent Asset detail projection that is explicitly generation/representation scoped. The implemented route identifies `assetId`, `representationId`, `processingGeneration`, parser/normalization versions, content SHA-256 and typed block records. It enforces Workspace membership, deleted-source behavior, current/historical generation policy and no raw HTML execution. The Web renderer never infers canonical text from the upload filename or current parser.

The first Document slice exposes normalized-content access and exact block highlight through the route above; HTML remains rejected by OD-B5 and is not inferred from this Markdown contract.

### 4.7 Document retrieval

第一轮建议只注册 text channel：

```text
unit_kind: document_text_chunk
representation_kind: document_normalized
authorized locator: document_anchor
embedding_space: text
```

Lexical 和 dense 候选必须经过：Workspace、assetScope、ready/not-deleted、current generation、current index、representation/locator chain、active embedding contract、registered type signature。混合检索按唯一 locator 去重；不能将 `document_block` 和 chunk 误合并为两个引用位置。

### 4.8 Document Viewer

Markdown viewer 最小行为：

- 展示 source title、格式、heading navigation 和 sanitized/canonical text；
- 点击 Citation 打开相同 generation 的 block；
- highlight 使用 `blockId + charStart/end`，失败显示 unavailable，不跳到第一个 block；
- source deleted 时显示 snapshot、禁用打开；
- unknown locator/version 显示 contract error；
- 不执行原始 HTML，不加载未经批准的外链资源。

HTML viewer 只有在 OD-B5 通过后实现；不能复用 Markdown renderer 的假设。

## 5. Audio / Video 预留合同

Audio/Video 只允许先写 brief 和 fixtures，当前不进入 production registry，因为 V5-A ASR 状态是 unavailable。

### 5.1 Audio 候选

```text
asset_kind: audio
representations: audio_source, audio_transcript
content_units: audio_transcript_segment
locator: audio_range, detail_family=temporal
```

必须冻结：duration_ms、channel count、sample rate、codec、segment `start_ms/end_ms`、speaker identity policy、overlap policy、transcript normalization、ASR provider/model/version/fingerprint、最大时长/成本/超时、播放 source 与 transcript representation 的关系。`end_ms > start_ms`，范围不得越过 duration，segments 在同一 generation 内按 start/order 稳定。

缺少 ASR 时错误必须在 representation/content unit 持久化前产生稳定 `asr_capability_unavailable` 或批准后的等价 code；禁止空 transcript、caption 假文本或自动转到其他 provider。

### 5.2 Video 候选

```text
asset_kind: video
representations: video_source, video_transcript, video_keyframe, video_preview
content_units: video_transcript_segment, video_shot, video_keyframe
locators: video_range, video_frame, detail_family=temporal
```

必须冻结 duration/timebase/frame rate、frame number 与 timestamp 的关系、keyframe sampling budget、字幕/ASR provenance、preview object、播放器 seek tolerance、range overlap 和 delete/restore 对大对象的策略。不能把 Video 当成 Audio 加一个 MIME。

## 6. 错误、幂等与恢复

每种模态必须有稳定错误码表，至少覆盖：

```text
asset_modality_not_enabled
asset_mime_mismatch
asset_bytes_invalid
asset_encoding_unsupported
document_parse_failed
document_normalization_failed
locator_invalid
locator_version_unsupported
modality_capability_not_configured
modality_provider_timeout
modality_provider_error
modality_persist_failed
embedding_configuration_mismatch
embedding_index_mismatch
asset_delete_cleanup_failed
```

| Code candidate | HTTP/API projection | Retryable | Side-effect rule |
|---|---:|---:|---|
| `asset_modality_not_enabled` | 409 | no | no ingest rows or objects |
| `asset_mime_mismatch` / `asset_bytes_invalid` | 400/422 per existing upload contract | no | reject before job |
| `asset_encoding_unsupported` / parse/normalize failure | 422 | no unless policy explicitly marks provider transient | failed job may retain safe failure only; no current generation activation |
| `locator_invalid` / `locator_version_unsupported` | 409 | no | no Citation/NoteSource write |
| `modality_capability_not_configured` | 409/503 per capability boundary | no automatic retry | fail before provider HTTP and derived persistence |
| `modality_provider_timeout` / `modality_provider_error` | existing provider error projection | policy-defined | cleanup partial objects; failed generation stays non-current |
| `modality_persist_failed` | 500/internal safe error | operator retry only if idempotent | transaction rollback and manifest cleanup |
| `embedding_configuration_mismatch` / `embedding_index_mismatch` | existing V5-A mapping | no automatic retry/reindex | preserve explicit reindex meaning |
| `asset_delete_cleanup_failed` | existing delete-retry projection | delete retry only | never resurrect source or current generation |

Before B-G3, each chosen literal must be mapped to the repository's existing API/Worker error class, HTTP status, job `lastErrorCode`, retry policy, metrics label, and user-safe message. This table is a contract checklist, not permission to invent a new public error envelope.

错误信息可以给用户理解，但不能泄露 raw secret、endpoint、request body、provider response 或未审计路径。重试规则按现有 job/policy；不可重试的 schema/contract/permission/bytes 错误不能由 retry endpoint 强行重跑。

对象和 DB side effects 必须遵守：

1. 先完成上传/解析校验，再写派生对象和 rows；
2. 任何 commit failure 都有 manifest cleanup；
3. 失败 generation 不成为 current；
4. delete/retry 幂等，迟到 job 不 resurrect；
5. historical locator/citation/note source 可解释性不依赖 current derived row；
6. backup format 增加新表/对象时递增 format version，旧 restore 不接受未知版本。

## 7. V5-B gates

| Gate | 必须完成 | 禁止事项 |
|---|---|---|
| B-G0 | canonical worktree、docs 状态、owner 和 fixture policy 明确 | 在 stale worktree 开始编码 |
| B-G1 | B001 brief、OD-B1 priority approved；若选 HTML 再要求 OD-B5 | 直接把 MIME 加入 registry |
| B-G2 | PDF/Image shared entry audit、影响清单、无意外 save-contract 变化 | 在共享 shell 增加 modality branch |
| B-G3 | OD-B2/B3/B4 locator/API/catalog/migration/retrieval impact 批准；若选 HTML 同时完成 OD-B5 | worker 自行命名 schema/literal |
| B-G4 | upload→ready→retrieve→cite→note→view→retry/delete 的 first modality slice，使用已批准 text retrieval contract | 先做局部 parser 再补链路 |
| B-G5 | mixed workspace、generation、delete/recovery、restore oracle 通过 | 只测新模态 happy path |
| B-G6 | Critical review `ACCEPT`、catalog/code/fixtures 同批启用 | 只提交 DB row 或 MIME |
| B-G7 | ASR contract 后再开 Audio；Video 另行 gate | ASR unavailable 时假实现 |

## 8. B001 modality brief 模板

任何新模态 brief 必须逐项填写：

1. 用户 JTBD、明确不做的任务、样本和成功结果；
2. MIME/bytes/size/duration/encoding/security limits；
3. Asset kind、catalog version、Representation kinds；
4. ContentUnit kinds、ordering、text derivation；
5. Locator literals、detail family、version、coordinate/time/path rules；
6. provider capability、secret boundary、timeout、cost、privacy；
7. adapter input/output、object manifest、cleanup；
8. API detail/locator/evidence target variants；
9. retrieval channel/signature/embedding space/ranking；
10. Web renderer/selection/playback and mobile behavior；
11. error table、retryability、idempotency、delete/recovery；
12. Citation/NoteSource/history/reindex invariants；
13. fixtures/golden cases/hash policy；
14. migration/restore/metrics/runbook impact；
15. enablement review and rollback plan；
16. open decisions with owner and approval date。
