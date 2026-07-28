# 实施进度

## 1. 这份文档是什么

这份文档记录项目当前的实施进度，用来回答：

- 已经设计到哪
- 已经完成哪些阶段
- 当前正在做什么
- 下一步应该做什么

更新规则：

- 进入新阶段时更新
- 某个阶段完成后更新状态
- 如果实施顺序调整，也在这里同步记录

## 2. 当前总状态

当前项目状态：`V1、Chat-first 工作台、V2-A Hybrid/RRF、阶段 9、V3 M401-M403B 与 V4 R000-R800 确定性工程基线已完成；R803 真实模型质量和 M404 用户价值仍为 not_evaluable，产品保持 internal_preview。`

M403A 的逐次优化假设、实验手段、通过/否决结果、指标和 artifact 统一记录在 `docs/evals/m403a-optimization-log.md`；后续不得只更新最终结论而遗漏失败实验与运行环境证据。

说明：

- 产品设计与架构、数据库设计、API 契约均已完成
- **前端交互外壳已全部完成**（页面布局、PDF 浏览器、章节大纲导航树、划词提问浮窗、随手记、流式对话气泡、多语言与暗黑模式切换、自适应抽屉布局与微动效都已具备；后续继续保留 UI 壳，但对应旧 mock 数据流会逐段替换并删除，不作为正式逻辑继续维护）
- `web / api / worker` 基础工程已初始化完成
- 真实后端认证接口与 BFF session cookie 已接通
- `users / workspaces / workspace_memberships` 最小真表链路已接通
- 首页与工作区详情页的 workspace 可见范围、创建、归档已切到真实 BFF/API
- API 侧已接入数据库结构版本步骤工具，当前数据库 head 为 `e8f1a2b3c4d5`；embedding current-chain、双 HNSW、生产 Image、Research/Evaluation ledger 与 Workflow/Prompt v2 已落地
- Asset、向量检索、Chat thread/message/citation、notes/tags 已进入真实链路
- 生产运行时已移除 `/documents` 和 Document 业务模型，历史 PDF 数据已机械迁移到 Asset/Evidence 内核

## 3. 阶段进度

| 阶段 | 内容 | 状态 (前端原型) | 状态 (真实对接) | 说明 |
| --- | --- | --- | --- | --- |
| 1 | 项目定位与架构总览 | 已完成 | 已完成 | 产品设计、系统架构、详细架构已落文档 |
| 2 | 前端骨架与 BFF 接入 | 已完成 | 已完成 | Workspace、Assets、Chat、Notes、Tags、settings 的真实 BFF 已落地；feature hooks 负责数据域，Provider 只做组合与视图状态暴露 |
| 3 | 鉴权与 Workspace 隔离 | 已完成 | 已完成 | BFF session、membership 校验和 API 内部 token 边界已接通；业务 API 不再只信任可伪造的 `x-user-id` |
| 4 | 对象存储与上传链路 | 已完成 | 已完成 | BFF/API 使用请求流和 spool 临时文件上传，保留 100 MB 限制并校验 upload-session 字节数；预签名直传仍是后续优化项 |
| 5 | Worker 与任务状态机 | 已完成 | 已完成 | Worker 已消费 `ingest` / `embed_chunks` / `delete_cleanup`，具备 lease 回收、结构化日志、SIGTERM/SIGINT 优雅退出和 5 次有限退避；异步删除失败可由 owner 重新入队 |
| 6 | PDF 原始阅读、文本解析与切块 | 已完成 | 已完成 | `pdf_pages`、`content_units` 与 `content_unit_embeddings` 已落真实表；文本 PDF 和扫描 PDF 的 OCR 结果按页和 ContentUnit 持久化，原始文件通过文件流供 PDF.js 阅读 |
| 7 | Embedding 与检索 | 已完成 | 已完成 | `vector(1024)`、HNSW、PostgreSQL FTS/pg_trgm、页级 RRF 和 Dense/Hybrid 显式策略已接通；40 条生产评测通过后默认使用 Hybrid |
| 8 | Chat、citation、笔记与标签 | 已完成 | 已完成 | Chat `assetScope`、消息范围快照、不可变 locator/sourceVersions citation、notes、note_sources、tags、asset_tags、note_tags 真表、API、BFF 和 citation -> note 已接通 |
| 9 | 部署、日志与观测 | 已完成 | 已完成 | 锁定镜像、迁移 gate、Prometheus、Worker 私网指标、同批备份销卷恢复、Caddy 安全入口和全业务 smoke 已通过 |
| V3-1 | Asset/Evidence 基础迁移 | 已完成 | 已完成 | 不可逆迁移、封闭模态注册表、Asset API/Worker/Web、Chat scope、Evidence Viewer shell、历史快照 oracle 和 Critical 复审已完成；Image 在该早期阶段仅注册合同，后续由 M403B 启用摄取 |
| V3-2 | 多模态 PDF Evidence | 已完成 | 已完成 | 页面几何、layout/OCR、表格/图表/页内图片、`pdf_page/pdf_region` Citation/NoteSource、Viewer 区域交互与失败 Chat 回放已通过两轮 Critical 复验 |
| V3-3 | 独立图片闭环 | 已完成 | M301-M305 已通过最终 Critical | 图片归一化、OCR/caption、Evidence 历史快照、Viewer、区域 Chat/Note 与混合检索已完成；M403B 已将生产 Image 正式启用 |
| V3-4 | 质量与发布验收 | M401-M403B 已完成 | M403B 已完成 | M403 恢复、M403A binary64/3N canonical 与 M403B 三格式生产上传/恢复/浏览器门均通过；工程 `releaseGatePassed=true` |
| V4 | Evidence Research Workflow | R000-R800 已完成 | 确定性工程门通过 | Research ledger、固定 executor、HITL/SSE/retry/recovery、Web、observability、Evaluation 与 R800 PostgreSQL/MinIO 恢复全部通过；R803/M404 仍 not_evaluable |

## 4. 已完成的设计文档

- `docs/ssot/product-design.md`
- `docs/ssot/system-architecture.md`
- `docs/architecture/detailed-system-architecture.md`
- `docs/architecture/feature-map.md`
- `docs/architecture/database-design.md`
- `docs/architecture/api-contracts.md`
- `docs/architecture/job-state-machine.md`

## 5. 当前建议实施顺序

V1、V2-A、阶段 9、V3 M401-M403B 与 V4 R000-R800 工程基线已完成。后续按以下顺序推进：

1. 仅在真实 provider、fixture、Asset scope 与 comparison keys 明确批准后执行 R803 Quick/Research 成对质量
2. 真实用户验证作为 M404 Beta 门推进；数据不足时保持 `not_evaluable` 和内部预览
3. 后续切片继续沿用确定性 fixture、真实 BFF、恢复与独立复审门，不以“多 Agent”或工程绿灯替代证据质量

## 6. 当前正在做什么

当前：`V4 R800 v4 确定性工程门已通过。Research main Run、bounded parallel fan-out、unsupported withholding、冲突审批恢复、分支重试、lease reclaim、SSE replay、取消/成员移除、唯一 final Artifact、PostgreSQL/MinIO 空部署恢复和最终清理均通过；R803/M404 继续 not_evaluable。`

## 2026-07-20：M403A 完成记录

- current-chain 修复前的失败 canonical 保留为历史证据：S0/S1 通过，S2 `image-ocr:D1=0.8`；不能将失败报告改写为通过。
- 根因已由保留库矩阵确认：旧 generation/index 与 current target 的向量重复，ANN CTE 只按 embedding metadata 取前缀，外层 current-chain 过滤后丢失 current target；提高 `ef_search`、`m` 或窗口不能稳定修复，完整 current-chain `EXISTS` 会导致 exact sort。
- 已落地的修复边界：向 `content_unit_embeddings` 冗余 `asset_id`、`processing_generation`、`index_version`、`is_current`；`f2a4c6e8b0d1` 从 ContentUnit/Locator/Asset 回填并 fail closed，current-only partial HNSW 与 statement-level scope trigger 已安装。摄取先写 inactive 投影，latest CAS 通过并切换 Asset current generation 后再原子激活；Dense ANN 与 SQLite 路径都在同链条件下过滤，外层业务 scope 保留。
- 状态机保护已补齐：失败回写、claim/stale recovery、retry/reindex、上传二进制和 finalize 都不会越过 latest/delete_cleanup CAS；上传在对象写入前重新锁定 pending Asset。migration 的 HNSW drop/recreate 需要维护窗口，当前无真实用户，不能宣称零停机。
- 最小验收已完成：migration/model drift、摄取成功/失败回滚、current-only Dense/SQLite parity、selected/all-ready SQL、partial HNSW EXPLAIN 与 fresh S1 Recall/plan 全通过。最新完整 canonical 仍是历史 cosine-only 失败证据；双索引优化的逐次结果见 `docs/evals/m403a-optimization-log.md`。
- ef512 两次有效 S2 均将 9/9 Recall 提升到 `1.00`，但 load/index 分别为 `3216.427s` 和 `2817.828s`；binary128 最干净 S2 的 load/index `2721.264s`、并发 p95 `424.622ms` 仍略超冻结门。最终 binary64/3N fresh S1 的 9/9 Recall、双 HNSW plan、性能和 cleanup 全通过；首次 S2 因共享盘异常在建图前已数学超门而中止并清零，不能计为产品失败。
- binary64/3N fresh S2 全门通过：load/index `2255.299s`，9/9 Recall `1.00`，Dense/lexical/Hybrid p95 `32.745/23.391/55.745ms`，8 并发 p95 `291.122ms`、吞吐 `56.405 req/s`，数据库 `7.159 GiB`，零错误、零 drift、零 cleanup 残留。S2-only 仍为 `debugOnly`。
- fresh S0/S1/S2 canonical 已设置 `releaseGatePassed=true`：S2 load/index `2062.742s`，9/9 Recall `1.00`，Dense/lexical/Hybrid p95 `32.237/41.663/54.373ms`，8 并发 p95 `246.531ms`、吞吐 `61.069 req/s`，数据库 `7.159 GiB`，零错误、零 drift、零 cleanup 残留。正式证据为 `docs/evals/artifacts/m403a-v2/`。
- 最终 migration `f2a4 -> e1f3 -> f2a4`、Alembic drift、API `278 passed`、Worker `93 passed`、Ruff、compileall、runner 语法、artifact SHA-256、canonical oracle 与 diff check 均通过；临时 test output/cache 已清理，正式 artifact 保留。
- M403A 完成时生产 Image 保持 disabled；该门已由后续单独批准并完成的 M403B 正式打开，M404 仍未提前宣称通过。

收口结果：

- 架构和数据库口径已经统一
- API 契约和状态机已经补齐
- 文档已完成一次交叉评审
- `apps / packages / infra` 目录骨架已经建立
- `apps/web`、`apps/api`、`apps/worker` 基础工程已初始化
- Workspace 列表与详情的最小 API/BFF/页面链路已建立
- `users / workspaces / workspace_memberships` 最小真表、查询、创建、归档链路已落地
- API 侧已从启动时自动建表切换到显式数据库版本步骤；当前 head 版本为 `e8f1a2b3c4d5`
- `assets / ingestion_jobs` 真表、迁移、列表、upload-session、二进制上传、finalize-upload、job 查询与删除链路已落地；Worker 通过 `IngestionAdapterRegistry` 按 `asset_kind` dispatch，API 共享 orchestrator 不再理解 PDF/OCR/page/bbox
- `pdf_pages / content_units / content_unit_embeddings` 真表和迁移已落地；Worker 会领取 queued ingest job、回收超时任务，先提取文本层，必要时用 RapidOCR + ONNX Runtime 渲染页面并识别，再按页生成 ContentUnit、批量调用 embedding provider、写入向量并推进 `chunking -> embedding -> ready`，同时支持 `embed_chunks` 回填已有 ContentUnit。
- 原始 PDF 文件流已接通 API/BFF；`PdfViewer` 使用 PDF.js canvas 作为主页面、text layer 支持原生 PDF 文本选取、扫描 PDF 使用透明 OCR block 层支持划词、annotation layer 支持 PDF 内置链接/批注，OCR 文本不覆盖源页面视觉内容
- 2026-07-14 回归：真实 84 页扫描 PDF 的 API/BFF 文件流返回 `200 application/pdf`，浏览器确认 canvas 页面非空、84 页翻页、110% 缩放、目录跳页均可用；桌面端无横向溢出，移动端默认收起两侧面板且打开目录后仍无横向溢出。扫描页额外使用透明 OCR 文本层支持选取，不重排或覆盖源 PDF 的图片与排版
- BFF 现已从登录 cookie session 中透传 `x-user-id` 和 `x-ai-pdf-internal-token` 到 FastAPI，按当前用户 membership 返回可见工作区并代理 Asset 上传请求；FastAPI 不再只信任可伪造的用户 header
- 主工作台的 Workspace、Assets、Chat、Notes、Tags 和 settings 已删除 localStorage/mock 数据流，改为按 workspace hydrate 真实列表；Notes 支持新建、编辑、归档删除和 citation 来源跳转，Tags 支持创建、删除、Asset/笔记绑定和筛选；threads 继续使用真实表、API、BFF 和 hydrate/send/归档链路
- 已支持真实后端注册/登录与 BFF httpOnly cookie session（不自动注册，要求显式配置 `AI_PDF_SESSION_SECRET`）
- 已补 FastAPI auth / workspace / assets / ingestion / provider / retrieval / chat / notes / health service 自动化测试；真实回归验证了 Ollama 1024 维向量、扫描 PDF 84 页 OCR block、ContentUnit ready、Hybrid/RRF、Responses API 真实 delta SSE、消息分支编辑、citation 快照、notes/tags workspace 隔离、历史 Chat 会话切换保留和真实 BFF 页面读写
- 2026-07-15 回归：修复旧聊天迁移按 UUID 排序导致的同时间问答倒序，新增 `e6a7b8c9d0f1` 重建历史父节点链；真实工作区确认问题始终显示在对应答案前，编辑旧问题后只显示新活动分支，旧分支仍保留。
- 2026-07-15 回归：真实扫描页存在 23 个 OCR 可选块；选区文字通过“问 AI”进入当前 thread，Responses API 流先显示加载态再持续增量渲染，完成后 citations 和分支状态可刷新恢复。
- 2026-07-15 回归：修复历史 Chat 会话切换时的状态覆盖。列表 hydrate 继续按 workspace 替换服务端线程列表，单线程详情 hydrate 改为只按 `(workspaceId, threadId)` 精确替换缓存项，保留其他会话消息；补齐 A/B 切换、切回和跨 workspace 同 ID 隔离测试。
- 2026-07-15 回归：Chat 助手回答改用 `react-markdown + remark-gfm` 渲染标题、强调、列表、引用块、代码、表格和安全外链；正文中的已知 `[n]` 按服务端 0-based `citationIndex` 转为内联跳转按钮，未知编号、代码块和已有 Markdown 链接保持原样。引用跳转会打开对应文档、切到快照页码、平滑回到阅读区并短暂提示目标页面；工作区主题统一由 ThemeProvider、CSS 变量和 light/dark surface 样式控制，创建工作区弹窗也跟随主题。
- 2026-07-15 回归：修复上传处理中 PDF 阅读区反复刷新。文档状态轮询现在对未变化的文档复用对象和数组引用，无状态变化时不触发 Provider 更新；Viewer OCR 页面请求只依赖 workspace、document ID 和页码，不再依赖轮询生成的新文档对象。临时上传观测确认同一页请求不再持续重复，canvas 尺寸保持稳定。
- 2026-07-15 回归：修复 Chat 流式输出期间滚动条强制回到底部的问题。消息列表仅在用户已经停留底部时自动跟随新 token；用户主动上滑后暂停自动滚动，切换会话时重新定位到底部，并改为直接设置 `scrollTop`，避免每个 delta 排队平滑动画。
- 2026-07-15 回归：修复刷新后默认首个 Chat 会话只显示标题、不显示历史消息的问题。原因是线程列表更新 `threadCount` 后，工作区详情页重复调用 `switchWorkspace`，把刚选中的 `activeThreadId` 清空；现在重复选择同一 workspace 不再重置 workspace 视图状态，并补充选择状态回归测试。
- 2026-07-15 回归：补齐失败文档重试入库链路。失败文档可从侧边栏直接创建新的 `ingest` job，保留失败 job 历史并递增 `attemptCount`，清理旧错误后重新进入 `uploaded -> parsing -> chunking -> embedding -> ready`；API、BFF、Web Hook 和入口均已接通。
- 2026-07-15 回归：将文档删除从同步清理改为 `delete_cleanup` 异步任务。DELETE 先返回 `deleting + job`，Worker 成功后再删除对象、页面、chunk 并写入 `deleted_at`；清理失败保留错误并支持 `delete-retry` 重新入队，前端继续轮询文档状态。
- 2026-07-15 回归：建立 40 条人工标注检索评测集与 dense baseline CLI；当前 Ollama `qwen3-embedding:0.6b`、top-k=6 的 Recall@6=0.7708、MRR=0.7229、nDCG@6=0.6935、候选 citation 命中=0.8500，下一步在同一数据集上对比 hybrid/RRF 与 rerank。
- 2026-07-15 回归：增加离线 lexical/RRF 对比工具；同一 40 条数据集上 RRF 的 Recall@6=0.8167、MRR=0.7667、nDCG@6=0.7426、候选 citation 命中=0.9000，结果支持继续做 hybrid/RRF 生产实验，但尚未切换 Chat 默认检索。
- 2026-07-16 体验重构：工作区从固定 `PDF 主视图 + 窄 Chat 侧栏` 调整为 `Chat 主画布 + 按需 PDF 证据面板`；侧栏文档、citation 与笔记来源统一打开证据面板，支持全宽阅读模式和移动端覆盖层，Notes/Settings 改为主画布同级视图。后端契约、citation 定位、消息分支、PDF/OCR 渲染和保存语义保持不变。
- 2026-07-16 交互修正：Chat Markdown 使用标准 soft-break AST 插件，修复选择题题干与 A 选项粘连；笔记编辑改为原卡片内联替换；桌面 PDF 证据面板增加拖拽/键盘调宽和双击复位；PDF 工具栏增加指定页码输入并做范围收口。
- 2026-07-16 视觉修正：笔记编辑态改用固定主题表面，不再继承浏览态整卡 hover；普通卡片和编辑操作按钮补齐明暗主题 hover 前景/背景组合，避免低对比文字。
- 2026-07-16 检索质量验收：PostgreSQL 增加 lexical FTS GIN 与 trigram GiST 索引，拉丁术语使用全文检索、纯中文使用 Workspace 内 KNN 候选，Dense/lexical 按文档页执行稳定 RRF；同轮 40 条生产评测中 Hybrid Recall@6=0.8417、MRR=0.7354、nDCG@6=0.7394、citationHit@6=0.9250，端到端 p95=109.9ms，对比 Dense 增加 24.3ms；4 并发 40 条无错误和结果漂移。全部门禁通过，默认策略切换 Hybrid，保留显式 Dense 配置；API 同时启用 `ai_pdf_api` INFO 平面日志，使检索策略与阶段耗时在运行态可直接检索。收口验证为 API 76 passed、Alembic 单一 head 且模型无漂移、compileall 与 diff check 通过。
- 2026-07-16 阶段 9 收口：API/Worker/Web 镜像均为非 root，migration 从空库升级到 `a8c9d0e1f2a3`；API 暴露 HTTP/provider/retrieval/storage/job Prometheus 指标，Worker 私网 9101 暴露 job/active 指标。真实业务触发 Hybrid success、Ollama embedding、OpenAI stream success/error、storage 和 Worker claimed/handled，指标按 route template 与有界 outcome 记录。
- 2026-07-16 恢复演练：隔离 Compose project 中注册用户、创建 Workspace、上传两页 PDF、Worker ready、Chat 返回第 2 页 citation、保存 note；同批备份生成 PostgreSQL custom dump、MinIO mirror 和闭集 SHA-256 manifest。最终脚本在数据库用户对象、Redis key 和 MinIO bucket 均为空后执行恢复，MinIO list/find 失败显式中断；销毁全部容器/网络/卷后 55 秒完成恢复，用户/Workspace/ready 文档/citation/note/note_source 和 Alembic head 完整，恢复对象 SHA-256 与源 PDF 一致，七个长期服务达到 healthy/running 后才报告完成。
- 2026-07-16 安全与业务验收：Caddy 成为唯一公开入口，本地显式 HTTP smoke 返回 200、HSTS、nosniff、frame deny 和 referrer policy；Web/API/Worker/Postgres/Redis/MinIO API 未发布宿主端口。恢复后异步删除返回 202，delete job succeeded，文档列表和 MinIO 对象均消失。
- 2026-07-16 战略调整：保留 Chat-first 主画布和按需 PDF 证据层；第一用户收敛为基于论文、技术规范和评测报告做判断的 AI/软件工程师与技术研究者。下一阶段只设计并验证多模态 PDF Evidence；Asset/Representation/ContentUnit/EvidenceLocator 是目标域，不是已实施合同。Omnilabel 作为独立产品赌注，不作为普通格式扩展。
- 2026-07-16 Evidence 设计启动：建立第一用户任务验证协议，按事实、比较、方法、表格、图表和无答案任务记录支持结论完成率、核验后耗时和区域定位缺口；建立 `pdf_page/pdf_region` Draft RFC，明确当前 Citation/NoteSource 冻结合同、CropBox/旋转/多区域坐标提案、持久化选项和 6 项待批准决策。当前没有数据库、API、SSE 或保存语义变更。
- 2026-07-16 Evidence 设计夹具：新增不含机密数据的合成 PDF，后续扩为 12 页，覆盖 0/90/180/270 度旋转、每个旋转与非对称 CropBox 的组合、表格、向量图表、页内栅格图片、同页多区域和无文本层扫描页；生成器和 manifest 反向验证通过。当前 Citation/NoteSource fixture 严格通过现行 Pydantic schema，候选 `.draft.json` 只用于 payload 对照。
- 2026-07-17 用户验证工具：新增严格 18 列 CSV 校验和确定性 JSON 分析 CLI，按 manual/AI 工作流计算支持结论完成率、中位耗时、Citation 页码准确率与打开率、转笔记率、正确拒答率、无答案编造和区域缺口，并区分自动门禁的 `pass/fail/not_evaluable`。真实 PDF 数量、继续使用意愿和七日复用仍保留为人工证据。
- 2026-07-17 V3 范围裁决：下一版本正式范围调整为多模态 PDF + 独立图片；Chat-first 主画布保留，左侧升级为类型化 Asset 列表和证据范围，右侧升级为通用 Evidence Viewer。Audio、Video、Omnilabel 不进入 V3；真实用户验证延期为 Beta 门禁。
- 2026-07-17 V3 目标设计：新增 Asset/Representation/ContentUnit/Embedding、`pdf_page/pdf_region/image_region`、统一 locator 头、类型化扩展表、受控迁移和 PDF/Image renderer 设计；补充部署期封闭模态注册协议，后续 Audio/Video 只新增 adapter/locator/retrieval/renderer 模块，不迁移核心主链。该设计阶段仍冻结运行时变更，随后六项合同获批并进入 Phase 1。
- 2026-07-17 V3 Phase 1：六项合同已批准并完成不可逆迁移，Alembic head 升级到 `c9d1e2f3a4b5`；数据库、API、Worker 和 Web 已统一使用 Asset/Evidence，`/documents` 与 Document 业务类型已移除。Chat 支持 `all_ready | selected` Asset 范围并保存消息范围快照，Citation/NoteSource 返回完整 locator/sourceVersions，Evidence Viewer 使用封闭 renderer 注册表。
- 2026-07-17 V3 Phase 1 验收：API 103、Worker 18、Web 57 单测及 lint/tsc/build 通过；真实 PostgreSQL 完成 legacy -> V3 -> custom dump -> 空库 restore 的 payload 全等 oracle；浏览器捕获显式选中资产后的真实 `assetScope.selected` 请求，PDF 第 29 页定位、非空 canvas、分隔条键盘调宽和手机/平板无横向溢出通过。Critical 复审关闭 Image 提前开放、畸形 SSE terminal fail-open 和未知 locator version 三项 High：生产目录只启用 PDF，Image 在建 Asset 前拒绝，`done/error` 与 Evidence v1 均 fail-closed；开发库 catalog 与 registry 一致。
- 2026-07-17 V3 Phase 2 M201/M203：新增 Worker PDF adapter，统一由 PyMuPDF + pypdf 输出 PDF.js 一致的 MediaBox/CropBox、旋转后 display geometry；API ingestion 只编排 job/generation/事务/embedding，PDF adapter/persister 独立处理解析、OCR、representation/page/locator/ContentUnit。原生页继续使用原有 `pdf_text_chunk + pdf_page`，扫描页在不复制检索文本的前提下使用 `pdf_ocr_region + pdf_region`；同页不同 region 不再被 RRF 合并。
- 2026-07-17 Phase 2 M201/M203 Critical 修正与复审：修复旋转与非对称 CropBox 组合的 parser 交叉校验；将 PDF/Image coordinateSpace 在 API schema、codec、SSE 和 Viewer 固定为批准的 v1 值；共享 ingestion 改为 Worker 注册的通用 adapter dispatch；region 文本必须与 char range 精确一致。失败重处理 rollback、成功换代历史 Citation/NoteSource、spatial region dump/restore P0 oracle 通过，独立 Critical 复审关闭全部发现。
- 2026-07-17 Phase 2 M202/M204/M205 初轮证据：12 页 fixture、正式上传/Chat、Viewer 框选/缩放/页码/移动端和全量门禁均曾通过；随后独立 Critical 对抗审查发现初轮 fixture 未组合覆盖 artifact × 旋转/非对称 CropBox，且存在 table 检测污染 page 状态、混合图表候选重复、装饰图片 caption 误判和字符范围空间错绑。因此 M202/M205 完成结论已撤回，初轮数字只保留为历史证据；M204 已实现但仍需补翻页清草稿与 locator/canvas 像素 oracle。
- 2026-07-18 Phase 2 最终验收：新增 12 页 table/raster/vector × 四种旋转 × 非对称 CropBox matrix，并以实际像素验证 source region 最大误差 `0.001852`；修复 table 检测状态污染、严格 token 映射、caption/续注误判、传递重叠合并、artifact offset 语义、失败 Chat locator 清理和失败态 UI。真实上传摄取、retrieve -> SSE -> citation、Viewer 像素与翻页草稿链通过；最终 API 114、Worker 36、Web 62 与全部静态/数据库门禁通过，独立 Critical 复验 PASS。
- 2026-07-18 品牌迁移：产品与仓库统一命名为 Citeframe；GitHub 远端改为 `Gujiassh/citeframe`，本地目录改为 `/home/cc/code/citeframe`，origin、`@citeframe/*` 私有 npm scope、Web/API 标题、canonical 文档和 `code--citeframe` workbench 历史同步完成。内部 `ai_pdf_api/ai_pdf_worker`、`AI_PDF_*`、数据库、bucket 和镜像标识保持不变。新路径 API/Web readiness 200，桌面与 390×844 Chromium 品牌烟测通过。
- 2026-07-18 V3 Phase 3 M301：注册表 byte inspector 改为返回实际 canonical MIME，阻断 PNG/JPEG/WebP 交叉声明；PUT 对齐 upload-session Content-Type。新增 dormant Image adapter 与 Pillow 直接依赖，对静态单帧执行完整容器、两遍解码、64 MP、EXIF 1-8 校验，输出无 EXIF canonical PNG；WebP 严格验证 RIFF、唯一 bitstream/VP8X、chunk 顺序、reserved bits/bytes 及 ICCP/EXIF/XMP/alpha feature 一致性，合法 lossy/lossless RGB/RGBA 与对抗变异矩阵通过。`image_oriented` 与方向后 geometry 按 generation 保存。共享 ingestion 通过 generated-object manifest 统一上传派生对象，后续失败回收，删除覆盖原对象和全部派生对象；旧 generation 保留。10 个冻结格式/方向 fixture 的对象 SHA、像素 SHA、尺寸和区域公式通过，最终 API 135、Worker 73、compileall、diff check 与独立 Critical 复审 PASS；生产 Image 仍 disabled，Worker registry 仍仅 PDF。
- 2026-07-18 V3 Phase 3 M302：RapidOCR 核心收敛为像素到中立文本区域，Image/PDF adapter 分别拥有格式解码与结果映射；真实 1200×800 fixture 识别 8 个有界区域。新增 Image-owned OpenAI Responses caption provider，使用 canonical PNG data URL、`input_image` 与冻结的 provider/model/version/detail/max tokens，不扩展 Chat 文本 provider 合同；无 API key 环境只验证官方请求结构和错误语义，不宣称真实 caption 内容质量。`image_ocr/image_caption` Representation、`image_ocr_region/image_caption` ContentUnit、`image_region` locator 与 text embedding 按 generation 持久化，sourceVersions 绑定实际证据 Representation，geometry 与落库 oriented geometry 对照，图片 offset 保持 NULL。真实 job 产出 3 个 unit/vector 并进入 ready，caption-only、配置漂移、OCR 失败、geometry mismatch 和回滚 oracle 通过。模态配置通过 registry hook 贡献，共享 Asset router 不新增 Image 摄取分支。最终 API 140、Worker 79、Web 62 与全部静态门禁通过；生产 Image 和 Worker adapter 注册仍 disabled。
- 2026-07-18 V3 Phase 3 M303：共享 Evidence clone/serializer 增加 locator 与 Workspace/Asset/generation/Representation/typed detail 全链一致性校验，Image evidence 只接受 `image_ocr/image_caption`，拒绝把 `image_oriented` 当作结论来源；clone 在 typed detail/regions flush 后才返回，支持同事务 chained clone。Chat Citation 和 Citation -> NoteSource 无图片特判，损坏快照与 geometry fail closed。P0 oracle 在 generation 1 先创建并冻结 Citation/NoteSource，再切 generation 2，对两个 locator ID、完整 DTO、geometry、excerpt 与 sourceVersions 做前后全等；独立 Critical 复审 PASS。最终 API 150、Worker 79、Web 63 与全部静态门禁通过，生产 Image 仍 disabled。
- 2026-07-18 V3 Phase 3 M304A：新增 frozen Evidence 与 current Asset 两条权限保护的 `image_oriented` 文件流；前者按 frozen generation 与 OCR/caption Representation 解析历史定向 PNG，后者重新抓取 Asset detail 并只使用该响应的 current generation，409、无效 geometry、`orientationApplied=false` 和自然尺寸漂移均 fail closed 且可重试。Critical 回查后补齐 Representation/geometry 的 Workspace/Asset 连接约束与交叉引用对抗测试，并让 Viewer 在 capture 阶段消费框选取消的 `Escape`，避免同一按键关闭证据面板。Image renderer 支持适应窗口、100%、10%-400% 缩放、鼠标/单指平移、双指缩放、区域 overlay、鼠标/键盘框选草稿；手机工具目标 44px，桌面 32px。真实 1200×800 fixture 验证 frozen/current 分派、2/0 overlay、4800×3200 表面、鼠标与键盘平移/框选；390×844 下 6 个控件均为 44×44，CDP 双指缩放 28% -> 69%，无横向溢出、页面错误或失败请求。仓库 Playwright 强制 generation 1 流返回 409，验证重试 refetch detail 后只请求 generation 2、单指滚动 `(200,100) -> (280,160)`，以及 Escape 清除键盘框选但 Viewer 保持打开；临时数据库与 MinIO 计数清理为 0。最终 API 154、Worker 79、Web 75、定向 Playwright 1 与 lint、tsc、Next build、compileall、Alembic current/check、JSON、diff check 通过；图片流测试拆出后主 Asset router 测试文件从 2114 行降至 1950 行，最终独立 Critical 复审 PASS，无剩余 finding。M304 整体仍 blocked：框选后的 Ask AI / Note 会改变 Chat 请求与 NoteSource 保存合同，当前未获批准；生产 Image 继续 disabled。

- 2026-07-18 V3 Phase 3 M304B 后端：经明确批准后新增可扩展 `evidenceTargets` 和 user-message `inputEvidence` 快照，不复用 `selectionText` 或伪造 Citation。Image resolver 严格重新校验 Workspace、ready Asset、当前 generation、canonical geometry/SHA、同代 current-index OCR/caption locator；全部区域命中 OCR 才冻结 OCR，否则冻结唯一 caption，canonical oriented PNG 仅用于按十进制 floor/ceil 像素边界裁剪模型输入。Chat 可在普通检索为空时仅用显式区域回答，失败生成保留用户输入 Evidence；直接笔记创建 `messageCitationId=null` 的真实 NoteSource，混合来源保持旧 Citation 顺序且整体事务回滚。API `174/174`，PostgreSQL legacy -> head -> dump/restore oracle `1/1`，实际 Alembic head `d0e2f4a6b8c1` 和五项顺序/locator 约束通过。Web 框选动作、冻结输入重开 Viewer、真实 Playwright 与最终 Critical 复审仍待完成；生产 Image 保持 disabled。
- 2026-07-19 V3 Phase 3 M304B 最终验收：Image Viewer 仅在 current generation 上将规范化框选提交为 `evidenceTargets`；Chat 请求被服务端接受后才切回主画布，失败保留框选；直接笔记持久化成功后切到 Notes。历史 user message 的 `inputEvidence` 与无 Citation NoteSource 都可按 frozen generation/Representation 重开同一区域。HTTP 接受后立即显示不可点击的输入 Evidence 锁定状态；SSE 中断且恢复 GET 同时失败时仍保留已持久化 user message 与锁定状态，只将 assistant 收敛为 failed。独立 Playwright 验证 422 保留、成功 SSE/hydrate、请求体白名单、自动显式 Asset scope、输入 Evidence 恢复、`messageCitationId=null` NoteSource 和两次 frozen Viewer 跳转。收口部署审查真实复现并修复 API 镜像 deploy lock 缺 Pillow，修复镜像 `sha256:0bcb53c0a4d9` 以 UID `10001` 成功导入 Pillow `12.3.0` 和应用模块，实际 `/health/live` 返回 200。Critical 初审还发现直接 Note 未读取 canonical 图片对象，以及 failed assistant 虽可在 service 续问却被 HTTP router 拒绝；修复后，Note 即使不生成 crop 也校验对象存在性、SHA、PNG 与自然尺寸，缺失/损坏对象时 Note、NoteSource、新 locator/detail/regions 全部零残留，真实 `/chat/stream` 可从 failed assistant 继续且仍拒绝 streaming parent。最终 API `178/178`、Worker `79/79`、Web `82/82`、Playwright `1/1`、lint、tsc、Next production build、compileall、Alembic current/check、PostgreSQL migration/dump/restore、JSON 与 diff check 通过；独立 Critical 复审 `PASS`，无剩余 finding。生产 Image 仍 disabled，下一步进入 M305。
- 2026-07-19 V3 Phase 3 M305 最终验收：共享 retrieval 候选移除 PDF page/detail，由 locator codec 生成稳定语义 key；ModalityRegistry text channel 的 8 条精确四元签名覆盖当前 PDF/Image persister 产物且不形成笛卡尔积。Dense/lexical 在排序前应用 Workspace、Asset scope、current index/generation、Representation/locator/embedding 一致性，并在 limit 前补足唯一 locator；4 条额外同页 PDF chunk 下 SQLite/PostgreSQL 都保持 `[pdf,image,image]`。Evidence detail/regions 批量 fail-closed 校验把单次真实 Hybrid SQL 从 `63` 降到 `7`，缺失 detail、缺失 region、非法 geometry 均有拒绝回归；离线 LexicalCorpus 复用同一生产 scope。正式 40-case `assetId` 报告的 Hybrid Recall 增益 `0.0708`、citation hit 增益 `0.0750`，端到端 p95 增加 `69.3 ms`、比例 `1.650x`，并发 `0` error/`0` drift，默认 Hybrid 门禁通过。最终 API `190/190`、Worker `79/79`、Web `82/82`、PostgreSQL oracle `1/1`、Playwright `1/1`、lint、tsc、Next build、compileall、迁移/恢复与 diff check 通过；独立 Critical 复审关闭全部 finding。生产 Image 仍 disabled，进入 Phase 4 工程验收。
- 2026-07-19 V3 Phase 4 M401：新增严格 `multimodal-golden-v1`、`multimodal-failures-v1` 与确定性 coverage report。黄金集将已有 40 条真实 PDF retrieval 数据作为 hash/case-count 冻结的 reference baseline，并以 3 个非机密确定性 source fixture 建立 21 个 PDF/Image/mixed 工程 case，retrieval/evidence/answer 各 7 个，覆盖 7 类任务与 2 个 no-answer。失败 taxonomy 固定 10 类，首批只收录 6 个有持久化回归测试的真实历史 failure。校验器对未知字段、规范路径/文件/source+manifest hash、坐标合同/几何、scope、typed locator、层级语义和覆盖门槛 fail closed；40-case baseline 复用现有严格 label loader，失败复现只接受 API/Worker pytest 中模块顶层、AST 可见的 `testFile + testName` 并生成结构化 argv，不接受自由命令或路径穿越。定向测试 `18/18`、API `208/208`、Worker `79/79`、Web `82/82`、compileall、lint/tsc/build、确定性报告与 diff check 通过；最终独立 Standard 复审 `PASS`。`coveragePassed` 只表示评测合同完整，不宣称模型回答质量或用户价值通过；生产 Image 继续 disabled。
- 2026-07-19 V3 Phase 4 M402 最终验收：单一 Worker node 直接消费 21-case golden set，真实执行 19 个 PDF/Image Evidence target adapter/locator、7 个生产 Dense/lexical/RRF/scope retrieval case 和 7 个 scripted Chat 编排；无 `page.route` 真实 BFF Playwright 在 1440x1000 与 390x844 下分别完成 7 Evidence case/8 target，生成 16 张截图，最小 approved-area coverage `0.294333`。预调用工具经独立 Standard 对抗复审 `PASS` 后，按明确批准向当前 `openai / gpt-5.5` 配置且仅发送 7 条非机密合成 prompt；全部请求无 provider 错误且 citation target 全覆盖。严格完整输出 allowlist 初次接受 1 条，其余 6 条正确改写经人工逐条对照 Evidence 后加入冻结 oracle；raw output/messages 和 capture-time false diagnostics 保持原样，正式报告忽略自报判分并独立复算。最终报告登记 16 张截图、4 个 raw 和 answer oracle 共 21 个 SHA-256 artifact，21 case 全部 `passed`，`engineeringExecutionPassed=true`、`fullStackEvidencePassed=true`、`realModelQualityPassed=true`、`releaseGatePassed=true`、`pending=[]`。最终 API `226/226`、Worker `84/84`、Web `82/82` 与 lint、tsc、Next build、compileall、Alembic、报告确定性重放和 diff check 通过；生产 Image 继续 disabled。

## 2026-07-28：V4 R800 确定性工程基线（已完成）

- R200-R700 已完成 PostgreSQL/Alembic Research 与 Evaluation 账本、固定 typed executor、Evidence-only tools、HITL/Research SSE/retry/recovery、Web Research 体验、OTel/Prometheus 与 owner-only Evaluation Dashboard。
- R800 v1/v2/v3 失败记录完整保留。v2 暴露 provider/tool completion 与 reservation 的反向锁序，v3 证明死锁消失后又暴露 scripted stub 的 Claim 状态误判；修复均有定向回归。
- provider/tool 共享锁序统一为 `Attempt -> Step -> Run -> call -> BudgetLedger`，锁查询显式刷新 identity map；已发送调用在 Run 取消后继续结算，未发送 reservation 仍禁止发送。
- canonical v4 结果：`engineeringGate=pass`、`releaseGatePassed=true`，provider `maxActive=2`，一次 transient failure/一次 retry，三个 unsupported Claims/零 final links，一个 conflict Decision，最终 Artifact API/DB 均唯一。
- PostgreSQL/MinIO 空部署恢复前后语义 SHA 均为 `a60fa5eaf70a86e47d3de1b17a7c49561a2c6cfbc369554fc1d94a9567bab6a8`；容器、卷、网络和 secret env 零残留。
- canonical 文档入口为 `docs/evals/r800-critical-review.md`、`docs/architecture/research-workflow-runtime.md` 与 `docs/evals/r800-demo-script.md`。
- scripted provider 不能评价真实模型；R803 与 M404 均保持 `not_evaluable`，不改变 `internal_preview`。

## 7. 下一步

下一步：`在明确批准真实 provider 与成对 comparison keys 后执行 R803；M404 继续收集目标用户证据。两者未完成前不扩大产品发布声明。`

具体建议从这些内容开始：

1. R803 使用同一 fixture、Asset scope、provider/model、Workflow/Prompt comparison keys 运行 Quick/Research 成对质量，不复用 scripted R800 结论。
2. M404 真实用户任务验证继续收集；结果未完成前产品继续作为内部预览。
3. Audio/Video 仍按独立模态 adapter/locator/Viewer 立项，不和 V4 workflow 状态机混成一次迁移。

## 8. 当前不进入主线

当前不进入主线：

- 音频、视频的一次性全模态接入
- 把 Omnilabel 标注/预测/数据集分析当作文件格式扩展
- 复杂 Agent 编排平台
- 多模型策略路由
- 复杂权限系统

## 9. 更新方式

后续每推进一个大步骤，都更新这份文档的：

- `当前总状态`
- `阶段进度`
- `当前正在做什么`
- `下一步`
## 2026-07-20：V3 M403 初次销卷恢复与 Critical 重开

- 新增 `m403_restore_acceptance.py`，以 UUIDv5 和固定时间种出 PDF/Image 两代、当前/旧 index、失败/删除 Asset、PDF/Image typed locator、all-ready/selected scope、MessageInputEvidence、四条 Citation、citation-backed/direct NoteSource 和历史对象语义。
- 新增隔离 Compose 编排与 readiness-only provider stub；真实备份 PostgreSQL custom dump 与 MinIO closed mirror 后删除 project 容器、网络和 5 个卷，再恢复到新空卷。stub 只回答 `/api/tags` 健康检查，不执行 embedding，不作为模型质量证据。
- 恢复前后 26 类数据库行/目录、9 个活跃对象 SHA-256、删除对象缺失状态、typed detail/regions、历史 generation 与 raster pixel oracle 严格全等，语义 SHA-256 均为 `1ccf86f3113a9d5a7be232d92080928758eb961779b59d38f5869f04c2f7719a`。
- 初次无 route mock 的 Playwright 在桌面 1440x1000 和移动 390x844 重放历史 PDF/Image；Critical 复审确认旧 oracle 只比较非白/颜色计数与 overlay 数量，无法排除同统计量 generation 漂移，且最终 cleanup 没有进入 release gate。因此旧 `releaseGatePassed=true` 只保留为数据库/对象诊断证据，不能继续作为最终 M403 证明。
- runner 已升级为完整 raster pixel SHA-256、规范化 overlay geometry、citation/viewport/phase/result cardinality 和最终容器/卷/网络零残留 gate，等待正式重跑。生产 Image 保持 disabled。
- 加强后的 `citeframe-m403-release-v2` 已从空隔离部署完成正式重跑。9 个 MinIO 对象和 27 类表/目录计数及语义恢复前后严格全等，语义 SHA-256 均为 `6b2a8758100229641271e7ced81c238a8ee69d7066c1b5076de8af002a8079c3`；桌面/移动端 PDF/Image 完整 raster SHA-256、规范化 overlay geometry、citation/viewport/phase/result cardinality 全部通过，历史 Image 像素绑定 generation-1 冻结 SHA。最终 Compose down 与容器/卷/网络检查退出码均为 `0`、实际残留均为 `0`，正式报告 `releaseGatePassed=true`。独立 Critical 评审服务连续因外部 `503/429` 未返回，主控制器已复核正式 artifact 与 oracle；不将外部服务失败伪记为代码 finding。M403 完成，生产 Image 仍 disabled。

## 2026-07-20：V3 M403A S1 diagnostic 与 oracle 加固

- S1 首轮 HNSW build 因容器 `shm_size=1g` 小于 `maintenance_work_mem=2GB` 而失败；隔离 override 调整为 3 GiB，并增加防回归测试，项目总资源仍为 PostgreSQL 3C/6 GiB + runner 1C/2 GiB。
- 修正后完成 100k Dense 可见、140k 物理 ContentUnit 和 150k 旧语料 embedding 的诊断运行：装载加索引 `130.309s`，HNSW `70.056s`，D8 4 轮/150 ranked rows，Latin GIN 命中，8 并发 32 次无错误/漂移，最终容器/卷/网络零残留。
- 真实 warm plan 仍从 8 个 Asset/Representation 扫出 100k ContentUnit，再做 100k embedding FK probe 与 exact top-N sort；HNSW 未被选择，Dense 约 `943-956ms`，因此 diagnostic 报告正确为失败。Critical 裁决阻止正式三档执行，当前改为显式有界 ANN candidate stage 后再套用不变的 current-chain/type/scope eligibility。
- M403A 语料/报告升级为 80% 500 字符 + 20% 1200 字符、实际 cohort x 8 signature/D1-D8-D64 持久化指纹、错误 provider-only ContentUnit、Dense/lexical 可见集合分报、最终 Evidence location Recall、all-ready/selected 计划、Docker inspect/cgroup 资源和带来源/公式成本。子集执行一律 `debugOnly`。
- production Dense 改为先从匹配 embedding metadata 的表执行有界 `MATERIALIZED` HNSW candidate stage，再应用原有 Workspace/Asset/current-chain/type scope；S1 warm plan 已从 exact sort 改为 HNSW，Dense p95 从约 `943-956ms` 降到 `10.2ms`。
- 初版 64 维全随机合成向量没有形成签名语义簇，S1 的目标签名独占门必然失败且最低 location Recall@10 仅 `0.80`。语料修正为 8 个正交签名中心加 56 维确定性 locator 扰动，D1/D8/D64 重复与全部噪声规模保持不变；新 S0/S1 diagnostic 的 8 类 Recall@10 均为 `1.00`，S1 全部子门禁通过、最终资源零残留。子集仍只作诊断，不构成发布证据。
- 首次完整 S0/S1/S2 canonical 正确 fail closed：S1 因 `ef_search=100` 的近似图波动出现 `0.90` Recall，S2 最低 Recall `0.60`；S2 Latin lexical p95 `226.6ms`，连带 Hybrid `254.4ms`、8 并发 `893.4ms`/`11.67 req/s` 未达标。其他 HNSW/GIN、scope/current chain、Dense p95、buffer、6.92 GiB 容量、`1283.684s` 装载建索引和零残留门均通过。
- 根据失败证据，将 Latin FTS 改为 ContentUnit-only `MATERIALIZED` 候选前缀，返回前仍执行完整 scope/current-chain/type 约束并按源匹配总数扩窗；单词查询跳过恒为 1 的全文 `ILIKE` 覆盖计算，首窗使用 `2 x limit`。HNSW 查询深度收敛到 `ef_search=400`，生产与验收配置一致。修正后 S1 diagnostic 再次 8 类 Recall `1.00` 且 HNSW/GIN 命中，Dense/lexical/Hybrid p95 为 `22.3/45.1/61.2ms`，8 并发 p95 `187.2ms`、吞吐 `57.0 req/s`，准备重新执行完整 canonical。
- 第二次 canonical 在 S1 seed 后的 PostgreSQL restart 暴露基础设施缺口：后台 WAL checkpoint 未完成时，Compose 默认 10 秒 stop 超时会强杀数据库，随后 crash recovery 超过 60 秒 health 窗口。seed 现显式执行 `CHECKPOINT` 并把耗时计入 `loadAndIndexSeconds`；部署 PostgreSQL 增加 5 分钟 graceful stop，避免把未计入的后台刷盘成本转移到重启阶段或在生产重启中强杀数据库。
- 第三次 canonical 在宿主连续大规模 I/O 后，S2 的 700k embedding insert 单条查询运行 `39m20s` 仍未进入 HNSW，已确定不可能满足 45 分钟总门限，因此主动中止并由 trap 清零资源。根因是 seed 先为约 215k locator 物化完整 1024 维临时 vector，再回读写入 700k 正式行；临时表现只保存 64 个有效 signal 分量，在最终 insert 时补 960 个零并 cast 为同一 `vector(1024)`。S0 真实运行确认 dataset checksum、持久化指纹、Recall 和所有语义门不变，load `7.6s`、显式 checkpoint `23.0s` 均计入。
- 第四次 canonical 在宿主 I/O pressure 较高时，初始 S0 PostgreSQL init 用时约 66 秒，超过 runner 的通用 60 秒 health 窗口后被误判失败；数据库日志显示其随后正常 healthy，未发生数据或查询错误。M403A 的初始与冷重启 health/SQL wait 均显式设为 300 秒，该等待不计入 seed/query 性能数据；正式容量运行只在外部 I/O pressure 回落后启动。
- 第五次 canonical 完整执行并清零全部 S0/S1/S2 容器、卷和网络。S0/S1 全部门通过；S2 的 HNSW/GIN plan、scope/current chain、D8/D64、buffer、Dense/lexical/Hybrid p95 `43.0/82.9/141.4ms`、数据库 `6.92 GiB` 和装载建索引 `1775.819s` 通过，但两个 D1 case 的 Recall@10 为 `0.80/0.90`，8 并发 p95 `1002.6ms`、吞吐 `11.62 req/s` 未达冻结阈值，因此 `releaseGatePassed=false`。S2 Latin warm plan 为每条查询额外启动 2 个 parallel worker，与 PostgreSQL 3C 和 8 个并发请求形成争抢；当前先在同一 S2 seed 上验证禁用 per-gather parallelism，并用 ANN window/`ef_search` 矩阵定位最小召回修复，不降低任何阈值。
- 同一冻结 S2 corpus 的保留库矩阵排除了无效方向：ANN `2x` overfetch 在 `ef_search=400/800` 下不改善最低 Recall；`ef_search=800/1200` 仍失败；per-gather worker `0/1/2` 均不能同时满足 lexical p95、8 并发 p95 和吞吐。HNSW `ef_construction=96` 最低 Recall 仍为 `0.90`，`128` 首次让 8 类 Recall 全为 `1.00`；重建 `759.1s`、索引 `1803 MiB`，在冻结资源/时间/容量内，因此 production model、migration 与 capacity seed 统一固化 `128`。
- 并发分解证明 Dense-only p95 `91.2ms`/`139.8 req/s`，Lexical-only p95 `918.3ms`/`15.37 req/s`，瓶颈完全在 Latin FTS 对匹配文本重复构造 `to_tsvector` 后执行同一 `ts_rank_cd` 排名。保留库诊断中 stored generated `search_vector` 让 GIN/排名复用同一列，保持 term coverage、`ts_rank_cd`、candidate limit、完整 scope/current chain 和 RRF 不变；两次运行均全门通过，第一次/第二次 8 并发 p95 `213.9/233.4ms`、吞吐 `66.18/62.08 req/s`。迁移 `106.8s`、数据库增加约 `148 MiB`。Owner 已批准并实现 `e1f3a5c7d9b2`，生产库已升级、`alembic check` 无新操作，定向 19、混合检索 9、API 全量 265 测试通过，待完整 canonical。
- current-chain 修复后的 HNSW 图质量实验没有降低冻结阈值：`ef_construction=256` 的完整 canonical 将 S2 最低 Recall 从 `0.80` 提升到 `0.90`，`512` 的 fresh S1 达到全部 Recall `1.00`，但最新完整 S0/S1/S2 canonical 仍在 S2 `image-ocr:D1` 得到 `0.90`。该次 S2 Dense/lexical/Hybrid p95 为 `16.0/20.4/36.0ms`，8 并发 p95 `261.8ms`、吞吐 `63.09 req/s`，数据库 `7.07 GiB`，HNSW `1.67 GiB`，其余 gate 与最终零残留全部通过。正式 artifact 为 `docs/evals/artifacts/m403a-efconstruction512-failed/report.json`；M403A 保持未完成。
- `m=24 + ef_construction=512` 的隔离 S1 diagnostic 已否决并从代码撤回：9 个 all-ready/selected Recall 均为 `1.00`，但 planner 不再选择 HNSW，Dense p95 `116.3ms`，8 并发 p95 `5188.0ms`、吞吐 `6.15 req/s`。该中间连接度不能同时满足计划与性能门，不进入 S2。
- filtered HNSW 的 `relaxed_order` 也被 S2 debug 否决并撤回：HNSW 计划、性能和并发保持通过（Dense/lexical/Hybrid p95 `17.3/19.6/36.1ms`，并发 p95 `219.8ms`、吞吐 `68.98 req/s`），但 `image-ocr:D1` Recall 仍为 `0.90`。外层 `MATERIALIZED` CTE 的 distance 重排未补回缺失位置，生产与验收恢复 `strict_order`。
- HNSW 连接度的二分诊断也已关闭：`m=20` 与 `m=18` 的 S1 全部 Recall 均为 `1.00`，普通 all-ready Dense 仍命中 HNSW，但 selected scope 都改走 `asset_id` 索引并做 exact sort，导致 `hnswPlan=false`。两者均在 S1 撤回，未进入 S2；默认 `m=16` 是当前同时满足 all-ready/selected HNSW plan 的已验证边界。
- 串行 HNSW build 用于验证并行建图波动：S1 全部门通过，HNSW `116.4s`、总 load/index `186.3s`；但 S2 在 HNSW `85%` 时已耗时约 21 分钟，按最近 137 blocks/分钟计算，结合约 7 分钟 load，完成前即确定超过 45 分钟门限。runner 被主动中止并由 trap 清零容器、卷和网络，串行 build 配置已撤回；不能用牺牲容量门换取可能的 Recall 稳定性。
- 最终迁移往返验证从 `f2a4c6e8b0d1` downgrade 到 `e1f3a5c7d9b2`，确认旧全量 HNSW `ef_construction=128`、current-chain 列和 trigger 均移除；再 upgrade 回 head，确认 current-only partial HNSW `ef_construction=512`、360/360 current、0 invalid 和 2 个 scope trigger。最终 API `277 passed, 1 warning`、Worker `93 passed`，Alembic check、compileall 与 diff check 通过。

## 2026-07-20：M404 诚实的未评估自动化

- 新增严格 `user-task-validation-manifest-v1`，结构化记录 participant/asset/task 资格；开发者自测、合成用户和模型代理不能计入真实目标用户，任务按 `(participant_id, task_id)` 去重，只有任务实际引用的真实复杂资产计数。
- 只有 5 名真实目标用户、20 个合格任务完成、3 份复杂 PDF、2 张复杂图片及来源/版式多样性全部满足，质量门才进入 `pass/fail`；此前顶层和全部质量门都为 `not_evaluable`。
- 自动报告始终固定 `userValueValidated=false`、`productStage=internal_preview`，因为 qualification evidence、继续使用意愿和七日复用仍需真实研究裁决。canonical 空报告 `docs/research/user-task-results-report.json` 由空 manifest + header-only CSV 生成，CLI 退出码为 `2`。

## 2026-07-24：M403B 生产 Image 启用与发布验收（已完成）

- Owner 已批准 M403B；冻结 oracle 为只接受精确 `application/pdf`、`image/png`、`image/jpeg`、`image/webp`，禁止 `image/*`、空 MIME、按扩展名猜测和 PDF fallback。Citation、NoteSource、Chat、Asset/Citation/NoteSource payload、持久化字段和保存语义保持不变。
- 新增 Alembic `a3c5e7f9b1d4`，只把 `asset_types.image.enabled` 从 `false` 切换为 `true`；升级/降级均校验 catalog contract v1，不新增表或字段。API `IMAGE_MODULE` 与 Worker `ImageIngestionAdapter` 已进入生产 registry；caption provider 继续复用已冻结的 OpenAI provider/model/version/detail/token 配置。
- Web production upload contract 统一暴露 PDF/PNG/JPEG/WebP MIME 与扩展名；两个侧栏入口共用该合同，空/未知/声明与扩展不一致在创建 upload-session 前 fail closed，BFF 缺失 Content-Type 返回 `415`，不再默认为 PDF。失败 Asset 展示截断错误原因，移动端 retry/delete 目标保持 `44px`。
- API/Worker 强化：Worker 在 adapter 前校验下载源对象长度与已持久化 SHA-256，初次摄取和 retry 的篡改对象都以 `source_object_integrity_mismatch` fail closed；legacy `source_sha256=NULL` 合同不被重写。部署 Compose 与示例显式共享六个 `AI_PDF_IMAGE_CAPTION_*` 参数，Image 启用时 readiness 额外返回 `imageCaptionConfiguration`，不为探针调用 provider。
- 生产 plumbing 报告 `docs/evals/artifacts/m403b-v2/`：PNG/JPEG/WebP 均经 API `201/204/200` 到 `ready`；MIME mismatch 为 `422`；确定性瞬态失败在同一源 key/bytes/hash 上从 attempt 1 `failed` 到 attempt 2 `succeeded`；PNG retrieval 6/6 为 `image_region`，Evidence Chat `inputEvidence=1`、Citation=6；两条删除链都要求 Asset `deleted`、`deleted_at`、job `succeeded`、派生内容行和对象零残留。
- 浏览器报告 `docs/evals/artifacts/m403b-browser-v1/`：无 route interception 的真实 session/BFF/API/MinIO/长期 Worker 链在桌面上传 PNG/JPEG/WebP，在 `390x844` 上传 PNG；Viewer 像素 `1200x800`、34 个采样颜色、290 个非白采样，panel/viewer/surface 均在视口内，scroll width 等于 client width，移动端 6 个图像工具全部 `44x44`。初次真实运行发现 loading 分支提前跳过一次性 ResizeObserver，修复为 Viewer ready 后重新绑定；同时修正 Asset 删除按钮误用“删除工作区”文案。
- 恢复报告 `docs/evals/artifacts/m403b-restore-v2/`：在最新代码上显式 `M403_EXPECT_IMAGE_ENABLED=true` 重跑，恢复前后语义 SHA 均为 `c4c8ab66e050bdbbaa33f3b3d0af3fd3f5fe21df3e6cca5988a3af113a86bd4d`；桌面/移动 PDF/Image raster/overlay 回放、9 个对象、27 类表/目录计数和最终容器/卷/网络零残留全部通过。目录 15 个正式文件均进入 `SHA256SUMS`。
- 最终验证：API `285 passed, 1 warning`，Worker `96 passed`（其中 restore focused `12 passed`），Web `85 passed`，readiness focused `8 passed`，生产 browser `2 passed`；API/Worker Ruff、compileall、Web ESLint、TypeScript、Next production build、Alembic current/check、Compose config、artifact SHA 和 diff check 通过。Critical finding 已关闭，工程门禁 `releaseGatePassed=true`；deterministic provider 报告固定 `modelQualityClaim=false`，M404 用户价值仍为 `not_evaluable`。

## 2026-07-24：文档一致性审计与 V4 计划补强

- 当前主入口已同步 M403B/V4 状态；当前数据库 head 为 `e8f1a2b3c4d5`，Image 已由 M403B 正式启用，R000-R800 确定性工程基线已完成。旧 Document/PDF-only 章节的逐段清单记录在 V4 `requirements-discovery.md` 第 11 节，R000 `RD003` 已关闭；历史 ER 与旧规划不得作为当前 Research 合同输入。
- 历史 V1/V2 规划、旧 Document 状态机、认证执行清单和 V3 Contract Draft 已加 legacy/历史状态说明，保留原始阶段证据但不再作为当前实现入口；Evidence RFC 与 migration impact 的 Image/restore 未完成项已同步关闭。
- V4 方向、阶段和非目标已经明确，但 R000 仍未完成：新增字段级 schema、唯一/幂等键、状态迁移、事件 payload allowlist、API error matrix、provenance、删除/恢复和审批记录要求；在这些合同获批前不实现 Research 持久化或 API。
