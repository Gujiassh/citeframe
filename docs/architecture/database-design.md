# 数据库设计

## 1. 当前状态

- 数据库：PostgreSQL + pgvector + pg_trgm
- Alembic head：`m7a8b9c0d1e2`
- 运行时领域模型：Asset/Evidence
- 已移除表：`documents`、`document_pages`、`document_chunks`、`document_tags`
- 当前生产摄取：九类启用模态（PDF、Image、Document、HTML、DOCX、XLSX、PPTX、Audio、Video）；PDF 文本层/扫描 PDF OCR、Image 规范化与各已启用模态 adapter 均由 Worker 注册表调度
- 图片 `image_oriented/image_ocr/image_caption` Representation、方向后 geometry、`image_ocr_region/image_caption` ContentUnit、`image_region` locator、text embedding、Citation/NoteSource 历史快照与 Image Viewer 已接入；M403B 的真实上传/检索/Evidence/恢复报告已通过并归档
- V4 Research/Evaluation ledger、Workflow/Prompt v2、immutable Artifact/Claim/Evidence provenance 与 provider/tool/budget accounting 已接入；R800 v4 的 PostgreSQL/MinIO 空部署恢复通过

当前 schema 以本文件的表分组、字段职责和 Alembic head `m7a8b9c0d1e2` 为准。`database-er-legacy-document.mmd` 与 `database-er.mmd` / `database-er.svg` 均为历史快照，不得作为当前迁移或模型实现输入。

`c9d1e2f3a4b5` 是不可原地 downgrade 的一次性 Asset 迁移；`d0e2f4a6b8c1` 在其上增加 user-message 输入 Evidence。回到旧 Document 模型只能恢复迁移前的 PostgreSQL/MinIO 同批备份。

`a3c5e7f9b1d4` 是生产 Image 启用的数据目录迁移，只把 `asset_types.image.enabled` 从 `false` 切换为 `true`；不新增表、字段、API payload 或保存语义，降级恢复为 `false`。

`b4d6f8a0c2e4` 增加获批 Research 账本，`c5e7a9b1d3f6` 增加 append-only Evaluation 账本，`e8f1a2b3c4d5` 增加 production Workflow/Prompt v2。已有业务引用时 downgrade fail closed；空引用往返保留 v1 Workflow/Prompt。

## 2. 设计原则

1. `workspace_id` 是所有业务查询的首要隔离键。
2. Asset 是用户文件身份；Representation 是某次处理产物；ContentUnit 是可检索内容；Embedding 是指定空间和模型下的向量。
3. EvidenceLocator 是不可变定位身份，模态细节放在类型化 detail 表，不放任意 JSON。
4. Citation 和 NoteSource 保存生成时快照，不能通过当前 Asset 或当前索引反推历史含义。
5. 运行时 UI 状态不进入持久化模型。
6. 新模态通过封闭代码注册表与数据库类型目录共同启用；目录和部署注册表不一致时 readiness 失败。
7. 不使用文件名、列表顺序、名称当 ID 或“第一个非空字段”推断数据语义。
8. Research runtime 状态、provider/tool usage 与 Artifact provenance 进入 PostgreSQL；模型消息历史、credential 和思维链不持久化。

## 3. 表分组

### 3.1 身份与 Workspace

- `users`
- `workspaces`
- `workspace_memberships`

### 3.2 模态类型目录

- `asset_types`
- `representation_types`
- `content_unit_types`
- `locator_types`
- `embedding_spaces`

### 3.3 Asset 与处理产物

- `assets`
- `asset_representations`
- `pdf_pages`
- `image_representation_geometry`
- `content_units`
- `content_unit_embeddings`
- `ingestion_jobs`

### 3.4 Evidence

- `evidence_locators`
- `pdf_locator_details`
- `image_locator_details`
- `spatial_locator_regions`

### 3.5 Chat 与范围快照

- `chat_threads`
- `chat_messages`
- `message_retrieval_scopes`
- `message_retrieval_scope_assets`
- `message_citations`

### 3.6 Notes 与 Tags

- `notes`
- `note_sources`
- `tags`
- `asset_tags`
- `note_tags`

### 3.7 Research 与 Evaluation

- `prompt_versions`、`workflow_versions`、`workflow_prompt_bindings`
- `research_runs`、`research_plan_revisions`、`research_execution_snapshots`
- `research_steps`、`research_step_dependencies`、`research_step_attempts`、`research_step_retry_requests`
- `research_events`、`human_decisions`、`human_decision_claims`
- `research_artifacts`、`research_claims`、`research_evidence_snapshots` 与 provenance 关系表
- `research_provider_calls`、`research_tool_calls`、`research_budget_ledgers`、`research_idempotency_records`
- `research_evaluation_suites`、`research_evaluation_runs`、`research_evaluation_case_results`、`research_evaluation_claim_results`

## 4. 稳定内核

### 4.1 `assets`

Asset 表示 Workspace 中一个用户文件的稳定身份。

关键字段：

- `id`
- `workspace_id`
- `created_by_user_id`
- `asset_kind -> asset_types.kind`
- `title`
- `source_filename`
- `object_key`
- `mime_type`
- `byte_size`
- `source_sha256`
- `status`
- `current_processing_generation`
- `current_index_version`
- `latest_ingestion_job_id`
- `last_error_code / last_error_message`
- `deleted_at`
- `created_at / updated_at`

语义：

- Asset 与文件扩展名解耦，`asset_kind` 来自 MIME 注册和字节签名校验。
- 删除采用软删除身份 + 清理原对象/可重建内容；历史 Citation/NoteSource 仍通过 Asset ID 和自身快照回放。
- `current_processing_generation` 标记当前处理代次，`current_index_version` 标记当前在线索引版本，两者不能混用。

### 4.2 `asset_representations`

Representation 表示某个 Asset 在一次 processing generation 中生成的可追溯表示。

关键字段：

- `asset_id`
- `representation_kind -> representation_types.kind`
- `processing_generation`
- `generator_provider / generator_model / generator_version`
- `object_key / content_sha256`

唯一约束：

```text
unique(asset_id, representation_kind, processing_generation)
```

历史迁移的 PDF 使用 `pdf_text_legacy` representation；新的处理不得覆盖旧代次身份。图片 M301 固定把方向归一化结果编码为无 EXIF canonical PNG，`object_key` 使用 `representations/{generation}/image-oriented.png`，`content_sha256` 只哈希该派生对象；原 Asset object 和 `source_sha256` 不变。M302 的 `image_ocr` 与 `image_caption` 是支持检索结论的 Evidence Representation，不替代 `image_oriented` 显示对象。

### 4.3 `content_units`

ContentUnit 是检索和生成引用的最小内容单元。

关键字段：

- `asset_id`
- `representation_id`
- `source_locator_id`
- `unit_kind -> content_unit_types.kind`
- `unit_order`
- `text_content`
- `search_vector`：由 `to_tsvector('simple', text_content)` 生成并持久化的 PostgreSQL `tsvector`
- `token_count`
- `char_start / char_end`
- `index_version`

`char_start / char_end` 仅用于能准确映射到页面文本单一连续跨度的 ContentUnit，并且必须成对为空或成对有值。`pdf_table` Markdown 和多段 `pdf_figure` caption 属于派生文本，其离散来源区间只在摄取期用于精确遮罩，持久化 offset 保持为空。图片 `image_ocr_region/image_caption` 的 offset 也固定为 `NULL/NULL`；权威来源由不可变 `source_locator_id`、类型化明细和有序 regions 表达。

唯一约束：

```text
unique(asset_id, representation_id, source_locator_id, unit_order, index_version)
```

`source_locator_id` 是必填外键。检索结果不允许在返回 citation 时再靠页字段或 MIME 临时拼 locator。

### 4.4 `content_unit_embeddings`

Embedding 与 ContentUnit 分表，支持同一内容进入不同 embedding space、provider、model 和 version。

关键字段：

- `workspace_id`
- `asset_id -> assets.id`
- `content_unit_id`
- `processing_generation`
- `index_version`
- `is_current`
- `embedding_space -> embedding_spaces.kind`
- `provider / model / version`
- `dimensions`
- `embedding vector(1024)`

唯一约束：

```text
unique(content_unit_id, embedding_space, provider, model, version)
```

当前生产只启用 `text` embedding space。`asset_id`、`processing_generation`、`index_version` 和 `is_current` 是 ANN 过滤所需的持久化投影：摄取成功切代时，旧投影在同一事务失活，目标 generation/index 的向量才标记为 current；失败事务不能留下半切代状态。`is_current` 只表达 generation/index 投影是否属于资产当前链，Asset 的 ready/deleted 状态仍由外层 scope 查询判定。

HNSW 只建立在 `is_current` 行上，并且 Dense ANN candidate CTE 在 embedding 表内直接应用 Workspace、资产范围和 provider/model/version/dimensions 过滤；外层仍保留完整 Asset/Representation/Locator current-chain/type 校验作为 fail-closed 第二道边界。这样旧 generation 的重复向量不会占用 ANN 前缀，同时不改变结果去重、唯一位置补足或 RRF 语义。当前 cosine HNSW 使用 `ef_construction=512`。Owner 已批准增加 `binary_quantize(embedding)::bit(1024)` 的 current-only Hamming expression HNSW；两路候选按 embedding identity 去重后，必须使用原始向量 cosine distance 精确重排，binary distance 不得作为最终排名或 Evidence 语义。该索引只增加可重建的数据库索引，不增加持久化业务字段。lexical 路径使用 `content_units.search_vector` 的 FTS GIN 与 `text_content` 的 trigram GiST 索引。`search_vector` 是 generated stored column，禁止由应用写入，保留 `ts_rank_cd`、候选窗口和范围过滤语义不变。

`f2a4c6e8b0d1` 还安装 statement-level trigger：只有 `is_current=true` 的 embedding projection 必须同时匹配 ContentUnit、Representation、Locator 与 Asset 的 Workspace、generation 和 index；inactive 历史行允许保留用于回滚/诊断。摄取的事务顺序固定为“写 inactive -> latest job CAS -> 切换 Asset current generation/index -> 激活目标 provider 投影”，避免 trigger 在切代中间拒绝合法新 generation。该迁移会 drop/recreate HNSW，部署必须安排维护窗口，不作零停机承诺。

## 5. 模态类型目录

类型目录不是动态插件市场，而是部署期闭集的数据库镜像。

### 5.1 当前 Asset 类型

- `pdf`
- `image`
- `document`
- `html`
- `docx`
- `xlsx`
- `pptx`
- `audio`
- `video`

以上九类在当前 `m7a8b9c0d1e2` 目录迁移中启用。

### 5.2 当前 Representation 类型

PDF：

- `pdf_text_legacy`
- `pdf_page_layout`
- `pdf_ocr`
- `pdf_table`
- `pdf_figure`

Image：

- `image_oriented`
- `image_ocr`
- `image_caption`

### 5.3 当前 ContentUnit 类型

PDF：

- `pdf_text_chunk`
- `pdf_ocr_region`
- `pdf_table`
- `pdf_figure`

Image：

- `image_ocr_region`
- `image_caption`

### 5.4 当前 Locator 类型

- `pdf_page -> spatial`
- `pdf_region -> spatial`
- `image_region -> spatial`

每种类型都有 `contract_version`。修改既有 kind 的含义不是普通代码改动，必须新版本或新 kind，并同步迁移、schema、renderer 和 fixture。

## 6. 模态表示表

### 6.1 `pdf_pages`

每行属于唯一 `(asset_id, representation_id, page_number)`。

字段分为三组：

- 页面身份：`asset_id / representation_id / page_number`
- 页面几何：MediaBox、CropBox、rotation、display width/height
- 当前文本能力：`extracted_text / char_count / legacy_ocr_blocks`

`legacy_ocr_blocks` 只服务扫描 PDF 透明选区层；同一 OCR 输出同时写入类型化 `pdf_region` locator/region 与 `pdf_ocr_region` ContentUnit，不把新的 Evidence 合同塞入 legacy JSON。原生文本仍只保留一套 `pdf_text_chunk`，避免重复 embedding 和检索候选。

### 6.2 `image_representation_geometry`

以 `representation_id` 为主键，保存：

- `asset_id`
- `width_pixels`
- `height_pixels`
- `orientation_applied`

图片区域坐标只针对已应用方向归一化的 `image_oriented` representation 解释，不能直接绑定原始 EXIF 坐标。`orientation_applied=true` 表示该 representation 已进入规范方向坐标系，包括缺少 EXIF 或 Orientation=1 的输入；读取当前 Asset detail 必须同时过滤 `image_oriented` 和 `current_processing_generation`，不能按 UUID 或“第一条”猜代次。locator 的 `representation_id_snapshot` 则指向支持该区域结论的 `image_ocr` 或 `image_caption`；Viewer 必须用同一 locator 的 `processing_generation_snapshot` 精确解析对应 `image_oriented`。

## 7. Evidence Locator

### 7.1 `evidence_locators`

共享 header 保存：

- `id`
- `workspace_id`
- `asset_id`
- `locator_kind -> locator_types.kind`
- `locator_version`
- `processing_generation_snapshot`
- `representation_id_snapshot`
- `created_at`

header 不包含 PDF 页码或图片尺寸。共享内核不按 modality 分支解释空间细节。

### 7.2 `pdf_locator_details`

保存：

- `locator_id`
- `page_id nullable`
- `page_number`
- `coordinate_space nullable`
- CropBox、rotation、display width/height 快照

`pdf_page` 只要求页码；`pdf_region` 还要求完整几何快照。删除当前 `pdf_pages` 后 `page_id` 可变为 null，但页码和几何快照保留。

### 7.3 `image_locator_details`

保存：

- `locator_id`
- `coordinate_space`
- `width_pixels / height_pixels`
- `orientation_applied`

### 7.4 `spatial_locator_regions`

一个 locator 可以有多个按 `region_order` 排序的区域。

约束：

- `unique(locator_id, region_order)`
- 所有坐标归一化到 `[0,1]`
- `width/height > 0`
- 区域不得超出边界

多区域顺序是合同的一部分，不能按面积或坐标重新排序。

## 8. Chat 与历史快照

### 8.1 `message_retrieval_scopes`

每条用户消息最多一行 scope header：

- `message_id`
- `workspace_id`
- `scope_mode IN ('all_ready', 'selected')`

### 8.2 `message_retrieval_scope_assets`

保存服务端解析后实际使用的 Asset：

- `message_id`
- `asset_id`
- `asset_order`
- `asset_kind_snapshot`
- `asset_title_snapshot`

约束：

- 主键 `(message_id, asset_id)` 防重复
- `unique(message_id, asset_order)` 保留确定顺序

前端选择状态不是历史真相；历史重放必须读取消息范围快照。

### 8.3 `message_citations`

Citation 保存：

- 消息内顺序：`message_id / citation_index`
- Evidence 身份：`evidence_locator_id / asset_id`
- 显示快照：`asset_kind_snapshot / asset_title_snapshot / excerpt_snapshot`
- 版本快照：`processing_generation_snapshot / representation_id_snapshot / parser_version_snapshot / index_version_snapshot`

Citation 不保存“当前 page/chunk”。重索引可以替换 ContentUnit，但不得更新历史 citation。图片 `representation_id_snapshot` 冻结 OCR/caption Evidence Representation；显示像素仍由相同 `processing_generation_snapshot` 下的 `image_oriented` 提供。

## 9. Notes 与 Tags

### 9.1 `note_sources`

NoteSource 保存和 Citation 同形的 Asset/Evidence/版本快照，并可选关联 `message_citation_id`。

约束：

- `unique(note_id, message_citation_id)` 防止同一来源重复保存
- `(note_id, source_order)` 索引支持稳定展示顺序

Citation 后续删除或源 Asset 软删除时，NoteSource 自身仍可读；API 只把 `sourceAvailable` 置为 false。

### 9.2 `asset_tags` 与 `note_tags`

继续使用两张显式关系表，不使用泛型 `tag_bindings(target_type, target_id)`：

- 外键约束更强
- Workspace 过滤直接
- 删除和查询语义明确

## 10. Research 与 Evaluation 账本

Research 表按职责分为四组：

1. immutable versions/snapshots：Workflow、Prompt、PlanRevision、ExecutionSnapshot 与冻结 Asset/Prompt bindings；
2. mutable execution ledger：Run、Step、Attempt、Event、Decision、Retry、provider/tool call 与 BudgetLedger；
3. immutable outputs：Artifact bytes metadata、Claim、Evidence snapshot/handle 与 exact provenance mappings；
4. independent Evaluation：trusted importer 写入 append-only suite/run/case/claim rows，浏览器仅 owner 可读。

**当前 owner 事实（须三分开写，不得混称）：**

- **Schema / migration owner**：API package（Alembic + ORM 定义在 `apps/api`）。
- **Mutation logic owner**：API Research/ingestion service 实现（锁序、状态机、保存语义）；Worker 不另起一套 ledger schema。
- **Session / commit process owner（Research）**：Worker `_ApiPort` **当前**创建 Session，并在 write 路径 `commit`/`rollback`（见 `apps/worker/src/ai_pdf_worker/research_runtime_core.py`）。因此“API 拥有 mutation logic 定义”不等于“API 进程独占 runtime commit”。
- **Ingestion**：API `process_ingestion_job` 编排 job，并把同一 SQLAlchemy `Session` / ORM `Asset` 传入 Worker adapter；模态行写入发生在该共享会话边界内。

Worker 通过 service ports 调用账本 mutation 函数，不直接定义 ORM 或 migration。Package staging is A1 contracts -> A1b/A2-foundation persistence mappings -> A2a Research persistence behavior; A2a now has an implementer-complete package and compatibility facades, with independent Critical review pending. 当前 Research 多行 mutation 的锁获取顺序仍然混合：Worker attempt paths 多为 `Attempt -> Step -> Run`，claim 为 `Step -> Run`，API cancel/retry/decision paths 为 `Run -> Step`；claim-vs-cancel 存在反向死锁环。A2a 保持当前行为，R0 才将目标顺序统一为 `Run -> Step -> Attempt -> Call -> Ledger`，并要求真实 PostgreSQL `pg_locks`/timeout 证据。上述 ORM/mutation/session runtime boundary migration 属于架构跟进（见 `api-worker-boundary-follow-up-2026-08-18.md`）：A1 contracts implementation 已于 2026-08-20 独立 ACCEPT；A1b/A2-foundation 已于 2026-08-21 独立 ACCEPT（follow-up Critical review：High=0、Medium=0、Low=0）；A2a 已由实现者完成，独立 Critical review 待进行；R0/R1/R2/W1 仍未实现并保持 blocked。ORM/mutation/session boundary migration 属于 A1b/A2a/R0 及后续切片。No schema/API/save/replay/permission changes are authorized；A1b follow-up Critical review 已 ACCEPT，A2a 独立 Critical review 待进行，后续切片仍须各自通过命名 gate。

完整字段、状态、唯一键和删除/保留语义以获批 V4 data contract、Alembic migration 与 ORM 为准；本文件不重复复制 30 余张表的字段清单。运行边界见 `research-workflow-runtime.md`。

## 11. Job 与删除语义

### 11.1 `ingestion_jobs`

关键字段：

- `asset_id`
- `job_type`
- `status`
- `attempt_count`
- `config_snapshot`
- `error_code / error_message`
- `requested_by_user_id`
- `queued_at / started_at / finished_at`

`config_snapshot` 冻结 chunk/embedding 等运行配置；Worker 不应在执行历史 job 时无条件读取最新 Workspace 配置。

### 11.2 删除

删除分两步：

1. API 将 Asset 置为 `deleting` 并创建 `delete_cleanup` job。
2. Worker 删除 MinIO 原对象、当前 ContentUnit/Embedding 与 PDF page，随后设置 `deleted_at` 和 `status=deleted`。

Asset 身份、Representation、EvidenceLocator、Citation 与 NoteSource 快照保留。`pdf_locator_details.page_id` 在页面删除后可为 null；这正是历史页码快照与当前页面实体分离的原因。

## 12. Workspace 隔离

数据库外键不能单独证明两个资源属于同一 Workspace，因此 service/query 层必须同时约束：

```text
child.workspace_id = :workspace_id
asset.workspace_id = :workspace_id
locator.workspace_id = :workspace_id
```

Chat scope、Citation -> Note、Tag binding、Job、Viewer、Research 与 Evaluation 查询都必须执行该检查。禁止仅凭全局 UUID 命中后返回资源。

## 13. 迁移与恢复 oracle

Phase 1 已验证：

- legacy PDF -> Asset/Representation
- legacy page/OCR -> PdfPage
- legacy chunk/vector -> ContentUnit/Embedding
- legacy citation/note source -> `pdf_page` locator + 不可变快照
- document tag/job -> asset tag/job
- 旧 Document 表不存在
- PostgreSQL custom `pg_dump` -> 空库 `pg_restore --single-transaction` 后 Asset/Evidence/Citation/NoteSource payload 全等

Phase 4 已完成：

- 销毁卷后的 PostgreSQL + MinIO 同批恢复
- 图片与版本化 Representation 对象字节 SHA-256
- `pdf_region/image_region` 数量、顺序、几何和 Viewer 像素定位
- 历史页、区域、已删除源 citation 与 NoteSource 全链路回放

V4 R800 v4 已验证：

- legacy 到 `e8f1a2b3c4d5` 的完整 Alembic upgrade；
- Research Run/Step/Event/Decision/Claim/Evidence/provider/tool/budget 与 Evaluation 行快照；
- MinIO plan/checkpoint/conflict/final Artifact bytes/hash；
- 销卷后空部署 restore 的前后语义 SHA 全等；
- 最终容器、卷、网络和 secret env 零残留。

## 14. 变更门禁

以下变化必须先获得明确合同批准：

- 修改持久化字段含义、save payload 或删除语义
- 修改 locator kind/version/coordinate space
- 修改 Citation/NoteSource 快照字段
- 修改消息实际 Asset 范围的保存方式
- 修改 Embedding space 或向量维度
- 为新模态启用数据库目录、Worker adapter 或 Web renderer
- 修改 Research lock order、budget/save semantics、Workflow/Prompt version 或 Evaluation append-only 语义

批准后必须同步 Alembic、ORM、Pydantic schema、API fixtures、Worker/Web 调用方、单元测试、恢复 oracle 与本文件。
