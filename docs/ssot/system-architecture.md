# Citeframe 系统架构

## 1. 架构结论

Citeframe 采用 `Web App + API Service + Worker + Data Plane` 的分层架构。

它不是前后端都各管一半业务逻辑的松散组合，而是：

- `Next.js` 负责用户界面、会话鉴权、BFF 网关、流式体验
- `FastAPI` 负责业务 API、Asset/Chat/Research 账本、检索编排与模型调用边界
- `Worker` 负责长任务：解析、切块、embedding、索引、重建索引与固定 Research workflow 执行
- `Postgres + pgvector` 负责业务数据和检索向量
- `MinIO` 负责原始 PDF/图片与处理产物
- `Redis` 当前作为已部署的缓存/队列基础设施预留；业务任务真相源仍是 Postgres `ingestion_jobs`

V1 默认以 `模块化双服务系统` 落地，而不是微服务集群。
原因很直接：

- 前端体验和鉴权边界需要 `Next.js`
- PDF 解析、embedding、检索、后台任务明显更适合 Python
- 继续拆分更多服务会让学习/面试版本过重

## 2. 架构目标

### 2.1 主要目标

- 支撑多 Workspace 的强隔离知识边界
- 支撑 PDF/图片 Asset 的异步入库与索引
- 支撑带引用的 RAG 问答
- 支撑笔记、标签、聊天历史沉淀
- 支撑显式、版本化、可恢复且 Evidence-bound 的深度研究运行
- 支撑本地学习部署和后续云上部署
- 支撑 OpenAI 与本地开源 embedding provider 并存

### 2.2 非目标

V1 架构不追求：

- 多租户企业级 IAM
- 多区域高可用
- 跨 Workspace 联邦检索
- 多模型 Agent 编排平台
- 超高吞吐搜索集群
- 音频、视频和标注数据 Asset

当前运行时已切换到 Asset/Evidence 合同，PDF 与 M403B Image adapter、Evidence、Viewer、区域 Chat/Note 和混合检索均已进入生产 registry 并通过发布门禁。PDF 支持可直接提取文本的页面与无文本层页面的 RapidOCR fallback；Image 只接受 PNG/JPEG/WebP，且不改变 Citation、NoteSource、Chat 或保存语义。

## 3. 顶层架构

### 3.1 逻辑分层

系统分为五层：

1. `Presentation Layer`
   - 浏览器
   - Next.js Web App

2. `Application Gateway Layer`
   - Next.js BFF Route Handlers / Server Actions
   - 会话校验、workspace 上下文注入、流式转发

3. `Domain Service Layer`
   - FastAPI Business API
   - Retrieval / Chat / Asset / Notes / Tags / Prompt / Research / Evaluation API

4. `Async Processing Layer`
   - Worker
   - Modality Parse / ContentUnit / Embed / Reindex / Cleanup 任务

5. `Data & Model Layer`
   - Postgres + pgvector
   - MinIO
   - Redis
   - OpenAI / Ollama / 本地模型运行时

### 3.2 服务清单

#### `web`

Next.js 应用。
职责：

- 页面渲染
- 用户登录态维护
- Workspace 切换 UI
- Chat / Asset List / Evidence Viewer / Notes / Tags 交互
- 作为浏览器唯一应用/BFF 边界，由 Caddy 在公网侧反向代理

#### `api`

FastAPI 主业务服务。
职责：

- Workspace、Asset、Note、Tag、Thread、Prompt 业务 API
- 上传 finalize
- 检索编排
- Chat 编排
- 引用结构生成
- 对 Worker 投递任务
- Research Run/Step/Event/Decision/Artifact 与 provider/tool/budget 账本
- owner-only Evaluation API 与可信离线导入边界

#### `worker`

后台异步任务服务。
职责：

- PDF/Image adapter
- Representation 与 ContentUnit 生成
- embedding 写入
- 索引重建
- 文档删除后的异步清理
- 固定 Planner/Researcher/Verifier/Critic/Synthesizer/Publisher 执行

#### `postgres`

唯一主业务数据库。
职责：

- 业务真相源
- pgvector 检索
- 任务状态持久化
- Research/Evaluation 业务账本、事件序号与版本化执行快照

#### `minio`

对象存储。
职责：

- 原始 PDF 文件
- 页面预览图
- 解析中间产物
- immutable Research plan/checkpoint/conflict/final Artifact bytes

#### `redis`

缓存与任务中间层。
职责：

- 任务队列
- 检索短缓存
- 限流计数
- 任务状态热点缓存

#### `model providers`

- OpenAI Responses API：问答与结构化输出
- OpenAI Embeddings：V1 默认托管 embedding provider
- Ollama `qwen3-embedding:0.6b`：本地 embedding provider
- 后续可选 reranker provider

## 4. 前端架构

### 4.1 组成与组件划分

前端采用 `Next.js App Router + React Context Provider + feature hooks + Tailwind CSS + Lucide Icons`。Provider 只暴露稳定的 WorkspaceContext API；Workspace、Assets、Chat、Notes/Tags 和视图状态分别由 feature hooks/纯工具模块承载。

1. `Shell & Navigation`
   - [WorkspaceSidebar](../../apps/web/src/components/workspace-sidebar.tsx)：折叠/抽屉式导航栏。
   - [CreateWorkspaceDialog](../../apps/web/src/components/create-workspace-dialog.tsx)：工作区创建 Modal 对话框。
   - [WorkspaceList](../../apps/web/src/components/workspace-list.tsx)：主门户 100% 宽度 cardless 行列表。

2. `Evidence Workspace UI`
   - [EvidenceViewer](../../apps/web/src/components/evidence-viewer.tsx)：通过 production Evidence registry 按 Asset 类型调度 `PdfEvidenceRenderer` 或 `ImageEvidenceRenderer`，共享 citation/note Evidence shell。
   - [PdfEvidenceRenderer](../../apps/web/src/components/pdf-viewer.tsx)：组合 PDF.js 页面 canvas、原生文本层、annotation layer 和类型化区域高亮，保留图片、排版与 PDF 内置链接。
   - [ImageEvidenceRenderer](../../apps/web/src/components/image-viewer.tsx)：显示图片 Representation，并按 `image_region` locator 渲染区域证据。
   - [OutlineTree](../../apps/web/src/components/outline-tree.tsx)：PDF 章节目录大纲树，使用 `activeAssetId` 参与节点 Key，避免切换 Asset 后复用旧折叠节点。
   - [SelectionPopover](../../apps/web/src/components/selection-popover.tsx)：划词即时问答/记录笔记浮空菜单。

3. `Knowledge UI`
   - [ChatPanel](../../apps/web/src/components/chat-panel.tsx)：流式问答管理器。
   - [ChatBubble](../../apps/web/src/components/chat-bubble.tsx)：对话气泡与行内快速笔记沉淀面板。
   - [ChatMarkdown](../../apps/web/src/components/chat-markdown.tsx)：助手 Markdown/GFM 渲染和 citation `[n]` 内联引用映射；只允许 `http/https` 外链。
   - [NotesPanel](../../apps/web/src/components/notes-panel.tsx)：沉淀笔记仓库。
   - [SettingsPanel](../../apps/web/src/components/settings-panel.tsx)：Prompt 参数调优。

4. `BFF & Data Layer`
   - Next.js BFF 路由转发。
   - [workspace-context.tsx](../../apps/web/src/lib/workspace-context.tsx) 只做 Provider 组合；数据域分别位于 `use-workspaces.ts`、`use-assets.ts`、`use-chat.ts`、`use-notes-tags.ts`，视图状态位于 `workspace-view-state.ts`。

### 4.2 前端自适应布局引擎 (Responsive Drawer Engine)

采用纯 CSS Breakpoints 实现大屏并排、小屏绝对定位浮出抽屉：
* 屏幕宽幅 $\ge 1024px$ 时：侧边栏与问答板在水平方向并排展示（`lg:relative`）。
* 屏幕宽幅 $< 1024px$ 时：侧边栏与问答面板自动重映射为 `absolute` 绝对定位浮层，增加半透明毛玻璃蒙层（Backdrop Blur overlay）控制点击外部空白区自动闭合抽屉，避免挤压中间阅读视窗。
* 屏幕宽幅 $< 768px$ 时：窄轨图标边栏被 `hidden md:flex` 隐藏，为手机屏幕腾出 100% 显示宽度。

### 4.3 状态划分与解析防御 (State & Sandbox Serialization)

前端状态分类与持久化定义：

1. `Server State`
   - Workspace、资产、任务、会话、笔记、标签和设置均以 FastAPI/Postgres/MinIO 为真实来源；Provider hydrate 后只保留当前页面运行时状态，不把业务数据写入 LocalStorage。
2. `Local UI Preferences`
   - 主题和语言可以写入 LocalStorage，因为它们不属于业务数据；不能用同一机制缓存 Workspace、文档、Chat 或设置。
3. `UI Runtime State`
   - 当前资产、PDF 页码、划词/框选草稿、缩放、平移和侧栏折叠状态。
   - Chat 消息列表是否跟随流式输出：用户在底部时自动跟随，主动上滑后保留用户阅读位置。
4. `Micro-Interaction Animations`
   - **纸张更新**：`activePdfPage` 作为 Content Key，翻页时触发 `animate-in fade-in` 动效。
   - **引用聚焦**：点击回答内联或来源列表中的 Citation 时打开对应文档并跳到快照页，阅读区平滑回到页面顶部，原始 PDF 页面短暂显示 `.animate-citation-pulse` 黄金脉冲。
   - **气泡滑入**：新对话产生时，组件以滑入渐显入场。

## 5. 后端架构

### 5.1 FastAPI 作为唯一业务后端

FastAPI 是业务 API 的单一实现层，不把一半业务逻辑留在 Next.js。

这样做的好处：

- 避免 JS/Python 各自维护一套文档逻辑
- 后续 Worker 与 API 可共享领域模块
- 检索、引用、笔记来源关系都在一处定义

### 5.2 后端模块拆分

#### `workspace service`

职责：

- Workspace CRUD
- Workspace 概览统计
- Workspace Prompt 配置
- Workspace membership / role 校验结果消费

#### `asset service`

职责：

- Asset 列表、详情、源文件与上传会话
- 上传流接收、校验、finalize 和状态流转
- 失败重试、重建索引、异步删除和清理重试
- 当前或冻结 generation 的 Representation、ContentUnit 和 Evidence 读取边界

#### `ingestion orchestrator`

职责：

- 创建 ingestion job
- 投递解析任务
- 更新状态机
- 触发 embed/index 任务

#### `retrieval service`

职责：

- query embedding
- pgvector Dense 相似度召回
- PostgreSQL lexical 候选：拉丁术语使用 FTS GIN，纯中文使用 pg_trgm GiST KNN
- 稳定 RRF 融合：页级 locator 按 Asset+页去重，区域 locator 保持独立
- 消息实际 Asset scope 与标签过滤
- 可选 rerank
- 返回引用片段候选

#### `chat orchestrator`

职责：

- 装配 Workspace Prompt
- 装配检索上下文
- 调用 Responses API
- 生成回答与 citation 结构
- 保存 thread/message/citation

#### `notes & tags service`

职责：

- 笔记 CRUD
- citation -> note
- 标签 CRUD
- 标签绑定与筛选

#### `provider adapters`

职责：

- OpenAI Responses 适配
- OpenAI Embeddings 适配
- Ollama/Qwen Embeddings 适配
- 后续 Rerank 适配

### 5.3 Worker 架构

Worker 是独立进程，不与 API 共用请求生命周期。

Worker 任务：

- `ingest`
- `embed_chunks`
- `delete_cleanup`

当前已实现：Worker 通过 Postgres 轮询领取 `ingestion_jobs.status=queued` 的上述三类任务。`ingest` 由共享 ingestion service 按 `asset.asset_kind` 从 Worker 的 `IngestionAdapterRegistry` 选择 `PdfIngestionAdapter` 或 `ImageIngestionAdapter`；共享层负责编排 job、processing generation、事务、embedding 和失败状态，模态 adapter 负责生成对应 Representation、ContentUnit 与 locator。PDF 路径持久化 `pdf_page_layout/pdf_ocr/pdf_table/pdf_figure` Representation、canonical `pdf_pages`、`pdf_page/pdf_region` locator 和 ContentUnit；Image 路径生成 image-oriented Representation、`image_region` locator 和对应 ContentUnit。`embed_chunks` 激活当前 generation/index 的 embedding 投影，`delete_cleanup` 清理源对象、派生对象和内容记录。检索以 Workspace、ready、未删除、当前 index version 和 provider metadata 为硬边界，分别取得 Dense 与 PostgreSQL lexical 候选；`pdf_page` 按 Asset+页去重，区域 locator 保持独立，再执行 RRF。Chat API 将候选交给 Responses API，转发 delta 流并持久化 immutable locator/sourceVersions citation；citation -> note 只接受当前 Workspace 的真实 citation，并复制完整 locator 与展示快照。

### 5.4 任务编排方式

目标架构采用：

- `Redis queue + Worker`
- `Postgres ingestion_jobs` 作为最终状态记录

即：

- 队列负责调度
- 数据库负责真相状态
- Redis 宕掉后可重新投递
- Postgres 仍保留任务最终结果与失败原因

当前实现采用 Postgres 轮询作为最小可运行调度：Worker 用 `FOR UPDATE SKIP LOCKED` 领取 queued job，再把 `running/succeeded/failed` 状态写回同一事务边界。Redis 队列会在重试、延迟任务和横向扩展进入主线时接入；当前不保留一套未使用的双队列逻辑。

## 6. 数据库架构

### 6.1 数据库选型

主数据库：`Postgres`

原因：

- 关系模型适合 Workspace / 文档 / 聊天 / 笔记 / 标签
- `pgvector` 足够支撑 V1 检索
- 运维复杂度比额外引入向量专用库更低

### 6.2 数据分层

数据库中存在四类数据：

1. `Identity & Auth Context`
   - users
   - sessions
   - workspace_memberships

2. `Knowledge Assets`
   - workspaces
   - assets
   - asset_representations
   - pdf_pages
   - content_units
   - content_unit_embeddings
   - evidence_locators 与模态类型化 detail/region 表
   - ingestion_jobs

3. `Conversation & Knowledge Capture`
   - chat_threads
   - chat_messages
   - message_citations
   - notes
   - note_sources
   - tags
   - asset_tags
   - note_tags

4. `Provider Metadata`
   - embedding_model
   - embedding_dimensions
   - embedding_provider
   - embedding_version

### 6.3 数据隔离原则

所有业务核心表都必须带 `workspace_id`，并遵守：

- 所有查询先按 `workspace_id` 过滤
- 所有缓存 key 带 `workspace_id`
- 所有对象存储路径带 `workspace_id`
- 所有检索操作先过 workspace 边界

### 6.4 向量存储原则

`content_units` 是检索内容主表，`content_unit_embeddings` 保存可重建向量投影。

每条 ContentUnit 至少保存：

- `workspace_id`
- `asset_id`
- `representation_id`
- `source_locator_id`
- `unit_kind / unit_order`
- `text_content`
- 可选且成对出现的 `char_start / char_end`，仅表示单一连续页面文本跨度
- `index_version`

Embedding 独立保存 `asset_id / processing_generation / index_version / is_current` 以及 `embedding_space / provider / model / dimensions / version / embedding`。`is_current` 由摄取事务维护，表示该向量属于资产当前 generation/index 投影；它不是 Asset ready/deleted 状态。Dense ANN 先在 embedding 表过滤 current 投影、Workspace、显式资产范围和 provider/model/version；批准的双索引路径分别从原始 cosine HNSW 与 binary-quantized Hamming HNSW 取候选，按 embedding identity 去重并以原始 cosine 精排，再由外层完整 current-chain/type scope 关闭校验。Binary distance 只用于候选发现，不进入最终排名或持久化语义。

主 cosine HNSW 使用 `ef_construction=512` 保留已验证的图质量；辅助 binary HNSW 使用 `ef_construction=64` 和 `3N` 补充候选，因为它不控制最终排序。这个物理索引与查询预算不改变任何业务数据或保存语义；同一次 fresh S0/S1/S2 canonical 已通过 Recall、双 plan、性能、容量、资源和 cleanup，并形成 M403A 发布结论。

原则：

- 一条向量列只对应一种维度
- 切换 provider 或维度时必须重建 embedding version
- 不做静默覆盖

## 7. 对象存储架构

### 7.1 选型

V1 使用 `MinIO` 作为本地 S3 兼容对象存储。

### 7.2 存储内容

- PDF 与 PNG/JPEG/WebP Asset 的原始源文件
- 摄取 generation 下不可变的派生 Representation 对象
- 当前 Image 路径生成的 image-oriented Representation
- 后续可选导出文件

PDF 页面、布局/OCR/表格/图片区域 Representation 元数据以及 PDF/Image ContentUnit 和 locator 当前持久化在 Postgres；文档不虚构尚未生成的 PDF 截图或解析 JSON 对象。

### 7.3 路径规范

当前路径：

- 源文件：`workspaces/{workspaceId}/assets/{assetId}/original{suffix}`
- 派生对象命名空间：`workspaces/{workspaceId}/assets/{assetId}/representations/{processingGeneration}/...`
- Image 当前派生对象：`workspaces/{workspaceId}/assets/{assetId}/representations/{processingGeneration}/image-oriented.png`

### 7.4 上传策略

当前采用 `Browser -> Next.js BFF -> FastAPI -> MinIO` 流式上传：

1. Browser 通过 Next.js BFF 请求上传会话。
2. FastAPI 创建 pending Asset，返回 BFF 上传 URL 与对象 key。
3. Browser 把文件上传到 BFF，BFF 保留准确 `Content-Type` 并将请求体流式转发给 FastAPI。
4. FastAPI 校验大小、MIME 和文件签名，将源文件流写入 MinIO，并记录源 SHA。
5. Browser 通过 BFF 调用 finalize。
6. FastAPI 创建 queued `ingest` job。

Browser 不持有 MinIO 预签名直传地址；上传鉴权、字节校验和 Asset 状态更新都留在 API 业务边界内。

## 8. 鉴权架构

### 8.1 鉴权结论

V1 采用 `Next.js 会话鉴权 + 内部服务鉴权` 双层架构。

#### 浏览器侧

- 浏览器只信任 Next.js
- 用户登录态由 Next.js 管理
- 推荐 `Auth.js` 这类 Web 会话方案
- Cookie 只对 Web 入口生效

#### 服务侧

- FastAPI 不直接暴露给浏览器
- FastAPI 只接受来自 Next.js BFF 的内部请求
- Next.js 在转发时附带内部签名 token 与用户上下文

### 8.2 鉴权链路

1. 用户登录 Web
2. Next.js 校验用户 session
3. 用户进入某 Workspace
4. Next.js 校验该用户是否有该 workspace 权限
5. Next.js 将 `user_id / workspace_id / role` 放入内部签名头或短时 JWT
6. FastAPI 验签并执行业务逻辑

### 8.3 为什么这样设计

这样做比“浏览器直接拿 token 调 FastAPI”更适合 V1：

- 减少 Python 侧处理 Web session 的复杂度
- 让浏览器永远只有一个公开入口
- 更容易做统一限流、审计、流式转发

### 8.4 鉴权原则

- 任何写操作都必须校验 `workspace_id` 权限
- 任何检索都必须以 `workspace_id` 为硬边界
- FastAPI 不信任前端直接传来的 `workspace_id`
- `workspace_id` 必须来自已认证上下文

## 9. 缓存架构

### 9.1 缓存选型

V1 使用 `Redis`。

### 9.2 缓存用途

#### `retrieval cache`

缓存项：

- query embedding 结果
- 同一 workspace 下短时重复检索结果

适合缓存：

- 高频重复问题
- 相同筛选条件的短时间重查

不适合缓存：

- 长时间持久答案
- 跨 embedding_version 的结果

#### `rate limit cache`

缓存项：

- 用户请求频率计数
- 上传频率计数
- Chat 请求频率计数

#### `task hot cache`

缓存项：

- 最近 ingestion_jobs 状态
- 最近重建索引状态

### 9.3 缓存原则

- 所有缓存 key 必须带 `workspace_id`
- 所有检索缓存必须带 `embedding_version`
- 缓存是加速层，不是真相源
- 任务最终状态只认 Postgres

## 10. 模型与检索架构

### 10.1 生成模型

默认：`OpenAI Responses API`

职责：

- 问答生成
- 结构化输出
- 引用型回答编排

### 10.2 Embedding Provider

采用 provider 抽象。

V1 支持两类：

- `OpenAI text-embedding-3-small`
- `Ollama qwen3-embedding:0.6b`

系统不允许直接把 provider 写死到业务逻辑中。

### 10.3 本地 embedding 路线

当前本机已安装并验活：

- `qwen3-embedding:0.6b`
- 运行在 Ollama
- 可经 `POST /api/embed` 使用
- 当前维度：`1024`

### 10.4 检索流程

1. 问题进入 Retrieval Service
2. 根据当前 Workspace 的 provider 配置生成 query embedding
3. 先在 `content_unit_embeddings` 按 `is_current`、Workspace、实际消息 Asset scope、当前 provider/model/version 做 pgvector ANN candidate，再按 ready Asset、representation/locator generation 和 index/type scope 做外层关闭校验
4. 从同一范围的 `content_units.search_vector` 做 PostgreSQL lexical 候选；该列由 `text_content` 的 `simple` 配置 generated stored，FTS GIN 直接索引该列
5. Dense 与 lexical 候选执行稳定 RRF：`pdf_page` 按 Asset+页去重，`pdf_region` 按 locator 保持独立
6. 只有黄金集证明 RRF 仍存在明确排序缺口时才评估 rerank

## 11. 部署架构

### 11.1 当前单机生产基线

采用 `Docker Compose`。

服务：

- `web`
- `api`
- `worker`
- `postgres`
- `redis`
- `minio`
- `ollama`
- `caddy`

特点：

- 单机可跑
- Alembic migration gate 可重复执行
- API/Worker/Web 使用锁定依赖和非 root 镜像
- Caddy 是唯一公开入口，Web 只在 Compose 私网
- PostgreSQL 与 MinIO 支持停写窗口同批备份、闭集 checksum 和空部署恢复

### 11.2 生产 / 云上部署

推荐 `Kubernetes` 或等价容器编排平台。

建议映射：

- `web` Deployment
- `api` Deployment
- `worker` Deployment
- `postgres` Stateful service 或托管数据库
- `redis` 托管或 Stateful service
- `minio` 或云对象存储 S3
- `ollama` 仅本地/内网实验环境保留
- 生产优先使用托管 OpenAI provider

### 11.3 网络拓扑

- 公网只暴露 `caddy`；生产域名由 Caddy 自动 HTTPS
- `web`、`api`、`worker`、`postgres`、`redis`、`minio` 在私网
- `api` 允许访问外部 OpenAI
- `worker` 允许访问 MinIO、Postgres、Redis、模型服务

## 12. 观测与运维架构

### 12.1 日志

- Web 请求日志
- API 业务日志
- Worker 任务日志
- 模型调用日志

日志格式统一为平铺键值格式。

### 12.2 指标

当前已采集：

- API HTTP route-template 请求数和完整响应生命周期
- embedding/generation provider success/error/cancelled 与操作时长
- Dense/Hybrid retrieval success/error、耗时和结果数
- MinIO 操作 success/error/cancelled 与生命周期
- ingestion job 各状态 gauge
- Worker claimed/handled/error counter 与 active gauge

正文、问题、文档名和对象 key 不进入 metric label。首 token、引用支持率和产品核验指标仍属于后续观测范围。

### 12.3 Trace / Correlation

关键链路统一带：

- `request_id`
- `workspace_id`
- `asset_id`
- `thread_id`
- `ingestion_job_id`

## 13. 关键业务流程的架构链路

### 13.1 上传与索引

1. Browser 通过 Next.js BFF 请求上传会话。
2. Web 与 API 校验用户、Workspace、Asset 类型和上传约束。
3. API 创建 pending Asset，返回 BFF 上传 URL 与对象 key。
4. Browser 上传文件；BFF 将请求体和准确 `Content-Type` 流式转发给 API。
5. API 校验字节并流式写入 MinIO，记录源 SHA。
6. Browser 调用 finalize，API 创建 queued `ingest` job。
7. Worker 领取任务，按 Asset kind 调度 PDF 或 Image ingestion adapter。
8. Adapter 创建对应 Representation、ContentUnit 与 locator；共享 ingestion service 写入 embedding 并激活当前 generation/index。
9. API/DB 将 Asset 状态更新为 `ready`。

### 13.2 Chat 问答

1. Browser 发问
2. Web 校验会话和 workspace
3. API 执行 retrieval
4. API 调用 Responses API 生成答案
5. API 先持久化用户消息和 `streaming` assistant 节点及 citation 准备记录
6. API 通过 SSE 返回 `meta/delta/citations/done`
7. Web 转发流到浏览器，Browser 展示回答并支持 citation 跳页

### 13.3 Citation 生成笔记

1. Browser 选中 citation
2. Web 转发 note create 请求
3. API 保存 note 与来源关联
4. Browser 刷新 notes 列表

### 13.4 Evidence Research

1. Browser 显式选择 Research；Quick Chat 不自动升级。
2. API 冻结 PlanRevision 的 Asset scope、Workflow/Prompt、provider/retrieval、policy 与预算。
3. creator 批准计划后，API 创建唯一 ExecutionSnapshot 和固定 DAG。
4. Worker 通过 typed service ports 领取 Step；Researcher 只调用 Evidence search/load 工具。
5. Verifier fail closed 标记 unsupported Claim；Critic 需要时发布 conflict Artifact 并等待 creator Decision。
6. Synthesizer 只选择 supported/resolved Claims；API 原子生成 canonical final Artifact、Claim markers、hash、Events 和终态。
7. 独立 Research SSE 通过持久化 seq 与 `Last-Event-ID` 重放；Evaluation 在 Run 完成后独立导入，不是核心 DAG Step。

详细职责、锁序和操作 runbook 见 [`../architecture/research-workflow-runtime.md`](../architecture/research-workflow-runtime.md)。

## 14. 安全边界

- 浏览器不可直连 Postgres
- 浏览器不可直连 Redis
- 浏览器不可直连 FastAPI 私有业务接口
- 模型调用密钥只存在服务端
- 对象存储由 BFF/API 校验用户、Workspace 与 Asset 归属后访问，Browser 不直接持有 MinIO 凭据或地址
- 删除 Asset 时通过 `delete_cleanup` 同步清理源对象、派生对象、ContentUnit 与向量引用关系

## 15. 演进路线

### V1

- OpenAI 生成
- OpenAI 或 Ollama/Qwen embedding
- pgvector 检索
- MinIO 本地对象存储
- Redis 缓存 + 队列

### 已完成的 V2 基线

- PostgreSQL lexical + Dense + RRF Hybrid
- 生产质量、延迟和并发门禁
- 可复现部署、指标、备份恢复和安全入口

### 已完成的 V3 Phase 1-2 基线

- 批准并迁移 Asset/Representation/ContentUnit/Embedding 合同
- PDF 页面布局、表格、图表、页内图片和 OCR 区域
- `pdf_page / pdf_region` 类型化 locator、Chat Citation/NoteSource 与 PDF Evidence Viewer
- 旋转、非对称 CropBox、扫描、artifact、多区域、指定页跳转、框选草稿和移动端 fixture 验收，以及 artifact/失败 Chat 两轮 Critical 复验

M402 的 21-case 工程执行、7-case 真实 BFF 全栈/像素 Evidence 与 7-case `openai / gpt-5.5` answer/refusal 均已通过。冻结 answer oracle、显式 opt-in runner 与独立复算门禁绑定 production prompt、Asset scope、Evidence 和 provider/model；回答质量使用移除数字 citation token 后的完整规范化输出 allowlist，未登记改写 fail closed。唯一一次获批外部执行无 provider 错误且 citation target 全覆盖；6 条正确改写经人工对照 Evidence 后加入冻结 allowlist，raw output/messages 与 capture-time diagnostics 保持不变，正式报告独立复算得到 `releaseGatePassed=true`。该本地证据链不宣称提供远程 provider 的密码学回执；若威胁模型包含整套 artifact 一致篡改，必须另接 provider 可验证回执或独立签名服务。M403 加强后的隔离 Compose 销卷恢复已通过恢复前后数据库/对象语义 SHA-256、桌面/移动端完整 raster/overlay 和最终容器/卷/网络零残留门。M403A 的 production Dense 使用 current-only cosine512/N + binary64/3N 两路 `MATERIALIZED` ANN candidate，identity 去重后只按原始 1024D cosine 精排；`f2a4c6e8b0d1` current-chain migration、scope trigger、两阶段 embedding 激活和 ANN/SQLite parity 已通过。fresh S0/S1/S2 canonical 三档全部通过，S2 9/9 Recall=`1.00`、load/index `2062.742s`、并发 p95 `246.531ms`。M403B 的 `a3c5e7f9b1d4` 已启用 Image 目录；PNG/JPEG/WebP 上传、源完整性、失败重试、检索/Evidence、长期 Worker 浏览器路径和 Image-enabled 销卷恢复均已通过，工程 `releaseGatePassed=true`。

### 已完成的 V4 确定性工程基线

- `b4d6f8a0c2e4` 增加获批的 Research ledger，`c5e7a9b1d3f6` 增加独立 Evaluation ledger，`e8f1a2b3c4d5` 发布 append-only Workflow/Prompt v2。
- Worker 使用固定 typed `BoundedResearchExecutor`，不引入动态 LangGraph checkpoint；PostgreSQL 是唯一业务事实源。
- provider/tool 共享锁序为 `Attempt -> Step -> Run -> call -> BudgetLedger`，锁后刷新 identity map；不使用 deadlock retry 掩盖锁序错误。
- R800 v4 在真实 PostgreSQL/MinIO、生产镜像和 scripted provider 上通过全部场景、空部署恢复和零残留清理。该证据只关闭工程门；R803 模型质量与 M404 用户价值仍为 `not_evaluable`。

## 16. 当前架构裁决

当前最重要的几条裁决是：

- `Workspace` 是顶层强隔离边界
- `Caddy` 是唯一宿主公开入口；`Next.js` 是浏览器唯一应用/BFF 边界
- `FastAPI` 是唯一业务后端
- `Worker` 负责所有长任务
- `Postgres` 是真相源，`Redis` 是加速层
- `MinIO` 存文件，`pgvector` 存检索向量
- `EmbeddingProvider` 必须可切换，不能把模型写死进业务层
- Research Workflow/Prompt/provider profile/Asset scope/预算在批准时冻结，Worker 不读取 latest 解释历史 Run
- API service 是 Research 持久化和事务唯一所有者；Worker 不拥有 ORM 或 migration
- Quick Chat SSE 与 Research Event SSE 是独立合同
- Workspace 视图状态只应在 workspace 实际切换时同步；重复选择当前 workspace 不能清空 active thread、文档或其他局部视图状态。

## 17. 当前 Evidence 域与演进门禁

以下职责边界已经在 V3 Phase 1-2 落地：

- `Asset`：Workspace 归属、权限、生命周期、源对象身份和资产类型
- `Representation`：原文件、OCR、布局、表格、caption、ASR 等不可变且可版本化的派生表示
- `ContentUnit`：段落、区域、表格、图像或时间片段等可寻址检索/分析单元
- `Embedding`：ContentUnit 的可重建索引投影，可存在多个空间和版本
- `EvidenceLocator`：带 discriminator 的稳定定位值；当前运行时已启用 `pdf_page / pdf_region / image_region`
- `Citation`：回答生成时冻结 locator、标题、摘要、索引映射和版本语义的证据快照

PDF/Image 不是稳定内核中的硬编码枚举。后端与 Web 使用部署期封闭注册表：每个模态模块提供字节验证、ingestion adapter、Representation/ContentUnit 类型、locator codec、retrieval channel 和 renderer。数据库类型目录与代码注册表不一致时 readiness 失败。后续 Audio/Video 允许增加模块和类型化 locator 明细表，但不得修改 Asset、Chat scope、Citation、NoteSource 或 Evidence Viewer shell 的核心职责。

Document/Page/Chunk 已通过受控迁移切换为 Asset/Representation/ContentUnit/Evidence，历史页码 citation 只机械映射为 `pdf_page`。当前 Evidence v1、Chat SSE、citation -> note、Viewer 跳转和删除/重索引语义保持冻结；任何 locator 新版本、核心表或保存 payload 变更仍必须先提交迁移、历史回放、坐标、fixture 和恢复影响设计并重新批准。

聚合、计数、类别分布和数据集质量问题必须走 SQL/分析路径，不能让 LLM 根据召回样本猜总量。Omnilabel 业务 schema 不进入通用 ContentUnit；它是独立业务域和产品赌注。


## 2026-07-15 运行边界

- 浏览器只访问 Next.js BFF；业务 API 额外要求 `x-ai-pdf-internal-token`，该值来自 Web/API 服务端环境变量 `AI_PDF_API_INTERNAL_TOKEN`。
- `/health/live` 只判断进程存活；`/health/ready` 检查数据库、对象存储、embedding provider 和 generation provider。
- Worker 采用有限退避、结构化事件日志和信号优雅退出；任务业务失败仍由 ingestion 服务落库，不能用进程重试替代任务状态机。
