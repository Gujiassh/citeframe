# Citeframe 详细系统架构设计

> 文档状态：历史架构规划快照。本文保留 V1/V2 的设计推导，不是当前实现的唯一事实源；当前运行状态、Asset/Evidence 合同、数据库 head 和阶段进度以 `docs/ssot/`、`docs/architecture/implementation-progress.md`、`docs/architecture/api-contracts.md`、`docs/architecture/database-design.md` 与 `specs/v3/` 为准。本文中标注为“当前实现”的旧 Document、`/documents`、PDF-only 或规划中依赖，不能作为新代码实现依据。

## 1. 文档定位

这份文档回答的不是“系统有哪些盒子”，而是“开发时每一层到底怎么组织、为什么这样组织、模块之间如何协作”。

它属于 `实现前架构设计`，目标是让后续的数据库设计、API 设计、项目骨架、前后端并行开发有明确边界。

它覆盖：

- 前端架构
- 后端架构
- Worker 架构
- 数据库架构
- 对象存储架构
- 鉴权架构
- 缓存架构
- 部署架构
- 仓库目录结构

不覆盖：

- 字段级 schema 细节
- 接口 request/response 细节
- 任务状态机细节
- 独立 OCR API、图表/表格/图片物体理解等多模态方案

这些会在后续专门文档中补齐。

## 2. 架构目标与约束

### 2.1 目标

系统架构必须同时满足：

1. 支持多 Workspace 强隔离
2. 支持大文件上传和异步索引
3. 支持带引用的 RAG 问答
4. 支持 PDF 浏览、笔记、标签、聊天历史
5. 支持本地学习部署和后续云上部署
6. 支持 OpenAI 托管模型与本地 Qwen embedding 并存

### 2.2 关键约束

1. PDF 解析、chunk、embedding 是长任务，不能塞进同步请求链路
2. 浏览器侧需要强交互和流式回答体验
3. 检索与业务数据强耦合，V1 不值得独立上向量专用数据库
4. 用户面向的是 Workspace，不是全局知识池
5. V1 架构必须可讲清楚、可本地复现、可后续演进，而不是先做企业级重平台
6. 当前运行时已采用 Asset/Evidence 内核；PDF 与 Image adapter 在 Worker 内分别输出页面/图片几何、原生文本、RapidOCR 和 caption region，生产 Image 只接受 PNG/JPEG/WebP

### 2.3 当前文档范围

当前运行时按 `Asset/Evidence + PDF/Image adapter` 主链实现：

- 直接提取文本层 PDF；无文本层扫描 PDF 走 Worker 内部 OCR fallback
- OCR 结果写入 `pdf_pages.legacy_ocr_blocks` 供透明选择层显示，同时形成 `pdf_ocr_region + pdf_region` 检索与 Evidence
- 页面 MediaBox/CropBox、rotation、display geometry 与 normalized top-left region 已持久化并进入 Citation/NoteSource 快照
- 表格、图表和页内图片区域已由 Phase 2 M202 产出 typed region Evidence；visual embedding 仍需评测证明必要性后单独批准

PDF 表格/figure 与独立 Image 已通过各自 adapter、Representation/ContentUnit 类型、locator codec 和 renderer 接入；后续新模态继续沿用该边界，不把模态规则压回共享 ingestion 或 Chat。

## 3. 总体架构结论

系统采用 `Web + API + Worker + Data Plane + Model Providers` 五层结构。

### 3.1 分层

1. `Web Layer（前端层）`
   - Next.js Web App
   - 用户界面、会话鉴权、BFF

2. `Application API Layer（业务接口层）`
   - FastAPI
   - 业务编排、RAG 编排、权限上下文消费

3. `Async Processing Layer（异步处理层）`
   - Worker
   - 解析、切块、embedding、索引、清理

4. `Data Plane（数据层）`
   - Postgres + pgvector
   - MinIO
   - Redis

5. `Model Provider Layer（模型提供层）`
   - OpenAI Responses API
   - OpenAI Embeddings
   - Ollama `qwen3-embedding:0.6b`

### 3.2 为什么是这套，而不是别的

#### 为什么不是 Next.js 全栈包掉一切

因为这个产品最重的链路不是页面，而是：

- PDF 解析
- chunk
- embedding
- 检索编排
- 索引任务

这些能力天然更偏 Python 生态，也明显属于异步后端任务，不适合塞进单个 Node Web 进程。

#### 为什么不是一个 Python 单体服务把前端也做了

因为产品明确追求：

- 现代 Web 交互体验
- App Router 风格路由和布局
- AI SDK 流式输出体验
- 组件化前端开发和面试演示效果

所以前端必须是独立的 Web 应用，而不是服务端模板页面。

#### 为什么不是更多微服务

因为 V1 不需要：

- 单独搜索服务
- 单独文件服务
- 单独聊天服务
- 单独权限服务

拆太细只会增加复杂度，不会提升 V1 产品价值。

### 3.3 最小必要拆分

最终选型是最小必要拆分：

- `web` 处理浏览器世界
- `api` 处理业务编排
- `worker` 处理长任务

这是为了把三种完全不同的负载分开：

- 用户实时交互
- 同步业务 API
- 异步长时处理

## 4. 仓库结构设计

### 4.1 推荐仓库形态

采用 `小型 monorepo / 双应用仓库` 结构。

原因：

- Web 与 API 生命周期不同
- 但又属于一个产品，不值得拆成多个独立仓库
- 共用文档、共用脚本、共用 Docker 编排更自然

### 4.2 推荐目录结构

```txt
citeframe/
  apps/
    web/
    api/
    worker/
  packages/
    shared-types/
    prompt-contracts/
  docs/
    ssot/
    architecture/
    research/
  specs/
    v1/
  infra/
    docker/
    k8s/
  scripts/
```

### 4.3 为什么这样分

#### `apps/web`

放 Next.js。
因为它是独立可部署物，有自己的依赖、构建、运行方式。

#### `apps/api`

放 FastAPI。
因为它是业务 API 边界，不该和 Worker 混在一个部署物里。

#### `apps/worker`

放任务消费者。
因为它的资源使用模式与 API 完全不同，后续部署要能单独扩缩容。

#### `packages/shared-types`

放跨层公共类型定义，例如：

- citation 基本结构
- note source 引用结构
- workspace role 枚举

这里不是放业务实现，只放稳定契约。

#### `packages/prompt-contracts`

放 Prompt 模板、结构化输出 schema、provider 无关的提示词契约。

理由：

- Prompt 是产品能力的一部分
- 但不应该散落在前端组件和 Python handler 里

## 5. 前端架构

## 5.1 技术选型与实施状态对比

> [!IMPORTANT]
> **当前实现态 (Current Interactive Frontend Prototype)**:  
> 当前核心数据链路已落地：`workspace`、`documents`、Chat thread/message/citation、notes、tags 及其 BFF/API 均已接通；`workspace-context.tsx` 现在只负责 Provider 组合和视图状态暴露；`use-workspaces`、`use-documents`、`use-chat`、`use-notes-tags` 分别负责各自真实 API/BFF 数据域。LocalStorage/mock 数据流已删除，后续新增能力继续沿用 API client + BFF + feature hook hydrate 的边界。
> 
> **规划目标态 (Target Production Architecture)**:  
> 后续对接真实 FastAPI 服务时，将全面引入并升级至以下生产级模块架构：

- `Next.js App Router`
- `TypeScript`
- `Tailwind CSS`
- `shadcn/ui` [规划中，暂未装包]
- `React Query` [规划中，暂未装包]
- `Zustand` [规划中，暂未装包]
- `AI SDK UI` [规划中，暂未装包]
- `react-hook-form` [规划中，暂未装包]
- `zod` [规划中，暂未装包]
- `react-pdf` 或 `pdf.js` 封装 [规划中，暂未装包]
- `Auth.js` [规划中，暂未装包]

### 5.1.1 为什么用这些

#### `Next.js App Router`

因为它同时提供：

- 页面路由
- 布局系统
- 服务端渲染与客户端混合
- BFF route handlers
- 与 Web 会话鉴权的天然结合

#### `React Query`

因为本产品有大量服务端状态：

- workspace 列表
- 文档状态
- ingestion jobs
- threads
- notes
- tags

这些都属于 `服务端状态`，不该塞进全局 store。

#### `Zustand`

因为 Viewer 页码、当前 citation、高亮定位、右侧 panel tab 等是 `UI 运行时状态`，不该进 React Query，也不该进数据库。

#### `AI SDK UI`

因为它只负责流式回答体验，适合作为 chat 渲染层。

注意：
它不是 RAG 实现层，RAG 仍在 FastAPI。

#### `react-hook-form + zod`

因为 Workspace 设置、Prompt 配置、Note 编辑都是表单型交互，需要统一校验和提交模型。

### 5.2 前端目录结构与路由口径对比

> [!IMPORTANT]
> **当前实现态 (Current Prototype Routing & Files)**:  
> * **入口页面 (`/`)**: 承载登录态下的真实 Workspace 管理大盘。
> * **控制台详情页 (`/workspaces/[workspaceId]`)**: 单个工作区的三栏物理分栏主体渲染页。
> * **页面重定向 (`/workspaces`)**: 自动跳回 `/` 主门户。
> * **物理组件群**: 集中位于 `src/components/`，状态管理器位于 `src/lib/`。
> 
> **规划目标态 (Target Production Routing & Folders)**:  
> 对接真实微服务 API 时，计划演进并规范为以下独立分层子文件夹：

```txt
apps/web/src/
  app/
    (auth)/              # [规划目标，暂未落地]
      login/
    (workspace)/
      w/[workspaceId]/   # [规划目标，暂未落地，当前为 /workspaces/[workspaceId]]
        layout.tsx
        page.tsx
        documents/page.tsx
        chat/page.tsx
        notes/page.tsx
        settings/page.tsx
    api/                 # [当前已落地最小 workspace BFF；其余业务路由仍属目标态]
      workspaces/route.ts
      workspaces/[workspaceId]/route.ts
      internal/          # [规划目标，暂未落地]
        chat/route.ts
        upload-session/route.ts
        finalize-upload/route.ts
  features/              # [规划目标，暂未落地]
    workspace/
    documents/
    viewer/
    chat/
    notes/
    tags/
    prompts/
  components/            # [当前实现：承载所有 UI 模块]
    shell/
    layout/
    ui/
  stores/                # [规划目标，暂未落地]
    viewer-store.ts
    workspace-ui-store.ts
  lib/                   # [当前实现：承载 i18n/theme/workspace/auth 状态分层]
    auth/
    bff/
    query/
    utils/
  types/
```

### 5.3 前端模块边界

#### `workspace feature`

负责：

- Workspace 列表
- Workspace 切换
- Workspace 概览
- 当前 Workspace 上下文展示

不负责：

- 具体文档内容
- 检索逻辑

#### `documents feature`

负责：

- 上传入口
- 文档状态列表
- 文档重试/删除
- 文档列表筛选

不负责：

- PDF 内部展示
- citation 联动

#### `viewer feature`

负责：

- 通过受权限保护的原始 PDF 文件流渲染页面
- 使用 PDF.js canvas 保留源文件图片、排版和视觉内容
- 为原生文本 PDF 渲染 text layer，为 PDF 内置链接/批注渲染 annotation layer
- 页码跳转
- 当前 citation 定位
- 视图模式切换

不负责：

- 检索
- 问答生成

#### `chat feature`

负责：

- 问题输入
- 流式回答展示
- `ChatMarkdown` Markdown/GFM 渲染
- 基于服务端 0-based `citationIndex` 的 `[n]` 内联引用映射
- citation 展示
- citation 点击事件发出

不负责：

- 真正的 RAG 编排

#### `notes feature`

负责：

- Notes 列表
- Note 编辑与保存
- citation -> note 创建

#### `tags feature`

负责：

- Tag 创建与删除
- Tag 绑定与筛选 UI

#### `prompts feature`

负责：

- Workspace Prompt 编辑
- 抽取模板编辑
- 回答风格设置

### 5.4 前端状态分层

前端状态分成四类：

#### A. Server State

用 React Query 管：

- workspace list
- workspace summary
- document list
- document status
- ingestion jobs
- threads
- messages
- notes
- tags

#### B. UI Runtime State

用 Zustand 管：

- 当前文档 id
- 当前页码
- 当前 citation
- 当前激活 panel
- viewer 缩放/分页模式

#### C. Stream State

用 AI SDK 管：

- 当前回答 token 流
- pending citation block
- 回复中的 loading 状态

#### D. Form State

用 react-hook-form 管：

- workspace form
- prompt settings form
- note edit form

### 5.5 前端路由设计

> [!IMPORTANT]
> **当前实现态 (Current Prototype Routes)**:  
> * **`/`**: 负责登录态控制与工作区管理门户。
> * **`/workspaces/[workspaceId]`**: 负责 Workspace 主工作台（整合了 Tab 切签，包含了文档浏览器、大纲树、Chat 对话气泡、随手记及设置面板）。
> * **`/workspaces`**: 重定向跳回首页 `/`。
> 
> **规划目标态 (Target Production Routes)**:  
> 接入正式后端后，计划将 Tab 式切换逻辑沉淀为 Next.js 独立物理子路由：

#### `/login`
负责登录。

#### `/w/[workspaceId]`
负责 Workspace 主工作台。建议作为三栏总布局承载页。

#### `/w/[workspaceId]/documents`
负责文档管理。

#### `/w/[workspaceId]/chat`
负责纯聊天视图。

#### `/w/[workspaceId]/notes`
负责笔记和标签视图。

#### `/w/[workspaceId]/settings`
负责 Prompt、Workspace 设置。

### 5.6 前端 BFF 设计

BFF 不是可选层，而是前端架构的一部分。

#### BFF 负责什么

- 校验用户 session
- 校验 workspace membership
- 代理浏览器请求到 FastAPI
- 生成上传 session
- 代理 chat stream
- 屏蔽浏览器直接访问内部业务服务

#### 为什么要 BFF

因为浏览器环境和业务服务环境是两套安全边界。

如果浏览器直接调 FastAPI：

- Python 要直接处理 Web session
- 浏览器直接暴露更多内部接口
- workspace 权限上下文容易被乱传

所以浏览器的唯一可信入口应该是 Next.js。

### 5.7 前端关键交互链路

#### 上传链路

1. 用户点上传
2. documents feature 请求 BFF 创建上传 session
3. 浏览器直传 MinIO
4. 上传成功后调用 finalize
5. React Query 开始轮询 job 状态
6. 文档 ready 后刷新文档列表和 viewer 可用状态
7. Viewer 从 `/documents/{documentId}/file` 读取原始 PDF，PDF.js 负责页面渲染；`document_pages`/`document_chunks` 只作为检索和 citation 数据源

#### citation 跳转链路

1. 用户点回答里的内联 `[n]` 或来源列表 citation
2. chat feature 根据 `citationIndex` 取已持久化 citation 快照并发出跳转事件
3. workspace view state 打开对应 `documentId` 并更新 `pageNumber`
4. viewer feature 平滑回到阅读区顶部并短暂提示目标 PDF 页面

#### citation 转 note 链路

1. 用户点 citation 的“记为笔记”
2. note create form 带来源信息打开
3. 提交后 notes feature 刷新列表

## 6. 后端架构

### 6.1 技术选型

后端采用：

- `FastAPI`
- `Pydantic`
- `SQLAlchemy / SQLModel` 风格 ORM
- `Redis`
- `ARQ` 作为任务队列消费者框架
- Provider adapters

### 6.1.1 为什么是 FastAPI

因为它适合：

- 结构化 API
- async IO
- Pydantic 契约建模
- 文档处理与模型调用编排

### 6.1.2 为什么是 ARQ 而不是 Celery

V1 更适合 `ARQ`：

- Redis 即可
- async 友好
- 心智负担比 Celery 小
- 对学习/面试项目更轻

Celery 当然能做，但对 V1 来说过重。

### 6.2 API 应用内部结构

推荐：

```txt
apps/api/src/
  app/
    main.py
    config.py
    deps/
    middleware/
    routers/
  modules/
    workspace/
    documents/
    ingestion/
    retrieval/
    chat/
    notes/
    tags/
    prompts/
    auth_context/
  providers/
    generation/
    embedding/
    rerank/
  infra/
    db/
    cache/
    storage/
    queue/
    observability/
  contracts/
    dto/
    events/
    errors/
```

### 6.3 后端模块职责

#### `workspace module`

- workspace CRUD
- summary aggregation
- settings storage

#### `documents module`

- document record lifecycle
- page/chunk metadata read models
- delete / retry / status read

#### `ingestion module`

- upload finalize
- create ingestion jobs
- orchestrate parse/chunk/embed sequence

#### `retrieval module`

- query preprocessing
- embedding dispatch
- pgvector recall
- candidate shaping

#### `chat module`

- prompt assembly
- retrieval context assembly
- response generation
- citation generation
- thread/message persistence

#### `notes module`

- note CRUD
- note source relation
- citation -> note transform

#### `tags module`

- tag CRUD
- tag binding
- tag filtering

#### `prompts module`

- workspace prompt config
- output schema profile

#### `auth_context module`

- consume signed user context from web
- enforce workspace scope

### 6.4 Provider 抽象

后端必须使用 provider 抽象，不允许在业务模块直接写死某个模型厂商。

#### `GenerationProvider`

负责：

- 普通回答
- 结构化输出
- 流式输出

#### `EmbeddingProvider`

负责：

- embed_query
- embed_documents
- 维度信息暴露
- provider/model/version 信息暴露

#### `RerankProvider`

V1 可留空接口，V2 再启用。

### 6.5 为什么要 provider 抽象

因为这个产品要同时支持：

- OpenAI 托管模型
- 本地 Ollama / Qwen embedding

如果不抽象，后面切换 provider 会把 retrieval 和 ingestion 代码全部污染。

## 7. Worker 架构

### 7.1 Worker 角色

Worker 是独立部署物，不和 API 共进程。

原因：

- 解析与 embedding 是长任务
- 和 API 混跑会污染延迟
- 后续可能单独扩容

### 7.2 任务拆分

V1 任务粒度建议：

- `parse_pdf`
- `generate_pages`
- `chunk_document`
- `embed_chunks`
- `mark_document_ready`
- `cleanup_document`
- `reindex_document`

### 7.3 为什么拆成这些任务

不是为了炫技，是为了：

- 明确失败点
- 可重试
- 可观察进度
- 后续支持重建索引

### 7.4 Worker 和 API 的关系

- API 只创建任务和读状态
- Worker 只执行重任务和更新状态
- 任何任务最终状态都写回 Postgres

当前实现已落 `ingest/embed_chunks/delete_cleanup` 消费：Worker 轮询 Postgres 中 queued job，以行锁领取任务，优先提取 PDF 文本层；没有文本时用 RapidOCR + ONNX Runtime 渲染页面并识别，再写入 `document_pages`（含 OCR blocks）、`document_chunks`，批量调用 Ollama/OpenAI embedding provider 写入 pgvector，并把文档推进到 `ready`。Web Viewer 从原始 PDF 文件流读取源文件，使用 PDF.js canvas/text/annotation layers 阅读，扫描页额外叠加透明 OCR 可选层。检索服务在 workspace 和当前索引版本边界内执行 Dense、PostgreSQL FTS/pg_trgm lexical 与页级 RRF，生产验收通过后默认使用 Hybrid；Chat API 已持久化 thread/message/citation，按父节点链支持编辑分支，并通过真实 Responses API delta SSE 返回；Notes/Tags API 已持久化知识沉淀关系，citation -> note 使用 `message_citations` 快照校验与落库。

## 8. 数据库架构

### 8.1 为什么是 Postgres + pgvector

因为当前系统里“检索数据”与“业务数据”不是分离域，而是强关联域。

每个 chunk 不只是向量，还必须绑定：

- workspace
- document
- page
- text
- embedding version

所以 V1 最合理的方案是：

- 一个数据库做事务真相源
- 一个数据库同时承接向量检索

### 8.2 表分组

#### 身份与权限

- users
- sessions
- workspace_memberships

#### 知识资产

- workspaces
- workspace_prompt_versions
- documents
- document_pages
- document_chunks
- ingestion_jobs

#### 会话与沉淀

- chat_threads
- chat_messages
- message_citations
- notes
- tags
- note_sources
- document_tags
- note_tags

### 8.3 设计原则

#### `workspace_id` 强约束

所有核心业务表必须带 `workspace_id`。

这是系统最重要的不变量之一。

#### `embedding_version` 强约束

任何 embedding provider/model/dimension 变化，都必须反映到版本层。

不能直接就地覆盖旧向量。

#### 软硬删除分层

- Workspace：建议归档优先
- Document：删除时需要联动对象存储和向量清理
- Note/Tag：可软删

## 9. 对象存储架构

### 9.1 为什么必须独立对象存储

因为 PDF 和页面图属于大文件资产，不适合塞进 Postgres。

### 9.2 为什么选 MinIO

因为：

- 本地可跑
- S3 兼容
- 后续迁移到云对象存储时业务接口几乎不变

### 9.3 对象层内容

- 原始 PDF
- 页面预览图
- 解析 JSON
- chunks 中间产物

### 9.4 路径组织

按 Workspace 隔离：

```txt
workspaces/{workspaceId}/documents/{documentId}/original.pdf
workspaces/{workspaceId}/documents/{documentId}/pages/{page}.png
workspaces/{workspaceId}/documents/{documentId}/artifacts/parsed.json
```

### 9.5 上传方式

选择 `预签名直传`，而不是 Web 中转上传。

原因：

- 大文件不压 Web
- 本地/云上都通用
- 上传链路和业务链路天然分离

## 10. 鉴权架构

### 10.1 设计结论

采用 `Web Session + Internal Signed Context`。

#### 用户面对的鉴权

- 用户只登录 Web
- 会话保存在 Next.js
- Cookie 只对 Web 有效

#### 服务之间的鉴权

- Next.js 转发给 FastAPI 时附带内部签名上下文
- FastAPI 不信任浏览器自传的 `workspace_id`
- FastAPI 只信任签名上下文里的 `user_id/workspace_id/role`

### 10.2 为什么不是浏览器直接拿 JWT 打 FastAPI

因为这会增加：

- Web 会话复杂度
- 公开接口暴露面
- Workspace 权限被篡改的风险

V1 更适合把浏览器世界收敛到 Next.js。

### 10.3 V1 权限模型

建议至少两级：

- `owner`
- `member`

V1 不做复杂 RBAC，但要保证：

- 未加入 Workspace 的用户不能访问其内容
- 任意请求都要在服务端二次校验 workspace 归属

## 11. 缓存架构

### 11.1 为什么需要 Redis

不是因为“流行”，而是因为有三种短时状态不适合放主库：

1. 队列
2. 限流计数
3. 热点临时缓存

### 11.2 缓存内容

#### 队列层

- ingestion task queue
- reindex queue

#### 热点查询层

- workspace summary 短缓存
- recent retrieval candidates 短缓存
- provider metadata 缓存

#### 限流层

- chat rate limit
- upload rate limit

### 11.3 为什么不缓存最终答案

V1 不推荐把回答结果做长期答案缓存，因为：

- Prompt 会变
- embedding version 会变
- 文档集会变
- 旧答案可能和当前知识库不一致

## 12. 模型与检索架构

### 12.1 生成模型

V1 默认使用 OpenAI Responses API。

原因：

- 稳
- 输出质量高
- 结构化输出路线清晰
- 流式体验成熟

### 12.2 Embedding 模型

V1 支持双路线：

- OpenAI `text-embedding-3-small`
- Ollama `qwen3-embedding:0.6b`

### 12.3 为什么保留双路线

#### OpenAI 路线

用于：

- 快速闭环
- 减少本地运维变量

#### Qwen 路线

用于：

- 本地学习
- 中文/多语言检索验证
- 展示 provider 可替换架构

### 12.4 检索链路

V1 明确采用：

- query embedding
- pgvector top-k recall
- 直接进入回答编排

当前检索事实：PostgreSQL lexical、pgvector Dense 和页级 RRF 已通过 40 条生产评测、warm-up 与并发门禁，默认使用 Hybrid；Dense 保留为显式回归策略。Rerank 和 graph retrieval 仍不进入主线，除非黄金集证明现有融合存在明确缺口。

## 13. 部署架构

### 13.1 本地环境

使用 `Docker Compose`。

服务：

- web
- api
- worker
- postgres
- redis
- minio
- ollama
- caddy

### 13.2 为什么本地需要 Ollama

因为本地架构要能展示“OpenAI 托管 embedding”和“本地 embedding”两条路线。

### 13.3 云上环境

云上部署建议：

- `web`、`api`、`worker` 容器化
- Postgres/RDS 托管
- Redis 托管
- 对象存储换 S3/R2/OSS
- 本地 Ollama 可以被关闭，embedding 改走托管 provider

### 13.4 网络边界

- 公网仅暴露 Caddy；生产域名由 Caddy 自动 HTTPS
- Web / API / Worker / DB / Redis / MinIO 在私网
- API 允许访问 OpenAI
- Worker 允许访问对象存储、数据库、缓存、模型服务

## 14. 观测与日志架构

### 14.1 日志

日志统一采用平铺 key-value。

至少记录：

- request_id
- workspace_id
- document_id
- thread_id
- ingestion_job_id
- provider
- model

### 14.2 指标

当前已落地：

- HTTP route-template count 和完整 response lifetime
- provider count/duration/outcome
- retrieval count/duration/outcome/result count
- storage operation count/duration/outcome
- ingestion job status gauge
- Worker job/active 指标和单行任务日志

产品层的 citation 核验率、回答支持率、答案转笔记率与首 token 仍需在下一阶段补充。

## 14.3 备份恢复与入口

- Web/API/Worker/Caddy 在 PostgreSQL custom dump 和 MinIO mirror 的同一停写窗口停止接收写入
- manifest 绑定 Compose project、数据库和 bucket，checksum 必须与文件闭集完全一致
- 恢复只允许进入空部署，停写前验证 custom archive，并使用单事务 `pg_restore`
- MinIO 恢复后回读并逐文件对比；恢复完成后重复执行 Alembic migration
- Caddy 在生产域名自动 HTTPS，并返回 HSTS、nosniff、frame deny 和 referrer policy

## 14.4 下一目标架构边界

V3 多模态 PDF + 独立图片需要把现有 `Document/Page/Chunk/Citation` 受控迁移为 `Asset / Representation / ContentUnit / Embedding / EvidenceLocator` 目标结构，不能只做名称替换或长期双模型。`pdf_region/image_region` 必须冻结坐标单位、原点、几何快照和多区域语义。正式实施属于持久化与 Citation API 合同变化，必须经 `specs/v3/multimodal-workspace/` 与六项合同裁决批准。

## 15. 这份架构文档能指导什么

它现在已经足够指导：

- 项目目录初始化
- 服务拆分
- 技术栈落位
- 前后端模块边界设计
- 部署与本地环境准备
- 后续 schema / API / 状态机文档编写

它还不能替代：

- schema 设计文档
- API 契约文档
- job state machine 文档

## 16. 下一步依赖文档

在这份文档之后，最应该补的就是：

1. `schema.md`
2. `api-contracts.md`
3. `job-state-machine.md`

只有把这三份也补上，整套架构设计才真正进入“可直接实现”的状态。
