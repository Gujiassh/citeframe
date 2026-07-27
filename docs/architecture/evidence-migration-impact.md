# Evidence 合同迁移影响设计
## 状态

- 状态：Implemented，Phase 1 受控迁移已完成
- 实施授权：六项合同裁决已批准
- 当前影响：生产运行时已统一到 Asset/Evidence；后续变更继续遵守本文件的历史语义和恢复门禁

## 1. 已执行迁移边界

迁移已经按以下不变量执行：

- `documents / document_pages / document_chunks / document_tags` 已一次性迁移并移除；`message_citations / note_sources` 保留历史显示语义但改为不可变 locator 快照
- Chat 历史响应和 Chat SSE citation 已切换为 Asset/Evidence envelope
- `citationIndex` 与正文 `[n]` 映射
- citation -> note 的 Workspace 校验与完整 locator/sourceVersions 快照复制
- Viewer 的 `assetId + locator` 跳转
- Asset 删除、重索引和历史来源回放
- PostgreSQL/MinIO 备份恢复格式

## 2. 迁移前语义 oracle

| 场景 | 当前必须保持的结果 | 证据 |
| --- | --- | --- |
| 读取历史 Chat | Citation 标题、页码、摘要和编号不变 | `current-citation.json` + API fixture |
| 流式完成回答 | citation 在 `done` 前持久化，刷新后结果一致 | SSE 事件记录 + DB 快照 |
| Citation 转 Note | 只接受当前 Workspace citation，并复制标题、页码和摘要 | `current-note-source.json` + payload/DB 对照 |
| 重索引 | 新 chunk 可替换，旧 citation 快照含义不变 | 重索引前后历史响应比较 |
| 删除文档 | 原对象/page/chunk 可清理，历史 citation/note source 文本仍可读 | 删除前后 API 和 DB 快照 |
| Viewer 跳转 | 有源文件时打开相同文档和 1-based 页码 | Playwright DOM/canvas 证据 |
| 备份恢复 | 用户、Workspace、文档、citation、note source 和对象字节保持一致 | 销卷恢复 + SHA-256 |

## 3. 已执行迁移阶段

以下阶段已在 `c9d1e2f3a4b5` 和对应 API/Worker/Web 切换中执行。

### Stage 0：冻结旧 fixture

- 从真实但脱敏的当前数据库导出 page citation、已删除源 citation 和 citation -> note fixture。
- 保存当前 API、SSE、数据库行和 Viewer 跳转证据。
- 固定 Alembic head、备份格式和应用镜像版本。

### Stage 1：增加 Asset 目标存储

- 已添加 Asset/Representation/ContentUnit/Embedding、locator discriminator/version 和 PDF/Image region 类型化存储。
- 新字段或子表必须有数据库约束，不能以“先放任意 JSON”代替合同。
- 现有 `page_number_snapshot` 在迁移期间继续作为旧语义真相源，除非另有明确裁决。

### Stage 2：机械回填旧记录

- 每条旧 citation 只能映射为 `pdf_page(pageNumber=page_number_snapshot)`。
- 每条现有 Document 必须机械迁移为 `asset_kind=pdf`，禁止按文件名猜类型。
- `document_pages/document_chunks` 分别迁移为 PDF page、文本 ContentUnit 和 Embedding；记录数、顺序、版本和 Workspace 归属逐项比较。
- `document_tags` 迁移为 Asset tag 关系，标签含义不变。
- 禁止从 chunk 文本、OCR block 或当前 parser 结果猜测历史 bbox。
- NoteSource 必须从其自身快照机械回填，不能重新读取当前 Citation 覆盖历史来源。
- 回填前后记录数、Workspace 归属、页码、标题、摘要和 source order 必须逐行比较。

### Stage 3：隔离验证

- 在隔离数据库中使用同一 fixture 从旧模型和 Asset 模型生成响应，仅比较必须保持的不变量。
- 不在生产业务逻辑中引入无期限双读或 fallback chain。
- 只有旧/新结果对照通过后，才能进入受控版本切换。

### Stage 4：写路径与 API 切换

- API、SSE 与前后端类型已经按同一受控版本切换完成。
- 新合同可表达 `pdf_page`、`pdf_region` 或 `image_region`；当前 Worker/Chat 已产出并消费三种 locator，Image 生产启用由 M403B 单独门禁保护。
- Citation -> Note 必须复制 locator 快照，不能只保存关联 ID。
- 切换必须有可执行回滚点和数据库备份。

### Stage 5：删除旧字段和旧运行时

旧 Document 表、字段、API/BFF 路由和 Web 业务类型已在同一版本切换中删除。历史页码没有丢弃，而是机械写入 `pdf_page` locator detail；生产扫描中 `/documents`、`documentId` 和 Document 业务类型为零。

## 4. 回滚要求

### DDL 回滚

- `c9d1e2f3a4b5` 明确不可原地 downgrade；回滚只能恢复迁移前 PostgreSQL/MinIO 同批备份。
- 新区域 citation 或图片 Asset 一旦创建，旧应用无法表达其语义；必须停止写入并受控导出，`image_region` 不能机械降为 PDF 页码。

### 应用回滚

- 回滚版本必须能读取迁移窗口内所有已提交记录。
- 如果旧应用不能理解新 locator，不能仅依赖部署回滚；需要先停止新写入并执行受控数据转换。
- 不提供静默忽略 `pdf_region/image_region` 的 fallback。

### 失败恢复

- 回填必须分批、可重复、带稳定游标和计数，不通过“第一个可用字段”猜含义。
- 单批失败不得留下部分更新；使用事务并记录平面日志 `evidence_backfill batch=... status=...`。
- PostgreSQL 与 MinIO/派生表示若同时变化，必须建立停写窗口或版本切换协议，不能假设跨存储事务。

## 5. API 与客户端影响

当前实现结论：

- Citation 已替换为包含 `assetId/assetKind/locator/sourceVersions` 的稳定对象，SSE 与历史消息同形。
- `pageNumber` 位于 `pdf_page/pdf_region` locator 内，不作为所有模态的公共顶层字段。
- Asset list/upload/retry/delete 已一次性替换 Document endpoint，旧 `/documents` 返回 404。
- Chat `assetScope` 支持 `all_ready | selected`，服务端在检索前校验 Workspace、ready 状态和重复 ID，并持久化实际 Asset 范围快照。
- Web 使用 locator 和 EvidenceModule discriminated registry；未知或畸形 locator 明确合同失败，不猜 renderer。
- 源已删除时保留历史快照并禁止打开 Viewer；`pdf_region` 几何或 representation 不匹配时明确报错，不降级整页。

当前与候选 payload 位于 `docs/fixtures/evidence-contract/`，候选文件仅用于设计对照。

## 6. 删除与重索引影响

- 删除原 PDF/图片后 locator 快照仍保留，但无法再执行视觉高亮；历史界面显示来源已删除，仍展示标题、定位摘要、excerpt 和区域摘要。
- 重索引不得更新历史 locator、excerpt、processing generation、representation 或 parser version 快照。
- 如果源文件不变但 parser 输出变化，新 ContentUnit 可以替换，旧 citation 仍按生成时快照解释。
- 如果源文件内容变化，应创建新资产版本或新文档，不原位复用旧 locator 身份。

## 7. 备份恢复影响

Phase 1 已完成 PostgreSQL 层恢复 oracle，Phase 4 继续扩展完整销卷恢复：

- [x] Asset、Representation、ContentUnit、Embedding 和 locator 主记录逐项一致。
- [x] PDF region 数量、顺序、坐标、几何和版本逐行一致，并进入 custom `pg_dump` / 空库 `pg_restore` payload oracle；Image region 已在 M403B 加入同一门禁。
- [x] Citation 与 NoteSource 的 locator 快照一致。
- [x] 初次 M403 已验证原 PDF/图片和必要版本化 Representation 对象 SHA-256 一致；加强后 M403 将重新确认该不变量。
- [x] 恢复后 Viewer 在相同 PDF/图片 fixture、相同 viewport 下高亮同一区域（M403B restore artifact）。
- [x] 旧 page citation 与新 PDF region Citation/NoteSource 在成功重处理后保持 locator、region、excerpt 和 sourceVersions 快照不变；Image region 已在 M403B 加入历史回放门禁。

备份格式变更需要提高 format version；旧 restore 脚本不得接受未知格式。

## 8. 实施审批结果

Phase 1 已提交并验证：

1. 最终 RFC 决策和 ADR。
2. Alembic upgrade/downgrade 草案与数据回填算法。
3. 当前/候选 API 与 SSE fixture。
4. 历史、删除、重索引、坐标和 Viewer 验收矩阵。
5. 备份恢复变化和破坏性回滚说明。
6. 单元、集成、Playwright 和销卷恢复命令。

Phase 1 的 Alembic、API/SSE fixtures、迁移 oracle、Web runtime 和回滚限制均已落地。后续 Phase 2/3 若改变 locator 几何、持久化字段或保存语义，仍必须重新走合同评审，不能从 UI 需求直接改库。
