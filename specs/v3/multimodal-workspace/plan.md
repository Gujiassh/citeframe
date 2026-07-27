# V3 多模态工作区实施计划

## Phase 0：合同批准

- 评审 Asset/Representation/ContentUnit/Embedding 目标结构。
- 冻结 `pdf_page/pdf_region/image_region` 与坐标定义。
- 冻结 Asset、Citation、NoteSource、Chat `assetScope` 与消息范围快照 API。
- 确认一次受控迁移、历史回放、删除和恢复语义。
- 冻结 ModalityModule、Evidence locator、retrieval channel 和 Web renderer 扩展协议。

## Phase 1：Asset 基础迁移

- 建立 Asset、Representation、ContentUnit、类型化 region 和 Embedding 表。
- 机械迁移现有 PDF、page、chunk、embedding、tag、citation 和 note source。
- 更新备份恢复 oracle 与迁移回滚测试。
- 切换 API、Worker 和 Web 领域类型，移除 Document 业务模型。
- 用测试模态验证后端/前端注册、locator codec、候选序列化和 renderer 调度，不启用生产功能。

## Phase 2：PDF 多模态证据

- 接入页面几何、layout、OCR bbox、表格/图表/图片区域。
- 生成 PDF ContentUnit 与 `pdf_page/pdf_region` Evidence。
- 更新 Chat citation、NoteSource 和 PDF Viewer region overlay。
- 用旋转、CropBox、扫描、表格、图表和多区域 fixture 验收。

## Phase 3：独立图片闭环

- 接入 PNG/JPEG/WebP 上传、方向归一化、OCR、caption 和区域处理。
- 生成图片 ContentUnit、文本/caption embedding 和 `image_region` Evidence。
- 实现 Image Evidence Viewer、框选提问和框选笔记。
- 验证全部资产与显式资产范围下的 PDF/图片混合问答。

当前状态：M301-M305、M401-M403B 已完成。加强后的 M403 正式销卷恢复报告已通过完整数据库/对象语义、桌面/移动端 raster/overlay 和最终零残留门。M403A binary64/3N fresh S0/S1/S2 canonical 的三档全部通过，正式报告 `releaseGatePassed=true`；S2 9/9 Recall=`1.00`、load/index `2062.742s`、并发 p95 `246.531ms`。M403B 已完成 PNG/JPEG/WebP 生产上传、immutable-source retry、检索/Evidence、长期 Worker 浏览器链、Image-enabled 销卷恢复和 Critical 复审，工程发布门禁 `releaseGatePassed=true`。

M305 不新增对外 API 字段。检索内部已为 `content_unit_embeddings` 增加 `asset_id / processing_generation / index_version / is_current` 投影字段，让 Dense ANN 在向量表内先过滤 current chain 和显式资产范围；这不改变 Asset、Citation、NoteSource、Chat 或保存语义。`f2a4c6e8b0d1` 完成回填、partial HNSW 和 current-scope trigger；摄取以 inactive 写入、latest CAS、Asset 指针切换、目标 provider 激活的同一事务维护 current 投影，Dense/SQLite 与外层 Representation/Locator 校验保持一致。PDF-only 评测适配器可以在边界上读取 PDF typed detail，但不能反向污染共享候选模型。

## Phase 4：质量与发布

- 使用 M401 已冻结的 40-case 真实 PDF reference baseline、21-case PDF/Image/mixed 工程黄金集和回归失败分类。
- 只有 caption/OCR 检索缺口明确时实验视觉向量。
- 跑 API/Worker/Web、Playwright、定位像素对比和销卷恢复。
- 用大规模分层 ContentUnit 语料验证 pgvector/HNSW、lexical 执行计划、buffer 命中和 p95；当前 318 条 PDF ContentUnit 报告不能替代容量证据。
- 完成真实用户任务验证后进入 Beta；评测未完成时只标记内部预览。

M403 固定使用隔离 Compose project：写入同时覆盖 PDF/Image、当前/历史 generation、当前/历史 index、失败/已删除 Asset、PDF/Image typed locator、Message scope、输入 Evidence、Citation 和两类 NoteSource 的确定性语料；生成备份前语义与对象哈希快照，完成真实 PostgreSQL + MinIO 备份后删除整个 project 及卷，再恢复到空部署并要求快照严格全等。任何数据库行、对象 SHA、历史 generation、直接 NoteSource 空 Citation 语义或服务健康差异都判失败。

M403A 分 S0 10k/14k、S1 100k/140k、S2 500k/700k（Dense 可见/物理 ContentUnit）执行，只有同一次完整 S0/S1/S2 执行可形成发布报告；子集一律 `debugOnly`。PDF/Image 为 80/20，覆盖 production text channel 全部 8 个类型签名，额外 40% 均分为范围外 Workspace、旧 generation、旧 index 和仅带错误 provider/model/version embedding 的 current-chain 行。由于 lexical 不读取 embedding metadata，报告分别登记 Dense eligible 与 lexical current-chain。语料冻结为 80% 500 字符、20% 1200 字符，并保存实际 cohort x signature、D1/D8/D64 行/位置分布和持久化指纹。Production Dense 先在 embedding 表执行有界 MATERIALIZED ANN candidate stage，再套用原 current-chain/signature/scope eligibility；exact oracle 仍使用未预限候选的完整 scoped SQL。报告包含 all-ready/selected HNSW/FTS GIN JSON plans、按最终 Evidence location 的 D1/D8/D64 Recall@10、shared-buffer cold/warm、current-chain 排除项、D8/D64 补足、串行/并发 p50/p95/p99、吞吐、错误/位置漂移、实际 cgroup/inspect 资源、索引/数据库尺寸、建库耗时和带来源/时点/公式的月存储成本。固定项目总 4C/8G 下，S2 要求 HNSW/GIN 被选择、最小 Recall@10 >=0.95、D8 不超过 4 轮/150 ranked rows、warm Dense/lexical/Hybrid p95 分别 <=100/150/250 ms、8 并发 Hybrid p95 <=400 ms且吞吐 >=20 req/s、Dense/Latin buffer hit 均 >=0.90、数据库 <=12 GiB、加载和建索引 <=45 分钟、错误和漂移为零；任一项失败都必须保持 `releaseGatePassed=false`。

最新 `ef_construction=512` 完整 canonical 严格保持 `releaseGatePassed=false`：S2 `image-ocr:D1 Recall@10=0.90` 是历史 cosine-only 失败项；双索引有效 S2 diagnostic 已达到 9/9 Recall=`1.00`，但 load/index 仍超 `2700s`。不得因 Recall 已修复或宿主 I/O 波动而放宽容量门禁。

`ef_search`、candidate overfetch、`ef_construction=256`、`m=18/20/24/32`、`relaxed_order` 和串行 HNSW build 均已有真实否决证据；cosine `ef_construction=512` 与 binary `ef_construction=512/128` 的双索引 S2 已证明 Recall 可达 `1.00`，但容量或并发仍超门。当前最终候选只验证 binary `ef_construction=64` + `3N`，不重复已否决配置。

Owner 已批准双索引 ANN 候选架构：保留 current-only cosine HNSW，新增 `binary_quantize(embedding)::bit(1024)` 的 current-only Hamming HNSW；生产 Dense 在两个独立 `MATERIALIZED` candidate CTE 中取候选，按 embedding identity 合并去重，再用原始 `vector(1024)` cosine distance 精确重排，最后进入不变的 Asset/Representation/Locator current-chain、类型和 Workspace/selected scope 校验。该方案不增加持久化字段，不改变 API、Citation、NoteSource、Chat 或保存语义；migration 增加一个 expression index 和维护窗口成本，容量 runner 必须分别证明两类 HNSW plan、Recall、索引尺寸和总 load/index 仍满足冻结门禁。

双索引 fresh S1/S2 已持续把 9/9 all-ready/selected Recall 提升到 `1.00`，两类 HNSW plan 保持命中。binary128 的最干净 S2 将 load/index 降至 `2721.264s`，只超门 `21.264s`，但并发 p95 `424.622ms` 仍超门 `24.622ms`。当前最终辅助预算候选使用 binary `ef_construction=64` 与 `3N` 候选，主 cosine 保持 `512/N`，最终仍只按原始 cosine 精排；必须重新通过 S1/S2 全门，不能降低阈值。

binary ef128 fresh S1 已通过 9/9 Recall、两类 plan、性能与 cleanup；首次 fresh S2 在 seed 前检测到宿主 `iowait=51%`、阻塞任务 `b=16-17`、swap 约 `7.9GiB`，已主动中止且 trap 清零资源。后续有效 S2 已完成并形成 binary128 的失败关闭结论，当前不再重跑该配置。

最终辅助预算已收敛并由 canonical 接受为 binary `ef_construction=64` + `3N`，主 cosine 保持 `512/N`。fresh S0/S1/S2 同一次执行全部通过；S2 load/index `2062.742s`，9/9 Recall=`1.00`，Dense/lexical/Hybrid p95 `32.237/41.663/54.373ms`，并发 p95 `246.531ms`、吞吐 `61.069 req/s`，数据库 `7.159 GiB`，零错误、零 drift、零 cleanup 残留。正式证据在 `docs/evals/artifacts/m403a-v2/`。

M403B 是独立批准并完成的生产启用阶段：数据库目录、API registry、Worker Image adapter、caption 配置与 Web PNG/JPEG/WebP 入口已同步；真实上传、失败重试、删除、浏览器和恢复证据归档于 `docs/evals/artifacts/m403b-*`。M404 仍是独立真实用户价值门，未完成时产品继续标记内部预览。

## 质量门禁

- 每一阶段同步测试、SSoT、API fixture、迁移证据和运行手册。
- 任何历史 Citation/NoteSource 语义差异都阻塞切换。
- 不允许通过字段 fallback、文件名、列表顺序或名称当 ID 推断资产/locator。
- 不允许把 Viewer runtime 状态写入持久化 locator。
- 新模态允许新增模块和类型化表，但不得修改稳定核心表、已有 locator 含义或共享 Chat/Viewer shell。
