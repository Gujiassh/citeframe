# 任务状态机设计

> 文档状态：V1 历史状态机设计。本文保留早期 `Document`/`/documents` 任务流的推导，当前 Asset/Representation/ContentUnit、Image adapter、generation/CAS、`ingestion_jobs` 和 delete cleanup 合同以 `docs/architecture/database-design.md`、`docs/architecture/api-contracts.md`、`apps/worker/README.md` 与 `docs/architecture/implementation-progress.md` 为准。修改当前任务状态时必须先更新当前合同，不要直接照抄本文旧接口。

## 1. 文档定位

这份文档定义：

- 文档入库相关状态如何流转
- `documents.status` 和 `ingestion_jobs.status` 的职责如何区分
- 初次入库、失败重试、重建索引、删除清理分别如何建模

当前范围覆盖 `原始 PDF 阅读 + 文本检索主链`，扫描 PDF 的 OCR 作为 ingest Worker 内部 fallback，不单独建状态机。

## 2. 设计目标

当前状态机设计需要满足：

1. 前端能清楚知道文档当前是否可用
2. 后端能清楚记录每一次任务的执行过程
3. 初次入库和重建索引不能混为一谈
4. 失败后能够重试
5. 删除动作能被追踪，而不是直接“消失”

## 3. 为什么需要两层状态

系统里必须同时有：

- `documents.status`
- `ingestion_jobs.status`

它们不是重复字段，而是两种不同语义。

### 3.1 `documents.status` 是什么

它代表：

- 这份文档当前对用户来说处于什么可用状态

例如：

- 还没处理完
- 已经可以检索
- 当前失败
- 正在删除

它回答的是：

- “这个文档现在能不能用？”

### 3.2 `ingestion_jobs.status` 是什么

它代表：

- 某一次具体后台任务执行到哪了

例如：

- 这次 ingest 任务是否在排队
- 这次 `embed_chunks` / reindex 是否执行成功
- 这次 delete cleanup 有没有失败

它回答的是：

- “这次任务现在跑到哪了？”

### 3.3 为什么不能只靠 `documents.status`

因为文档会经历多次任务：

- 第一次入库
- 失败重试
- 后续重建索引
- 删除清理

如果只有一份文档状态，你看不到：

- 失败历史
- 任务类型
- 尝试次数
- 当时使用的处理配置

所以必须把“文档可用状态”和“任务执行状态”拆开。

## 4. `documents.status` 设计

## 4.1 状态列表

当前建议值：

- `pending_upload`
- `uploaded`
- `parsing`
- `chunking`
- `chunked`
- `embedding`
- `ready`
- `failed`
- `deleting`
- `deleted`

## 4.2 状态含义

### `pending_upload`

含义：

- 文档记录已经创建
- 但浏览器还没完成对象存储上传

用户可见性：

- 不可检索
- 不可聊天

### `uploaded`

含义：

- 文件已经存在于对象存储
- 任务已经可以开始或已入队

用户可见性：

- 不可检索
- 可看到“处理中”

### `parsing`

含义：

- Worker 正在解析 PDF 文本

### `chunking`

含义：

- Worker 正在根据页面文本生成 chunk

### `embedding`

含义：

- Worker 正在调用 embedding provider 并写入向量

### `chunked`

含义：

- 页面和文本块已持久化
- 当前可以供 Viewer 读取页面文本
- 尚未生成检索向量，不能作为问答检索来源

### `ready`

含义：

- 文档当前在线索引已经可用
- 用户可以浏览、检索、问答引用

### `failed`

含义：

- 最近一次入库主任务失败
- 失败原因通过 `error_code` / `error_message` 保存，例如 `ocr_failed` 或 `no_extractable_text`
- 当前没有可用在线索引

### `deleting`

含义：

- 文档正在被删除清理
- 用户侧不应继续操作
- 删除清理失败时仍保留该状态，并通过最近一次 `delete_cleanup` 任务的错误信息展示重试入口

### `deleted`

含义：

- 文档逻辑上已被删除
- 后续可由清理任务做最终回收

## 4.3 状态语义规则

1. `ready` 是唯一“当前可用”状态
2. `embed_chunks` 负责给已有页面/chunk 批量补写向量；初次 `ingest` 也会在切块后执行同一 embedding 阶段
3. 初次入库的 `failed` 表示当前没有可用在线索引；`embed_chunks` 失败时先回滚事务，已有完整索引则保留 `ready`
4. `deleting` 表示进入删除流程后，前端应把文档视为不可用
5. `deleted` 主要用于软删语义，不是前端常态展示状态

## 5. `ingestion_jobs.status` 设计

## 5.1 任务类型

当前建议：

- `ingest`
- `embed_chunks`
- `delete_cleanup`

## 5.2 任务状态值

当前建议：

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`

## 5.3 任务状态含义

### `queued`

- 已创建
- 尚未开始执行

### `running`

- Worker 已取到任务并开始执行

Embedding job 执行前会校验任务快照中的 provider、model、dimensions、version；配置漂移会让 job 显式失败，不会写入与当前检索配置不一致的向量。

### `succeeded`

- 任务成功完成

### `failed`

- 任务失败
- 应附带 `error_code` 和 `error_message`

### `cancelled`

- 任务被人工或系统取消

## 6. 初次入库状态机

## 6.1 主流程

```text
pending_upload
  -> uploaded
  -> parsing
  -> chunking
  -> chunked
  -> embedding
  -> ready
```

## 6.2 失败流

```text
parsing  -> failed
chunking -> failed
embedding -> failed
```

## 6.3 对应任务状态

初次入库时会有一个 `job_type=ingest` 的任务：

```text
queued -> running -> succeeded
```

失败时：

```text
queued -> running -> failed
```

## 6.4 关键规则

1. 初次入库过程中，`documents.status` 跟随处理阶段变化
2. 只有 `ready` 才表示这份文档可进入检索与问答
3. 一旦任务失败，`documents.status` 必须进入 `failed`
4. `documents.latest_ingestion_job_id` 应始终指向最近一次主任务

## 7. 重试状态机

## 7.1 触发条件

当文档状态为：

- `failed`

并且用户执行“重试”时：

1. 创建一个新的 `ingest` 任务
2. 增加 `attempt_count`
3. 文档重新进入处理链

## 7.2 主流程

```text
failed
  -> uploaded
  -> parsing
  -> chunking
  -> embedding
  -> ready
```

## 7.3 关键规则

1. 重试不是复活旧 job，而是新建一条 job 记录
2. 失败历史必须保留
3. 文档是否恢复可用，仍以 `documents.status=ready` 为准

当前实现：`POST /documents/{documentId}/retry` 会新建 `job_type=ingest` 任务，保留原失败任务记录，按同一文档历史最大 `attempt_count + 1` 写入新任务，并清除文档上的最近错误信息。

## 8. 重建索引状态机

这是最容易设计错的一块。

## 8.1 为什么重建索引不能直接把文档重新置为 `parsing`

因为重建索引时，很多文档本来已经 `ready`，用户还在用它。

如果重建索引一开始就把 `documents.status` 改回 `parsing`：

- 用户会突然看见文档不可用
- 当前在线索引会被错误地当成失效
- 体验很差

## 8.2 正确设计

对于用户触发的 reindex 动作（当前实现为 `job_type=embed_chunks`）：

- 文档在 job 排队期间保持 `ready`
- 新建一条 `embed_chunks` job；Worker 开始运行时把文档置为 `embedding`
- 当前 V1 不维护 shadow 向量，运行期间检索暂时等待；Worker 在当前 chunk 版本上批量更新向量
- 成功后回到 `ready`；失败时事务回滚，旧向量存在则恢复 `ready`，否则恢复 `chunked`

当前 V1 在现有 `current_index_version` 上事务性替换向量；未来引入并行索引版本后再做成功切换。

## 8.3 主流程

```text
Document stays: ready while queued
Reindex job: queued -> running -> succeeded
After success: current chunk vectors are replaced
```

## 8.4 失败流

```text
Document keeps its previous usable state after rollback
Reindex job: queued -> running -> failed
Previous vectors remain unchanged
```

## 8.5 关键规则

1. V1 重建索引排队时不让当前文档下线；运行期间暂时进入 `embedding`
2. V1 在现有在线索引版本上事务性替换向量，未来并行索引版本只有完全成功后才切换
3. reindex 失败不能把已有完整向量的文档误标成 `failed`

## 9. 删除状态机

## 9.1 为什么删除不是同步动作

删除文档不只是删一行 `documents` 记录。

还涉及：

- page/chunk 数据清理
- citation 关系保留策略
- 对象存储文件删除
- 失败补偿

所以删除必须建成异步动作。

## 9.2 主流程

```text
documents.status: ready|chunked|failed -> deleting -> deleted
job_type=delete_cleanup: queued -> running -> succeeded
                              -> failed -> queued (owner retry)
```

## 9.3 关键规则

1. 一旦进入 `deleting`，前端应把该文档视为不可操作
2. 清理过程中失败时，删除任务进入 `failed`，文档保持 `deleting` 并保存错误
3. 只有 workspace owner 可以发起删除或重试失败的清理任务
4. 文档主记录是否立即隐藏，由前端列表策略决定，但业务上不应继续让它参与检索

当前实现：删除接口返回 `202 Accepted`，只把文档置为 `deleting` 并创建 `delete_cleanup` job；Worker 负责幂等删除对象存储、`document_pages`、`document_chunks`，全部成功后才写入 `deleted_at` 和 `deleted`。清理失败时 `POST /documents/{documentId}/delete-retry` 会保留失败历史并重新排队。

## 10. 前端如何消费这些状态

## 10.1 文档列表

前端主要看：

- `documents.status`
- `last_error_message`

用于展示：

- 正在上传
- 正在解析
- 正在切块
- 正在向量化
- 可用
- 失败
- 正在删除

## 10.2 Job 详情 / 轮询

前端在需要展示详细进度时，再查：

- `GET /jobs/:jobId`

主要看：

- `job_type`
- `status`
- `attempt_count`
- `error_code`
- `error_message`

## 10.3 为什么前端不应该只轮询 job

因为用户列表层最关心的是：

- 这份文档现在能不能用

这是 `documents.status` 的职责，不是 `jobs.status` 的职责。

## 11. 关键异常场景

### 场景 1：上传会话创建成功，但浏览器没真正上传文件

处理：

- 文档停留在 `pending_upload`
- 不创建 ingest job
- 可由前端超时清理或用户重新发起上传

### 场景 2：对象存储上传成功，但 finalize 失败

处理：

- 文档停留在 `pending_upload` 或由服务端修正为失败前状态
- 不进入处理链
- 前端应允许再次 finalize 或重传

### 场景 3：embedding 失败

处理：

- 文档进入 `failed`
- job 进入 `failed`
- 保留错误原因，允许 retry
- 只有所有当前 chunk 都有完整向量和 provider 元数据时，文档才会恢复为 `ready`；部分索引恢复为 `chunked`

### 场景 4：reindex 失败

处理：

- 排队期间现有文档仍保持 `ready`
- Worker 运行期间文档进入 `embedding`，当前 V1 没有 shadow 索引，检索暂时等待
- 只有 reindex job 失败

### 场景 5：删除时对象存储清理失败

处理：

- delete_cleanup job 标记 `failed`
- 文档保持 `deleting` 或进入明确的恢复策略
- 不应让它重新回到可检索状态

## 12. 当前状态机边界

这份状态机设计当前不覆盖：

- 独立 OCR 流程状态（OCR fallback 复用 ingest 的 `parsing -> chunking` 状态）
- 多模态页面理解状态
- 批量导入多个文档的聚合状态
- 多 worker 竞争同一文档的并发控制细节

这些可以在后续扩展时单独加层，不应该现在压进主线。


## 2026-07-15 可靠性补充

- Worker 主循环只对进程级基础设施异常做有限指数退避；连续 5 次失败后以非零状态退出，由外部进程管理器重启。
- PDF/OCR/embedding 业务失败仍由 `process_ingestion_job` 写入 `failed`，Worker 不会自动把已失败业务任务复活。
- 任务领取后的 `running` lease 仍由 API 的 15 分钟回收逻辑兜底；进程在同步 OCR/embedding 中被终止时，不承诺立即更新状态。
- `config_snapshot.chunkSize` 是本次 ingest 的切块配置快照；旧任务没有该字段时按历史默认 1200 处理。
