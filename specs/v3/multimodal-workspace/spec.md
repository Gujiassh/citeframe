# V3 多模态工作区规格

## 状态

- 范围已确认：多模态 PDF + 独立图片
- 产品/交互设计：已形成目标稿
- 数据/API 实施：合同已批准，Phase 1-3 已完成并通过最终 Critical 复审；Phase 4 M401-M403B 已完成，21-case 工程/全栈 Evidence、7-case 真实模型和 Image 生产工程门禁全部通过
- 用户验证：延期到 Beta 验收，不阻塞内部实现

## 用户目标

用户可以在同一个 Workspace 中上传 PDF 和图片，通过 Chat 检索、比较和分析两类资产，并从答案直接回到 PDF 页/区域或图片区域核验证据，再将带定位快照的结论保存为笔记。

## 功能需求

- FR-001：PDF 和图片必须是正式可上传、处理、检索、引用和删除的 Asset，不能只做预览附件。
- FR-002：Chat 保持默认主画布，Evidence Viewer 按资产或 citation 打开。
- FR-003：用户可以使用全部 ready 资产或显式资产集合提问；服务端必须解析并保存本次消息实际使用的 Asset 范围快照。
- FR-004：PDF 支持整页和区域 locator；图片支持区域 locator。
- FR-005：Citation 和 NoteSource 必须冻结 asset、locator、标题、excerpt 和处理版本快照。
- FR-006：PDF Viewer 保留页码/缩放/目录/文本层/OCR 层，并增加 region overlay。
- FR-007：Image Viewer 支持适应窗口、100%、缩放、平移和 region overlay。
- FR-008：页面、图片和 region locator 使用 discriminated union，不能通过 MIME、字段缺失或第一个可用值猜类型。
- FR-009：文本、OCR、caption 和视觉候选按独立检索通道融合，不默认共用向量空间。
- FR-010：源删除、重处理、重索引和历史回放不能改写已保存 Evidence 的含义。
- FR-011：所有 Workspace、Asset、ContentUnit、Citation 和 NoteSource 操作保持 Workspace 隔离。
- FR-012：V3 生产 registry 已启用 PDF 与 PNG/JPEG/WebP Image；M403B 已在恢复语义、容量验收、独立 Critical 复审和独立批准完成后同步启用数据库目录、API registry、Worker adapter 与 Web 上传入口。Audio/Video 不提供入口、adapter、renderer 或数据库启用记录，Omnilabel 业务模型不进入稳定内核。
- FR-013：Asset、Representation、ContentUnit、Embedding、retrieval scope、Citation、NoteSource 与 Evidence Viewer shell 必须保持模态无关。
- FR-014：新增模态通过封闭后端/前端注册模块、类型目录、类型化 locator 表和 contract fixture 接入，不能修改已有 locator 含义或核心快照表。
- FR-015：图片源对象与 `source_sha256` 不可变；方向归一化必须生成独立、不可变、按 processing generation 寻址的 `image_oriented` 表示，所有图片 locator 只解释该规范显示空间。
- FR-016：图片框选在提交前只属于 Web runtime 草稿；提交时使用可扩展的 `evidenceTargets` 联合类型，不能编码成选择文本或复用现有 Citation 伪造来源。
- FR-017：图片区域目标只由客户端提交 Asset、当前 processing generation 和规范化区域；服务端必须重新校验 Workspace、Asset、generation、canonical geometry，并解析同代允许的 OCR/caption Evidence Representation，客户端不得指定 Representation、excerpt 或显示 geometry。
- FR-018：Chat 必须持久化用户消息的输入 Evidence 快照，并将同代 canonical oriented 图片的框选内容作为视觉输入；`image_oriented` 只承担显示/模型输入，不能成为 Citation 或 NoteSource 的 Evidence Representation。
- FR-019：直接从图片框选创建笔记时必须生成真实、不可变、无伪造 Citation 的 NoteSource；`messageCitationId` 保持为空，来源冻结服务端解析的 Evidence locator、excerpt 与版本快照。
- FR-020：现有 `selectionText`、`assetScope`、`sourceCitationIds`、历史 Message/Citation/NoteSource payload 和保存语义保持不变；`evidenceTargets` 后续可以增加 `pdf_region`、`audio_range`、`video_range`，不得再次改写核心请求结构。
- FR-021：检索候选必须是模态无关的 Evidence 候选；共享 retrieval/Chat 不得依赖 PDF page/detail 字段解释 Image 候选。
- FR-022：检索范围与 current index/generation/Representation/locator 一致性必须在 Dense/lexical SQL 召回前生效，不能先召回范围外或旧代候选再过滤。
- FR-023：生产模态注册表声明每个模态参与的 retrieval channel；M305 的 text channel 覆盖 PDF 文本/OCR/表格/图表文本与 Image OCR/caption，不启用 visual embedding。

## 非功能需求

- NFR-001：桌面、平板和手机均能完成问答与证据核验主链，无横向溢出或控件重叠。
- NFR-002：Viewer 显示资源可以延迟加载，但业务选择、locator 和消息状态必须立即切换。
- NFR-003：普通文字与交互状态满足 WCAG AA 对比度，键盘和触控操作完整。
- NFR-004：上传、解析、检索、Chat 和 Viewer 关键路径有有界指标与 grep-friendly 日志。
- NFR-005：迁移和恢复能逐项验证当前 PDF 历史语义及新增图片语义。
- NFR-006：使用仅存在于测试环境的模态模块验证扩展协议；测试模块不得出现在生产上传类型或持久化启用目录。
- NFR-007：内部黄金集必须区分 retrieval、evidence 和 answer 三层，冻结 fixture/hash/scope/typed locator；合成工程 case 不得替代真实内容质量或用户价值证据。
- NFR-008：销卷恢复必须在独立 Compose project 中删除容器与数据卷后恢复到空 PostgreSQL、Redis 和 MinIO；恢复前后数据库语义快照与全部对象 SHA-256 必须严格全等。
- NFR-009：容量验收分 S0 10k/14k、S1 100k/140k、S2 500k/700k（Dense 业务可见/含干扰物理 ContentUnit）三档；只有完整 S0+S1+S2 可形成发布报告，子集执行必须标记 `debugOnly`。S2 为发布门禁，PDF/Image 比例 80/20，覆盖生产 text channel 全部 8 个类型签名；额外 40% 行严格均分为范围外 Workspace、旧 generation、旧 index 和仅有错误 provider/model/version embedding 的 current-chain ContentUnit。由于 production lexical 不读取 embedding metadata，报告必须分别记录 `denseEligible` 与 `lexicalCurrentChain`，不能伪称二者集合相同。每档覆盖每 locator 1/8/64 条重复候选，并使用 80% 500 字符、20% 1200 字符的确定性文本分布。
- NFR-010：M403A 必须保留 production Dense/Latin lexical 在 all-ready 与 selected scope 下的 `EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON)`；S1/S2 Dense 的显式 ANN candidate stage 使用 HNSW，Latin lexical 使用 FTS GIN。D1/D8/D64 必须按最终去重 Evidence location 对 exact 全范围基线计算 Recall@10，最小值不低于 0.95；D8 唯一位置补足不超过 4 轮且累计 ranked rows 不超过 150，D64 只记录实测成本、不套用 D8 阈值。固定项目总 4 vCPU/8 GiB（PostgreSQL 3C/6 GiB + runner 1C/2 GiB）必须由 Docker inspect/cgroup 实值证明。S2 warm Dense p95 不超过 100 ms、lexical p95 不超过 150 ms、Hybrid p95 不超过 250 ms，8 并发 Hybrid p95 不超过 400 ms且吞吐不低于 20 req/s；错误/位置漂移为零、warm Dense/Latin lexical shared-buffer hit ratio 均不低于 0.90、数据库不超过 12 GiB、加载加索引构建不超过 45 分钟、清理不超过 5 分钟。容量报告必须冻结存储价格来源、时点、区域、币种、主副本/备份因子和公式。

## 成功标准

- SC-001：一个 Workspace 中的 PDF 和图片都能从上传进入 ready，并被同一 Chat 查询命中。
- SC-002：资产范围过滤在检索前生效，回答不引用范围外资产。
- SC-003：合成 PDF 的旋转/CropBox 区域和测试图片区域在不同缩放下正确高亮。
- SC-004：历史页码 citation、region citation 和 NoteSource 在刷新、重索引、删除、备份恢复后保持语义。
- SC-005：端到端回归覆盖上传、Chat、citation、Note、删除和恢复。
- SC-006：Beta 前完成真实用户任务验证；延期不等于通过。
- SC-007：测试模态可以在不修改 Workspace/Chat/Citation/NoteSource/Evidence Viewer shell 和稳定核心表的前提下完成注册、候选序列化与 renderer 调度测试。
- SC-008：图片区域 Chat 请求在跨 Workspace、跨 Asset、generation 漂移、无效 geometry、无同代 Evidence Representation 时全部 fail closed；成功时刷新后仍能恢复输入 Evidence 快照。
- SC-009：图片框选直接笔记在没有 MessageCitation 的情况下保存一个可打开的真实 NoteSource，重处理后仍保持原 generation、区域、excerpt 和 Representation 语义。
- SC-010：混合 fixture 的一个 `all_ready` 问题同时产生 PDF 与 Image Citation，显式 PDF-only/Image-only scope 分别只产生所选资产 Citation，Message scope 快照顺序与请求一致。
- SC-011：旧 generation、旧 index、跨 Workspace/Asset/Representation 损坏链和未注册 channel 类型都不能进入候选；混合结果重复执行顺序稳定。
- SC-012：M403 的 PDF/Image 历史 Evidence、MessageInputEvidence、Citation、citation-backed/direct NoteSource、对象内容和类型化 locator 在销卷恢复后逐项全等，且全部服务恢复健康。
- SC-013：M403A 在冻结语料和阈值下通过计划、范围、唯一位置补足、延迟、并发、容量和成本判定；如果 PostgreSQL 仍选择 exact sort 或任一阈值失败，必须报告未通过，不能宣称规模就绪。
- SC-014：M404 只有在至少 5 名真实目标用户完成 20 个真实任务和 5 份复杂资产后才可评估；合成用户、开发者自测或模型代理不能计入，缺少数据时状态必须为 `not_evaluable`，产品保持内部预览。

## 非目标

- Audio/Video/Omnilabel
- 运行时任意文件类型预览、动态插件市场与万能 Asset adapter
- 未经质量证据引入视觉向量、reranker、GraphRAG 或独立向量数据库
- 用 UI 兼容层长期维持 Document 与 Asset 两套业务模型
