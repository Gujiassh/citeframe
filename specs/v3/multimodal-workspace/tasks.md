# V3 多模态工作区任务

> 当前说明：V3 已完成 PDF/Image 工程主链，是 V5 多模态扩展的基础。R803/M404 属于后置质量/用户验证，不阻塞 V5 功能开发；本文件保留 V3 当时的范围和验收历史。

## Phase 0：设计与审批

- [x] M001 确认首个范围为多模态 PDF + 独立图片
- [x] M002 重做资产栏、Chat 范围和 Evidence Viewer 信息架构
- [x] M003 建立 Asset/Representation/ContentUnit/Embedding 目标边界
- [x] M004 建立 PDF/Image locator 与迁移目标设计
- [x] M004A 建立字段级数据、API、SSE 和旧数据映射 Contract Draft
- [x] M004B 建立后续全模态文件的封闭注册与类型化扩展协议
- [x] M005 批准目标数据结构、坐标、类型表、API 版本和历史语义

## Phase 1：Asset 基础

- [x] M101 编写 Alembic migration、回填和 downgrade 限制测试
- [x] M102 实现 Asset/Representation/ContentUnit/Embedding 模型与 schema
- [x] M103 迁移现有 PDF/page/chunk/tag/citation/note source
- [x] M104 实现 Asset API 与上传、重试、删除 job
- [x] M105 将 Web Document 类型和状态迁移为 Asset
- [x] M106 扩展备份恢复和历史 payload oracle
- [x] M107 实现 Chat `assetScope` 校验、解析与消息范围快照
- [x] M108 实现后端/前端模态注册表与测试模态 contract test

Phase 1 验收证据：Alembic head `c9d1e2f3a4b5`；API 103、Worker 18、Web 57 通过；legacy -> Asset/Evidence 迁移和不可逆 downgrade 门禁通过；custom `pg_dump` -> 空库 `pg_restore` 后 Asset/Evidence/Citation/NoteSource payload 全等；生产代码 `/documents`、`documentId`、Document 业务类型扫描为零；浏览器捕获显式选择后的 `assetScope.selected` 请求体。Critical 复审已关闭三项 High：Image 保持注册但 disabled，畸形 SSE terminal 和未知 locator version 均 fail-closed。

## Phase 2：多模态 PDF

- [x] M201 产出页面几何、layout、OCR bbox 和区域 ContentUnit
- [x] M202 产出表格、图表和页内图片区域
- [x] M203 实现 `pdf_page/pdf_region` Citation 与 NoteSource
- [x] M204 实现 PDF region overlay、定位与框选交互
- [x] M205 完成旋转/CropBox/扫描/表格/图表 fixture 验收

Phase 2 验收证据：12 页非对称 CropBox matrix 覆盖 table/raster/vector × `0/90/180/270`，实际彩色像素与 source region 最大误差 `0.001852`；表格使用隔离未旋转页检测，artifact token 序列严格 fail closed，raster/vector 按原始 overlap graph 连通分量合并，caption 与续注要求显式语义，artifact offsets 持久化为 `NULL/NULL`。真实上传摄取得到 12 text、4 table、8 figure ContentUnit；正式 retrieve -> SSE -> finalize -> citation clone 与 Viewer locator/canvas/像素、翻页清草稿链路通过。失败 generation 会清理专属 citation locator，并以可继续的失败分支和明确 Web 告警态回放。最终 API 114、Worker 36、Web 62、lint、tsc、Next build、compileall、Alembic current/check 与 readiness 全部通过；独立 Critical 复验 PASS，无剩余 finding。图片摄取继续 disabled，冻结的 Chat/NoteSource 保存合同未变。

## Phase 3：独立图片

- [x] M301 接入 PNG/JPEG/WebP 上传与方向归一化
- [x] M302 产出 OCR、caption、区域 ContentUnit 和 embedding
- [x] M303 实现 `image_region` Citation 与 NoteSource
- [x] M304 完成 Image Evidence Viewer 与图片区域提问/笔记闭环
  - [x] M304A 实现受保护 frozen/current 图片流、缩放、平移、overlay 和区域框选草稿
  - [x] M304B 实现已批准的图片区域 `evidenceTargets`、消息输入 Evidence、多模态 Chat 与直接 NoteSource 合同
    - [x] T304B-01 添加 `message_input_evidence` 持久化迁移、ORM 与 P0 数据合同测试
    - [x] T304B-02 实现服务端 Image evidence target 解析、校验、locator/excerpt 冻结和区域裁剪
    - [x] T304B-03 扩展 Chat 请求、消息 DTO 与多模态 GenerationProvider 输入，保留现有文本合同
    - [x] T304B-04 扩展 Note 创建请求，支持无 Citation 的服务端校验 Evidence target
    - [x] T304B-05 接通 Web 图片框选提问、直接笔记、消息输入 Evidence 恢复与 Viewer 跳转
    - [x] T304B-06 完成 API/Web/Playwright、迁移/恢复、生产禁用门禁和独立 Critical 复审
- [x] M305 完成 PDF/图片混合检索与显式 Asset 范围过滤
  - [x] T305-01 将共享检索候选收敛为模态无关的 `ContentUnit + Asset + EvidenceLocator + channel + score`
  - [x] T305-02 从生产模态注册表解析 text channel 的允许 Asset/ContentUnit 类型，不在 Chat 或共享查询中硬编码图片分支
  - [x] T305-03 在 Dense/lexical SQL 召回前应用 Workspace、显式 Asset scope、current index、current generation 与 Representation/locator 一致性约束
  - [x] T305-04 用 PDF text/region 与 Image OCR/caption 混合 fixture 验证有界 RRF、稳定去重、Citation locator/sourceVersions 和范围快照
  - [x] T305-05 完成 API/Worker/Web、迁移/恢复、生产禁用门禁和独立 Critical 复审

M305 语义 oracle：同一问题在 `all_ready` 下可以同时返回 PDF 与 Image Evidence；`selected` 只允许所列 ready Asset，范围外候选必须在 SQL 召回前排除。候选的 ContentUnit、Asset、Representation 与 EvidenceLocator 必须同 Workspace、同 Asset、属于 Asset 当前 processing generation 和 current index，且类型属于该模态注册的 text retrieval channel。Dense 与 lexical 各自在通道内稳定排序，再按 locator 语义执行有界 RRF；PDF 整页可按 Asset+页去重，PDF region 与 Image region 保持独立。Chat 继续只克隆候选 locator，Citation、Message scope 和历史保存 payload 不增加字段、不改变含义。

M305 最终证据：共享 `RetrievedContent` 已移除 PDF page/detail，统一为 `ContentUnit + Asset + EvidenceLocator + channel + distance + locationKey`；生产 ModalityRegistry 的 text channel 以 8 条精确四元签名覆盖当前 PDF/Image persister 产物，SQL 使用完整 conjunction，未放宽为类型集合笛卡尔积。Dense/lexical 在排序前约束 Workspace、显式 Asset scope、ready/deleted、current index/generation、Representation/locator/embedding 同链，并在 limit 前按 locator 语义补足唯一位置；4 个额外同页 PDF chunk 下，SQLite/PostgreSQL 仍稳定返回 `[pdf,image,image]`。Evidence typed detail/regions 改为批量 fail-closed 校验，单次真实 Hybrid 查询从 `63` 条 SQL 降到 `7`；缺失 typed detail、缺失 region 和非法 geometry 均有持久化拒绝测试。离线 LexicalCorpus 复用同一生产 scope，旧代、跨 Asset locator、错误签名和范围外 Asset 不能污染评测。正式 40-case 报告已重生成 `assetId` payload：Hybrid Recall `+0.0708`、citation hit `+0.0750`，端到端 p95 增加 `69.3 ms`、比例 `1.650x`，并发 `0` error/`0` drift，`eligibleForDefaultHybrid=true`。Chat Citation/sourceVersions、Message scope 与保存 schema 未变。最终 API `190/190`、Worker `79/79`、Web `82/82`、PostgreSQL oracle `1/1`、Playwright `1/1`、lint、tsc、Next build、compileall、迁移/恢复与 diff check 通过；独立 Critical 复审关闭全部 finding。生产 API/DB/Worker/Web 仍为 PDF-only。

M301 验收证据：上传注册表按 canonical MIME 精确区分 PNG/JPEG/WebP，PUT `Content-Type` 与 upload-session MIME 绑定；Worker 使用直接依赖 Pillow 两遍验证完整静态单帧、64 MP 上限、格式、容器终止与 EXIF `1..8`，输出剥离 EXIF 的 RGB/RGBA canonical PNG。WebP 额外严格验证 RIFF 长度、唯一 image bitstream/VP8X、静态 chunk 顺序、reserved bits/bytes、ICCP/EXIF/XMP/alpha flags 与实际 chunk/VP8L 能力一致性，合法 lossy/lossless RGB/RGBA 矩阵通过且篡改变异全部 fail closed。`image_oriented` Representation、方向后 geometry、generation-stable 对象键与 SHA-256 已持久化；通用 generated-object manifest 在上传、embedding 或 commit 失败时回收派生对象，Asset 删除覆盖原对象与全部派生对象。10 个冻结 fixture 覆盖 PNG、lossless WebP 与 JPEG EXIF 1-8，独立像素变换、对象/像素 hash 与尺寸 oracle 通过。API 135、Worker 73、compileall 与独立 Critical 复审通过。生产 `IMAGE_MODULE.enabled=false`、数据库 Image disabled、Worker 生产 registry 仅 PDF、Web 无图片入口；M302 已完成，仍需 M303-M305 后才开放。

M302 验收证据：RapidOCR 像素原语保持模态中立，Image/PDF adapter 分别拥有图片解码与 PDF raster/mapping；1200×800 fixture 实际识别 8 个有界图片区域。独立 Image caption provider 按 OpenAI 官方 Responses API 使用 canonical PNG `input_text + input_image(data URL, detail)`，冻结 provider/model/version/detail/max tokens，空输出与 provider 失败 fail closed；当前环境无 OpenAI key，因此未把 mock caption 当作在线内容质量证据。`image_ocr/image_caption` Representation、`image_ocr_region/image_caption` ContentUnit 和 `image_region` locator 按同一 generation 持久化，locator/sourceVersions 冻结实际 OCR/caption Representation，图片 geometry 对照已落库 `image_oriented` geometry；图片 offset 为 `NULL/NULL`，权威来源是类型化 region。真实 job oracle 产出 2 OCR + 1 caption ContentUnit 与 3 个 text embedding 并进入 ready，caption-only 图片仍可检索；配置漂移、OCR 失败与 geometry mismatch 均在事务内回滚。模态自有 job config 由 `ModalityModule.ingestion_config_snapshot` 贡献，共享 router 不分支识别 Image，测试模态与共享字段冲突门禁通过。最终 API 140、Worker 79、Web 62、lint、tsc、Next build、compileall 与 diff check 通过。生产 Image 继续 disabled，M303-M305 前不开放。

M303 验收证据：共享 Evidence clone/serializer 现在校验 locator version、Workspace、Asset、processing generation、Evidence Representation kind 与 typed detail，Image 只允许 `image_ocr/image_caption`，明确拒绝 `image_oriented` 作为证据表示；clone 在 header、typed detail 和有序 regions 全部 flush 后才返回，可在同一事务内安全 chained clone。Chat Citation 与 Citation -> NoteSource 均复用该主链，没有图片特判；损坏快照、空/越界 region、非正 geometry、`orientationApplied=false` 和非正 PDF 页码全部 fail closed，Note 创建失败时整笔回滚。P0 oracle 在 generation 1 先创建并冻结 Image Citation/NoteSource，再切换到 generation 2，逐项确认两个独立 locator ID、完整 DTO、geometry、excerpt 与 sourceVersions 前后全等；当前批准的 `image-citation.json/image-note-source.json` 由测试直接加载。最终独立 Critical 复审 PASS；API 150、Worker 79、Web 63、lint、tsc、Next build、compileall、JSON 和 diff check 通过。生产 Image 继续 disabled，M304-M305 前不开放。

M304A 当前证据：新增两条权限保护的 `image_oriented` 文件流。Citation/NoteSource 使用 frozen `processingGeneration + image_ocr/image_caption representationId` 验证 Evidence 后解析同代显示对象，历史 generation 不受 Asset 当前代次影响；资产行预览重新读取 detail，并以该响应的 `currentProcessingGeneration` 请求当前显示对象，代次漂移 409 后可重新抓取 detail，不按旧列表 generation、UUID、列表顺序或原图猜显示对象。API detail 与文件流均拒绝非正 geometry 或 `orientationApplied=false`，Representation/geometry 查询显式约束同 Workspace 和 Asset；交叉 Asset/Workspace 损坏引用均 fail closed。Image renderer 独立实现适应窗口、100%、10%-400% 缩放、鼠标/单指平移、双指缩放、区域 overlay、鼠标与键盘框选草稿、错误重试；移动端工具目标为 44px，桌面保持紧凑，`Escape` 清除框选时不会同时关闭 Viewer。1200×800 fixture 的受保护流 SHA-256 与冻结 PNG 全等；400% 表面为 4800×3200，鼠标平移 `(1100,700) -> (1200,860)`，键盘平移再到 `(1240,900)`，鼠标框选约 `[0.2,0.3,0.5,0.5]`，键盘框选约 `[0.5,0.5,0.05,0.05]`，手机 CDP 双指缩放从 28% 到 69%。390×844 下页面宽度严格为 390，6 个工具按钮实测均为 44×44，无页面/请求错误；仓库 Playwright 额外强制 current generation 1 返回 409，确认重试只 refetch 一次 detail、按 generation 2 加载，并验证单指平移及 Escape 只清框选。临时 User/Workspace/Asset/Citation/MinIO 对象清理后计数全部为 0。最终 API 154、Worker 79、Web 75、定向 Playwright 1、lint、tsc、Next build、compileall、Alembic current/check、JSON 和 diff check 通过；`test_asset_router.py` 已从 2114 行拆到 1950 行，最终独立 Critical 复审 PASS，无剩余 finding。M304 整体仍 blocked：当前框选只是 Web runtime 草稿，尚未批准如何进入 Chat 请求或成为 NoteSource，不能宣称提问/笔记用户链完成，也不能进入 M305 完成态。生产 Image 继续 disabled。

M304B 最终证据：`image_region` target 只接受 Asset、当前 generation、固定 coordinate space 与最多 8 个规范化区域，严格拒绝 Representation、excerpt、geometry 和额外字段。共享 Chat/Note 只调用 resolver 注册表，Image 模块独占 Workspace/Asset/generation、canonical geometry/SHA、OCR/caption 选择和 PNG 裁剪；全部区域命中 OCR 才冻结 OCR，否则冻结唯一 caption，`image_oriented` 只提供显示/模型像素。Chat 在 user message 上持久化独立 locator 与 `message_input_evidence`，刷新返回 `inputEvidence`；纯区域提问允许普通检索为空，失败 generation 保留用户输入 Evidence，并允许下一次真实 HTTP 请求从 failed assistant 继续。直接笔记生成 `messageCitationId=null` 的 NoteSource，Citation 来源在前、target 来源在后，任一 target 失败整笔回滚；即使 Note 不需要模型 crop，服务端也必须下载并校验 canonical PNG 的对象存在性、SHA-256、PNG 格式与自然尺寸。Web 仅从 current Viewer 构造 canonical target，服务端接受后才关闭 Viewer；422 或持久化失败保留框选。HTTP 接受后立即显示不可点击的输入 Evidence 锁定状态；SSE 中断且恢复 GET 同时失败时保留已持久化 user message 与锁定状态，只将 assistant 收敛为 failed。独立 Playwright 在真实 Workspace/Image 组件上验证 Chat 422、成功 SSE/hydrate、请求体白名单、自动 `assetScope.selected`、`inputEvidence` 恢复、`messageCitationId=null` NoteSource 以及两次 frozen generation/Representation Viewer 跳转。最终 API `178/178`、Worker `79/79`、Web `82/82`、Playwright `1/1`、lint、tsc、Next production build、compileall、Alembic head/current/check、PostgreSQL legacy -> head -> dump/restore、JSON 和 diff check 均通过。收口部署审查真实复现旧 API 镜像因缺少 `PIL` 无法导入应用；根因是 `pyproject.toml`/`uv.lock` 已加入 Pillow，但 `requirements.deploy.txt` 未重新导出。刷新锁定部署清单并增加直接运行时依赖一致性测试后，镜像 `sha256:0bcb53c0a4d9` 以 UID `10001` 导入 Pillow `12.3.0` 和 `ai_pdf_api.main` 成功，实际启动的 `/health/live` 返回 200。独立 Critical 初审先后发现 accepted request 双故障恢复隐藏 user/input Evidence、直接 Note 未读取 canonical 对象、failed assistant 被 router 拒绝三项问题；修正后，Web 接受/拒绝分支、缺失/损坏对象整笔零残留、真实 HTTP 失败后续问与 streaming parent 反向拒绝 oracle 全部通过，最终复审 `PASS`，无剩余 finding。生产 API/数据库/Worker/Web 仍只启用 PDF 摄取，待 M305 完成后再决定开放 Image。

## Phase 4：验收

- [x] M401 建立分层内部黄金集和失败样本
  - [x] T401-01 冻结 40 条真实 PDF 检索 reference baseline 的哈希与 case 数
  - [x] T401-02 建立 21 条 PDF/Image/mixed `retrieval/evidence/answer` 分层工程 case
  - [x] T401-03 建立 10 类失败 taxonomy，并只收录有持久化复现测试的失败样本
  - [x] T401-04 实现严格 schema、fixture/manifest/hash/scope/locator/coverage 校验和确定性报告
- [x] M402 完成 API/Worker/Web/Playwright、像素定位与真实模型 answer/refusal 验证
  - [x] T402-01 直接消费 21 个 golden case，通过真实 PDF/Image adapter、生产检索与 Chat 编排执行工程链
  - [x] T402-02 通过无 `page.route` 的真实 BFF 在桌面/移动端执行 7 个 Evidence case、8 个 citation 目标和像素/overlay/layout 验证
  - [x] T402-03 生成逐 case 报告、16 张截图和 21 个带 SHA-256 的证据记录（含冻结 answer oracle 与 real-model raw）
  - [x] T402-04 使用真实配置模型执行 5 个 answer 和 2 个 refusal 快照，由报告端绑定 production prompt/provider/model，并以冻结完整输出 allowlist 做 fail-closed 验收
- [x] M403 完成加强后隔离 Compose 销卷备份恢复、对象哈希与 PDF/Image 历史语义严格全等
  - [x] T403-01 冻结 PDF/Image 当前/历史 generation、失败/删除状态、typed locator、Chat scope/input Evidence/Citation/两类 NoteSource 语义快照
  - [x] T403-02 真实备份 PostgreSQL + MinIO，删除隔离 project 容器与卷，恢复到空部署
  - [x] T403-03 以完整 raster SHA-256、规范化 overlay geometry、citation/viewport/phase/result cardinality 和最终零残留清理门重跑确定性报告
- [x] M403A 用 S0/S1/S2（最高 500k 可见、700k 物理）分层 ContentUnit 语料验证 pgvector/HNSW 与 lexical 执行计划、buffer 命中、唯一位置补足成本和 p95；binary64/3N fresh canonical 三档全通过并设置 `releaseGatePassed=true`
  - [x] T403A-01 构造 PDF/Image 六层 current-chain 语料及 old generation/index、范围外和重复 locator 噪声
  - [x] T403A-02 为 `content_unit_embeddings` 增加 `asset_id / processing_generation / index_version / is_current`，完成回填、current-only partial HNSW、scope trigger 与模型/迁移门禁
  - [x] T403A-03 让摄取在同一事务维护 current 投影，验证成功切代、失败回滚、current-only Dense/SQLite parity 与 selected/all-ready scope
  - [x] T403A-04 保存 Dense HNSW、lexical FTS GIN 的 cold/hot JSON plans 和 buffer 指标，验证 ANN 内过滤与 partial index（fresh S1）
  - [x] T403A-05 验证唯一位置补足、20 次热查询与 8 并发 32 次稳定性（fresh S1）
  - [x] T403A-06 记录 p50/p95/p99、吞吐、索引/数据库尺寸、建库耗时、存储成本并按冻结阈值判定；fresh canonical 三档全门通过
  - [x] T403A-07 实现批准的 cosine + binary HNSW 候选 union、identity 去重与原始 cosine 精排，验证两类索引计划、S1/S2 Recall、容量和迁移维护窗口
- [x] M403B 已独立批准并完成生产 Image 数据库/API/Worker/Web 合同与发布验收
  - [x] T403B-01 冻结启用 oracle：仅开放 PNG/JPEG/WebP，不改变 Citation、NoteSource、Chat、持久化字段或保存语义
  - [x] T403B-02 同步数据库目录、API registry、Worker Image adapter、caption 配置与 Web 上传入口；API 285、Worker 96、Web 85、Alembic current/check、compileall、lint/build 通过
  - [x] T403B-03 验证真实上传、摄取、检索、Evidence、失败重试、删除与移动端用户路径
    - [x] T403B-03a deterministic local-provider run：真实 API upload `201/204/200`、Worker ready、6 条 scoped retrieval、Evidence Chat `inputEvidence=1`/Citation=6、source/oriented cleanup zero
    - [x] T403B-03b immutable-source failure/retry、MIME mismatch、ready delete、PNG/JPEG/WebP 长期 Worker 上传和 390x844 no-overflow browser evidence
  - [x] T403B-04 重跑 PostgreSQL/MinIO 备份恢复并证明 PDF/Image 历史 Evidence 语义不变
  - [x] T403B-05 完成全量门禁、Critical 复审和发布记录
- [ ] M404 完成至少 5 名目标用户、20 个任务和 5 份复杂资产的 Beta 验证

以下 M401-M403A 证据段按时间保留历史实验、失败关闭和最终验收过程；它们中的旧测试计数、旧 migration head 或“生产 Image disabled”只描述当时运行，不覆盖本文件顶部的当前任务状态和已完成的 M403B 结论。

M403A current-chain 的历史 cosine-only canonical：current-only partial HNSW、scope trigger、两阶段 embedding 激活、latest/delete CAS 和 selected exact-vs-ANN oracle 已落地。`ef_construction=256` 完整 canonical 的 S2 最低 Recall 为 `0.90`；提高到 `512` 后，fresh S1 的 9 个 all-ready/selected case 全部 `1.00`，但该阶段完整 canonical 的 S2 `image-ocr:D1` 仍为 `0.90`。该次 S0/S1 全通过；S2 其余 Recall、HNSW/GIN、scope、D8、Dense/lexical/Hybrid p95 `16.0/20.4/36.0ms`、8 并发 p95 `261.8ms`、`63.09 req/s`、数据库 `7.07 GiB`、HNSW `1.67 GiB`、成本、资源和 cleanup 全通过。历史失败证据保存在 `docs/evals/artifacts/m403a-efconstruction512-failed/report.json`；最终完成结论以后文 binary64/3N canonical 为准。

M403A `m=24` 中间连接度 diagnostic：S1 的 9 个 all-ready/selected Recall 均为 `1.00`，但 warm all-ready/selected Dense 都未选择 HNSW，Dense p95 `116.3ms`，8 并发 p95 `5188.0ms`、吞吐 `6.15 req/s`。该候选违反计划与性能门，未进入 S2，生产模型、migration、capacity seed 与测试已撤回到默认 `m` + `ef_construction=512`。

M403A filtered HNSW `relaxed_order` diagnostic：在默认 `m` + `ef_construction=512` 下，S1 全部门通过，S2 HNSW/GIN、性能、并发、容量、scope、资源和 cleanup 也通过，但 `image-ocr:D1` Recall 仍为 `0.90`。外层 materialized candidate CTE 已按 distance 重排，仍不能恢复缺失位置；该方向不进入生产，deploy/M403A Compose 恢复 `strict_order`。

M403A HNSW 连接度二分 diagnostic：`m=20` 与 `m=18` 的 S1 9 个 Recall 均为 `1.00`，普通 Dense plan 保留 current-only HNSW，但 selected scope 都选择 `ix_content_unit_embeddings_asset_id` + exact sort，`hnswPlan=false`。两者均在 S1 失败关闭并撤回，未运行 S2；当前恢复默认 `m=16` + `ef_construction=512`。

M403A 串行建图 diagnostic：`max_parallel_maintenance_workers=0` 的 S1 全部门通过，HNSW build `116.4s`、总 load/index `186.3s`。S2 在 HNSW 仅完成 `85%` 时 build 已约 21 分钟，结合约 7 分钟 load 和最近 137 blocks/分钟，未计 vacuum/checkpoint 即确定会超过 45 分钟冻结门限；控制器主动中止，trap 后容器/卷/网络均为零，串行 build 改动已撤回。

M403A 双索引架构批准：新增 current-only binary-quantized HNSW 作为与 cosine HNSW 误差独立的辅助候选源；两路 candidate 先按 embedding identity 去重，再按原始 cosine 精排并进入现有业务 scope。禁止增加持久化字段或改变 API/保存语义；实现必须同时新增 binary plan gate、索引/数据库尺寸和 load/index 成本门，S1/S2 diagnostic 通过后才能重跑 canonical。

M403A 双索引首轮诊断：fresh S1 的 9/9 Recall 均为 `1.00`，all-ready D1/D8 与 selected D1 warm plan 同时命中 cosine/binary HNSW，性能、容量和 cleanup 全通过。fresh S2 也将原失败项 `image-ocr:D1` 提升到 `1.00`，9/9 Recall、两类 plan、全部查询/性能/并发/数据库/cleanup 门通过；但 load/index `3216.427s` 超过 `2700s`，所以 S2 scale 与 M403A 继续失败关闭。完整过程、阶段耗时、宿主 I/O 证据和重试状态见 `docs/evals/m403a-optimization-log.md`。

M403A 双索引 unchanged S2 重试：9/9 Recall 与两类 plan 继续通过，但 load/index `2817.828s`、并发 p95 `417.263ms` 仍未过冻结门；零错误、零 drift、`49.96 req/s`、容量和 cleanup 通过。当前不再重复 unchanged 运行，改为只将辅助 binary HNSW 的 `ef_construction` 从 `512` 降至 `128`，主 cosine 保持 `512`，然后按 focused tests -> fresh S1 -> fresh S2 顺序验证。

M403A binary `ef_construction=128` fresh S1：`29` 条 focused test、Alembic drift、compileall 与 diff check 通过；S1 9/9 Recall=`1.00`，all-ready D1/D8 和 selected D1 同时命中 cosine/binary HNSW，Dense/lexical/Hybrid p95 `21.9/13.1/30.7ms`，并发 p95 `115.6ms`、吞吐 `84.96 req/s`，binary build `13.604s`，数据库 `1.44 GiB`，cleanup 零残留。S1 scale 已通过，下一步 fresh S2。

M403A binary128 阶段 migration 往返：本地开发库完成 `f2a4 -> e1f3 -> f2a4`，当时 actual current-only cosine/binary HNSW 的 `ef_construction` 为 `512/128`，360/360 embedding current、0 invalid，2 个 statement-level scope trigger 存在，`alembic current/check` 为 head/no drift。最终 binary64 候选落地后再次通过 `pg_indexes / pg_index` 枚举核验为 `512/64`，两索引均 valid/ready，current/invalid/trigger 计数不变。

M403A binary128 clean S2：9/9 Recall、双 HNSW/GIN plan、scope、串行 p95、吞吐、数据库和 cleanup 通过；load/index `2721.264s` 超门 `21.264s`，并发 p95 `424.622ms` 超门 `24.622ms`，因此继续失败关闭。最终辅助预算候选改为 binary `ef_construction=64` + `3N`，主 cosine `512/N` 和最终 cosine 精排不变；需重新通过 focused -> S1 -> S2。

M403A binary64/3N fresh S1：focused `29 passed`，Alembic/compile/diff 通过；9/9 Recall=`1.00`，双 HNSW plan、scope、性能与 cleanup 全通过，Dense/Hybrid p95 `24.7/40.9ms`，并发 p95 `159.1ms`、吞吐 `61.31 req/s`，binary build `9.520s`。进入 fresh S2。

M403A binary64/3N 首次 S2：共享盘 load 再次异常，embedding insert 超过 25 分钟且尚未开始 cosine HNSW；按历史最佳剩余阶段已确定总时间不可能低于 2700s，因此主动中止。trap 后容器/卷/网络均为零，无 seed/report，不计为质量失败。

M403A binary64/3N 最终 S2：60 秒连续预检 `avg/max wa=5.1/9%`、`avg/max b=1.033/2` 后启动，S2 scale 全门通过。9/9 all-ready/selected Recall=`1.00`，cosine/binary HNSW 与 GIN plan 全通过，Dense/lexical/Hybrid p95 `32.745/23.391/55.745ms`，8 并发 p95 `291.122ms`、吞吐 `56.405 req/s`，load/index `2255.299s`，数据库 `7.159 GiB`，零错误、零 drift、零 cleanup 残留。S2-only 顶层按规则保持 `debugOnly=true / releaseGatePassed=false`，现只解锁一次 fresh S0/S1/S2 canonical。

M403A binary64/3N 正式 canonical：独立 60 秒 preflight 为 `avg/max wa=0.250/3%`、`avg/max b=0.033/1`；同一次 fresh S0/S1/S2 全部 seed/query/resource/cleanup gate 通过，正式报告 `debugOnly=false / releaseGatePassed=true`。S2 9/9 Recall=`1.00`，双 HNSW/GIN plan 全通过，Dense/lexical/Hybrid p95 `32.237/41.663/54.373ms`，8 并发 p95 `246.531ms`、吞吐 `61.069 req/s`，load/index `2062.742s`，数据库 `7.159 GiB`，零错误、零 drift、零残留。正式报告和 74 个带校验和文件归档于 `docs/evals/artifacts/m403a-v2/`；生产 Image 仍 disabled，M403B 不随 M403A 自动启用。

M404 延期不阻塞 M101-M403，但未完成时产品只能标记内部预览，不能宣称用户价值已验证。

M401 验收证据：`multimodal-golden-v1.json` 绑定 3 个确定性 PDF/Image source fixture、对应 source+manifest hash 和现有 40-case 真实 PDF retrieval baseline；21 个工程 case 按 retrieval/evidence/answer 各 7 个，覆盖 11 PDF、6 Image、4 mixed、全部 7 类任务和 2 个明确拒答案例。`multimodal-failures-v1.json` 冻结 10 类 taxonomy，首批 6 个样本全部指向可执行的持久化回归测试。校验器对未知字段、重复 ID、路径逃逸、文件/hash 漂移、manifest schema/coordinate/geometry、locator/manifest 不一致、selected scope 越界、层级语义和薄覆盖 fail closed；40-case baseline 复用生产评测的严格 label loader，failure reproduction 只保存规范 API/Worker pytest 路径和模块顶层 AST test name，并由代码生成 argv，自由命令、`..` 路径和类内/嵌套符号被拒绝。确定性报告 `coveragePassed=true`，定向校验 `18/18`；最终 API `208/208`、Worker `79/79`、Web `82/82` 与静态门禁通过，独立 Standard 复审 `PASS`。这只证明质量合同与回归资产成立，不等于 M402 实际全栈结果、模型回答质量或 M404 用户价值通过。生产 Image 继续 disabled。

M402 执行语义：golden region 是人工相关表面，不要求与生产 artifact/OCR locator bbox 全等；实际 locator 的渲染 overlay 必须与目标区域相交并覆盖关键内容。原生 PDF 文本页在没有 region ContentUnit 时使用 `pdf_page`，不能为通过评测伪造 `pdf_region`。Scripted provider 只能证明编排，真实模型 answer/refusal 快照单独记录。

M402 最终证据：单一 Worker node 直接加载全部 21 个 case，真实执行 19 个 Evidence target 的 PDF/Image adapter 与生产 locator、7 个 retrieval case 的 Dense/lexical/RRF/scope，以及 7 个 answer/refusal case 的 Chat 编排；mixed query 的测试 embedding 显式映射 PDF chart 与 image observation 两个语义维度，连续 3 次随机 UUID 重建均通过。真实 BFF 临时 Workspace 含 2 PDF + 1 Image、14 条消息和 8 个 Citation；Playwright 未使用 `page.route`，在 1440x1000 与 390x844 下分别完成 7 case/8 target，验证指定页、canvas/image 非空像素、overlay 与 golden region 相交、mixed 双模态导航和布局边界，生成 16 张截图。正式定位口径为渲染区域对人工批准区域的覆盖率，最小值 `0.294333`；旧 intersection/min-area `0.997906` 已废弃。经明确批准后，runner 向当前 `openai / gpt-5.5` 配置发送且仅发送 7 条非机密合成 prompt；全部 provider 调用无错误，5 个 answer 与 2 个 refusal 的 citation target 均覆盖。初始严格 allowlist 只接受 1 条，另外 6 条正确完整改写经人工逐条对照 Evidence 后加入冻结 allowlist；raw output/messages 与 capture-time `passed=false` 诊断保持原样，正式报告不信任这些自报判分，只按当前 oracle 独立复算。`multimodal-execution-v1.json` 登记 16 张截图、4 个原始执行报告和冻结 answer oracle，共 21 个 SHA-256 资产；21 个 case 全部 `passed`，`realModelQualityPassed=true`、`releaseGatePassed=true`、`pending=[]`。最终 API `226/226`、Worker `84/84`、Web `82/82` 与静态、Alembic、报告重放门禁通过。生产 Image 继续 disabled，下一步进入 M403/M403A。

M403 初次诊断证据：`citeframe-m403-release` 隔离 Compose project 在冻结源代码镜像上创建 5 个 Asset、8 个 Representation、4 个 ContentUnit/Embedding、12 个 locator、4 个 Citation、1 个 MessageInputEvidence、3 个 Message scope、3 个 NoteSource 和失败 job；同时覆盖 PDF/Image 当前与历史 generation、当前/历史 index、selected/all-ready 顺序、失败分支、已删除 PDF/Image 及其对象应缺失语义。备份前 9 个活跃 MinIO 对象逐一对照 Asset/Representation SHA-256；真实 PostgreSQL custom dump 与 MinIO closed mirror 完成后，全部 project 容器、网络和 5 个数据卷被删除，再恢复到新空卷。恢复前后 26 类行/目录、对象清单、typed detail/regions 和历史语义 SHA-256 均为 `1ccf86f3113a9d5a7be232d92080928758eb961779b59d38f5869f04c2f7719a`，`mismatches=[]`；备份 `33.927s`、恢复与全服务健康 `114.617s`。该报告的旧 Viewer oracle 与最终 cleanup gate 经下段 Critical 重开，因此不能继续把其 `releaseGatePassed=true` 当成最终 M403 证明。M403 readiness-only provider stub 不执行 embedding，也不构成模型质量证据；生产 Image 仍 disabled。

M403 Critical 重开：初次报告的数据库、对象和销卷恢复数据保持为可信诊断证据，但旧 Viewer 比较只绑定非白/颜色计数与 overlay 数量，不能排除同统计量的 generation 漂移；最终 cleanup 也未进入自动 release gate。runner 与 Playwright oracle 已升级为完整 canvas/image pixel SHA-256、规范化 overlay geometry、citation ID、viewport、phase、结果基数和最终容器/卷/网络零残留，升级后正式重跑前不得继续引用旧 `releaseGatePassed=true` 作为发布证明。

M403 最终证据：加强后的 `citeframe-m403-release-v2` 从空隔离部署重新执行完整销卷备份恢复，正式 `m403-restore-report-v2` 得到 `releaseGatePassed=true`。恢复前后 9 个 MinIO 对象和 27 类表/目录计数及语义内容严格全等，语义 SHA-256 均为 `6b2a8758100229641271e7ced81c238a8ee69d7066c1b5076de8af002a8079c3`，`mismatches=[]`；桌面/移动端 PDF 与 Image 的完整 raster SHA-256、规范化 overlay geometry、citation/viewport/phase/result cardinality 全部通过，历史 Image 像素同时绑定 generation-1 冻结 SHA。最终 Compose down 及容器、卷、网络检查退出码均为 `0`，实际残留均为 `0`。独立 Critical 评审服务连续因外部 `503/429` 未返回结论；主控制器对正式 artifact、完整 oracle 与清理证据复核通过，该外部可用性问题不改写为代码 finding。生产 Image 仍 disabled。

M403A S1 diagnostic：首次 100k/140k 运行因 1 GiB `/dev/shm` 无法满足 2 GiB HNSW build memory 失败，修正为 3 GiB 后完成装载/建索引 `130.309s`（HNSW `70.056s`）、exact Recall 诊断 `1.0`、D8 4 轮/150 rows、GIN 计划、32 次 8 并发与零资源残留；但 warm Dense 对 100k 行执行 exact top-N sort，未选择 HNSW，约 `943-956ms`，所以报告正确保持 `releaseGatePassed=false`。该结果仅用于定位 cardinality/查询形状问题，不是 M403A 发布证据。

M403A ANN-first S0/S1 diagnostic：production Dense 现先在匹配 embedding metadata 的表执行有界 `MATERIALIZED` HNSW candidate stage，再套用不变的 Workspace/Asset/current-chain/type scope。首个 S1 ANN 运行暴露全随机 synthetic vector 没有签名语义簇，最低 location Recall@10 为 `0.80` 且目标签名独占失败；验收语料随后改为 8 个正交签名中心加 56 维确定性 locator 扰动，D1/D8/D64、100k/140k 规模和 40% 噪声不变。修正后的 S0/S1 分别在独立空卷运行，8 类查询 Recall@10 均为 `1.00`；S1 HNSW/GIN、all-ready/selected、current chain、20 次热查询、8 并发 32 次、D8、资源和 cleanup 全部通过，Dense/lexical/Hybrid p95 分别为 `10.2/51.4/61.1ms`。两次运行均为 `debugOnly`，正式发布证据仍必须来自单次完整 S0/S1/S2。

M403A 首次 canonical 与查询收敛：第一次单次 S0/S1/S2 运行正确保持 `releaseGatePassed=false`。S1 在 `ef_search=100` 下出现一次 `0.90` Recall，S2 最低 Recall 为 `0.60`；S2 Latin lexical p95 `226.6ms`，因此 Hybrid `254.4ms`、8 并发 p95 `893.4ms` 与 `11.67 req/s` 也失败。其余 scope/current chain、HNSW/GIN 选择、Dense p95、buffer、数据库 `6.92 GiB`、装载建索引 `1283.684s`、项目资源和 cleanup 均通过。生产 Latin FTS 随后改为 ContentUnit-only `MATERIALIZED` 候选前缀，完整业务 scope 在候选返回前校验且短缺时按源匹配总数扩窗；单词查询不再重复执行恒真的 `ILIKE` 覆盖扫描，首窗改为 `2 x limit`。生产与验收的 HNSW 查询深度统一为 `ef_search=400`。新 S1 diagnostic 的 8 类 Recall 再次全为 `1.00`，HNSW/GIN 与全部子门通过，Dense/lexical/Hybrid p95 `22.3/45.1/61.2ms`，8 并发 p95 `187.2ms`、吞吐 `57.0 req/s`；仍须新的完整 canonical 才能形成发布结论。

M403A cold restart 加固：第二次 canonical 在 S1 seed 后的 PostgreSQL restart 超时。日志证明后台 WAL checkpoint 尚未完成，Compose 默认 10 秒 stop 超时强杀数据库，随后启动进入 crash recovery，并非查询或数据门禁失败。seed 现显式执行 `CHECKPOINT` 并将耗时计入 `loadAndIndexSeconds`，部署 PostgreSQL 同时增加 5 分钟 graceful stop；正式运行不得把后台刷盘成本排除在容量时间之外，也不得依靠 crash recovery 形成所谓 cold baseline。

M403A seed I/O 加固：第三次 canonical 运行时，S2 的 700k embedding insert 单条查询已运行 `39m20s` 且仍在等待 `DataFileRead`，尚未进入 HNSW，已数学确定不可能满足 45 分钟总门限；运行被主动中止，trap 清理容器、卷和网络。原 seed 为每个唯一 locator 预先物化完整 1024 维临时 vector，再回读生成 700k 正式 embedding，产生约 1 GiB 无业务价值的临时 I/O。临时表现只保存 64 个有效 signal 分量，最终 insert 时再补 960 个零并 cast 为同一 `vector(1024)`。S0 真实回归的 dataset checksum、持久化指纹、8 类 Recall `1.00`、scope/current chain 和最终清理均不变；正式规模、物理 embedding 行数和最终向量维度未减少。

M403A startup wait 加固：第四次 canonical 在宿主短时 I/O pressure 较高时，初始 S0 PostgreSQL init 约 66 秒后正常 healthy，但 runner 的通用 60 秒 health 窗口已先行报错。M403A 初始启动与 cold restart 的 health/SQL 等待统一为 300 秒；等待窗口不进入 seed/query p95 或 load/index 时间，也不放宽任何发布阈值。正式容量报告必须在外部宿主压力回落后重新生成，不能把共享宿主争用误归因于 Citeframe 项目 4C/8G 容器预算。

M403A 第五次 canonical：单次 S0/S1/S2 已完整运行并通过每档 seed、资源和最终 cleanup；S0/S1 query gate 全通过。S2 HNSW/GIN、scope/current chain、D8/D64、无 temp blocks、buffer、容量、构建时间和串行 p95 均通过，但 `image-ocr:D1`/`pdf-text-legacy:D1` Recall@10 只有 `0.80/0.90`，8 并发 Hybrid p95 `1002.6ms`、吞吐 `11.62 req/s`，因此 query gate 与最终 `releaseGatePassed` 正确为 false。S2 Latin warm plan 实测 `Gather Merge` 启动 2 个 worker，而 PostgreSQL 总预算只有 3C；下一步在保留 `ts_rank_cd`、GIN、完整 scope 和全部冻结阈值的前提下，先做 per-gather parallelism A/B 与 ANN recall 参数矩阵，再决定最小生产修复。

M403A S2 保留库历史诊断：新 seed 与当时 canonical 的 dataset checksum、persisted fingerprint、700k physical rows 完全一致；最终项目容器、卷和网络为零。ANN `2x` overfetch、`ef_search=800/1200` 和 per-gather worker `0/1/2` 均被真实 A/B 否决并从生产候选移除。`ef_construction=96` 最低 Recall `0.90`，`128` 达到 8/8 Recall `1.00`，构建 `759.1s`、索引 `1803 MiB`。Dense-only 并发通过而 Lexical-only 明确失败；stored generated `search_vector` 保持排名/scope/RRF 语义不变，两次达到 8 并发 p95 `213.9/233.4ms` 与 `66.18/62.08 req/s`，迁移 `106.8s`、空间增加约 `148 MiB`。Owner 已批准并实现 `content_units.search_vector` generated stored column、GIN 索引切换、生产查询和容量 seed；该阶段验证已完成，最终 canonical 结果见 `docs/evals/artifacts/m403a-v2/`。
