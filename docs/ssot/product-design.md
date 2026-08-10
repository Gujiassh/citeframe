# Citeframe 产品设计

## 1. 产品定位

Citeframe 是一个自托管、可扩展的多模态 AI 知识库与证据工作台。它以 `Asset/Representation/ContentUnit/EvidenceLocator` 为统一底座，逐步接入文档、图像、音频、视频及其他经过批准的资料类型，支持多模型/provider 配置、跨模态检索、可追溯引用、Research 和受控多 Agent 协作。

`Citeframe` 是统一的产品、GitHub 仓库、本地目录和私有 npm scope 品牌。名称强调 citation 与 evidence framing，不绑定 PDF；内部 Python 包、`AI_PDF_*` 环境变量、数据库和对象存储 bucket 继续作为稳定运行标识，不随品牌迁移。

每个 Workspace 都拥有独立的资产、检索范围、模型/Prompt profile、聊天历史、Research Run、标签、笔记和研究产物。系统首先保证资料从接入到证据定位的完整链路，再让模型和 Agent 在受控边界内完成问答、研究与知识沉淀。

当前完成基线是 PDF、扫描 PDF OCR、PNG/JPEG/WebP Image、Hybrid/RRF 检索、Evidence Viewer、Citation/NoteSource、固定 Research workflow、HITL、恢复和 Evaluation Dashboard。多模型 generation/vision/ASR provider 与更多模态是 V5 主线；R803 模型质量评估和 M404 真实用户验证后置，不阻塞功能建设，产品在证据完成前仍标记 `internal_preview`。

## 2. 目标用户

### 2.1 第一目标用户

- 需要基于多份论文、技术规范、评测报告、方案文档或技术图片做技术判断的 AI/软件工程师
- 需要反复核验原文证据并积累研究结论的技术研究者

`学习项目` 和 `面试展示` 是当前仓库的工程验证价值，不是产品第一用户画像。合同、财务、法律、泛个人学习和标注团队不是当前第一阶段市场。

### 2.2 核心 JTBD

当用户需要基于多种资料形成判断、比较或可复用结论时，系统应帮助其统一接入资料、快速获得有证据支持的答案或研究产物，回到原始页面、区域或时间段核验，并把结论沉淀在 Workspace 中。

### 2.3 核心使用场景

- 为不同研究问题或技术项目创建 Workspace，例如 `RAG 评测`、`推理服务选型`、`模型安全调研`
- 接入 PDF、图片和后续启用的文档、音频、视频等资料，建立专属知识库
- 在 Workspace 内进行跨模态检索、问答、结构化抽取和 Research
- 通过引用回跳页面、区域、时间段或关键帧，保证答案可追溯
- 对多份资产进行比较、抽取、协作研究和结论复用，而不是只进行单文档闲聊

### 2.4 护城河假设

- 证据保真：检索结果、回答和笔记可以稳定回到原始页码，并在多模态 PDF 阶段演进到精确区域
- 质量飞轮：真实失败样本、分层黄金集和定位/支持率评测持续约束检索与回答质量
- 上下文积累：Workspace 内的问题、证据、笔记和用户确认结果形成可复用研究资产

Chat UI、支持格式数量或接入某个模型本身不构成产品护城河。

## 3. 产品原则

- Workspace 是顶层隔离边界，任何知识、聊天、标签、笔记都不能串库
- 引用必须可追溯，答案不能只给结论不指向原文
- 问答是默认主任务，Evidence Viewer/播放器/结构化查看器是按需展开的核验层
- 问答是交互入口，不是最终价值；最终价值是形成可核验、可复用的知识产物
- 多模态接入、模型能力和受控多 Agent 协作按真实用户任务逐步交付
- Agent 只能在 Evidence、权限、预算和工具 allowlist 边界内工作，不能直接决定系统事实
- 功能完整度优先；模型质量评估和真实用户验证作为后置发布证据，不阻塞能力建设

## 4. 核心对象模型

### 4.1 Workspace

一个 Workspace 表示一组独立的知识工作上下文，包含：

- 基础信息：名称、描述、封面、创建时间
- 独立 Prompt：系统提示词、回答风格、抽取模板
- 独立知识库：文档、chunk、embedding、索引状态
- 独立聊天：thread、message、citation
- 独立标签：用于文档、笔记、聊天筛选
- 独立笔记：自由笔记、引用笔记、页内笔记

### 4.2 Asset

一个 Asset 是上传到某个 Workspace 的资料对象，当前生产模态为 PDF 和 PNG/JPEG/WebP Image，后续按 V5 逐步扩展。它包含：

- 原始源文件与类型
- 文件元数据和生命周期
- PDF 页面或图片几何
- 可版本化解析、OCR、布局、表格、caption 等 Representation
- ContentUnit 与可重建 embedding
- 索引状态与失败原因

当前代码已从 `Document/Page/Chunk` 受控迁移到 Asset/Representation/ContentUnit/Evidence；PDF 与 Image adapter、Viewer、区域 Chat/Note、混合检索和精确上传入口已同步，M403B 工程发布门已关闭。

V3 稳定内核不把 Asset 封死为 PDF/Image。部署版本通过封闭模态注册表启用类型；V3 只启用 PDF/Image，后续音频、视频和其他文件通过 adapter、类型目录、locator codec、检索通道和 Viewer renderer 接入，不再次迁移 Workspace/Asset/Chat/Citation/NoteSource 主链。

### 4.3 Note

Note 是 Workspace 内的知识沉淀单元，支持：

- 独立创建的自由笔记
- 绑定引用的摘录笔记
- 绑定页面或文档的上下文笔记

## 5. 产品模块

### 5.1 Workspace 管理模块

功能范围：

- 创建、编辑、归档 Workspace
- 切换当前 Workspace
- 配置 Workspace 专属 Prompt
- 查看 Workspace 级文档数量、索引状态、聊天数、笔记数

### 5.2 资产接入模块

功能范围：

- 上传 PDF、PNG、JPEG、WebP
- PDF/图片资产列表和类型筛选
- 资产处理状态展示：`上传中 / 解析中 / 建索引 / 可用 / 失败 / 删除中`
- 查看失败原因与重试
- 删除资产并异步清理索引和派生表示

### 5.3 资产解析与索引模块

功能范围：

- 解析 PDF 文本
- 提取页面几何、段落、表格、图表和图片区域
- 对扫描 PDF 和独立图片执行 OCR
- 为独立图片生成 caption 和区域 ContentUnit
- 生成类型化 ContentUnit 与 embedding
- 建立向量索引
- 支持无文本层扫描 PDF 的 OCR fallback，并为重建索引预留能力

### 5.4 Evidence Viewer 模块

功能范围：

- PDF Renderer：页码、目录、缩放、文本/OCR 层和 region overlay
- Image Renderer：适应窗口、100%、缩放、平移和 region overlay
- 根据 `pdf_page/pdf_region/image_region` 与引用结果联动定位
- 桌面可调宽/全屏、移动端全屏证据层

### 5.5 检索与问答模块

功能范围：

- Workspace 内语义检索
- 显式 Asset 范围或全 Workspace 检索
- 基于召回片段进行问答
- 回答携带 citations
- 点击 citation 跳转到对应 PDF 页/区域或图片区域

### 5.6 笔记模块

功能范围：

- 新建自由笔记
- 从引用结果一键生成笔记
- 笔记关联文档、页面、chunk
- 后续支持按标签和时间筛选

### 5.7 标签模块

功能范围：

- Workspace 内创建标签
- 为文档、笔记打标签
- 用标签过滤知识对象
- 后续支持智能标签建议

### 5.8 聊天历史模块

功能范围：

- 按 Workspace 保存聊天线程
- 查看历史问题、回答与引用
- 重开历史对话
- 后续支持线程摘要与置顶

### 5.9 Prompt 配置模块

功能范围：

- 维护 Workspace 专属系统 Prompt
- 维护回答风格约束
- 维护结构化输出模板
- 后续支持 Prompt 版本管理

### 5.10 模型与 Provider 模块

功能范围：

- 维护 generation、embedding、vision、ASR 等 capability profile
- 为 Chat、摄取、检索和 Research 选择可用 provider/model
- 记录运行使用的 profile、版本、能力和非机密配置指纹
- 对能力缺失、配置漂移、超时和 provider 失败给出明确状态
- 密钥、endpoint 和隐私策略只保留在服务端配置边界

## 6. 端到端主流程

### 6.1 Workspace 建立流程

1. 用户创建 Workspace
2. 填写名称、描述、可选 Prompt 和模型 profile
3. 进入空 Workspace 首页
4. 系统引导用户接入第一份资料

### 6.2 资料入库流程

1. 用户接入资料
2. 源对象存入对象存储并创建 Asset
3. 根据模态 adapter 生成 Representation 和 ContentUnit
4. 使用匹配 capability provider 执行 OCR、转写、caption、结构解析或 embedding
5. 建立类型化 locator 和检索索引
6. 索引完成后将 Asset 标记为 `ready`
7. 资料可被查看、检索、问答和 Research 引用

### 6.3 浏览与检索流程

1. 用户在 Workspace 内选择文档或全库检索
2. 系统执行语义召回
3. 返回匹配片段与来源信息
4. 用户点击结果后跳到对应文档页

### 6.4 问答与引用流程

1. 用户在 Workspace 内提问
2. 系统在当前 Workspace 内检索相关片段
3. 将片段作为上下文送入问答
4. 返回答案与引用列表
5. 用户点击引用查看原文页码
6. 用户可将引用结果转存为笔记

### 6.5 笔记沉淀流程

1. 用户从回答或检索结果中选中某条引用
2. 点击生成笔记
3. 系统保存笔记正文、来源文档、页码、chunk 关联
4. 用户可补充标签与个人结论

## 7. 页面与信息架构

### 7.1 页面清单

- **工作区大盘门户页 (`/` page.tsx)**：采用 100% 浏览器全屏宽度展现，取消卡片式边框，使用 SaaS 极简扁平表格行列表展示所有工作区。
- **工作区控制台详情页 (`/workspaces/[workspaceId]` page.tsx)**：Chat-first 主画布与按需 Evidence Viewer。
- **文档大纲导航抽屉 (`/components/outline-tree.tsx`)**：收折式左子分栏，支持目录跳页。
- **对话面板 (`/components/chat-panel.tsx`)**：流式对话、卡片级随手记编辑器与 Citation 原文跳页。
- **随手记面板 (`/components/notes-panel.tsx`)**：笔记流沉淀管理。
- **配置面板 (`/components/settings-panel.tsx`)**：工作区系统 Prompt 配置管理。

### 7.2 推荐主界面布局

采用 Chat-first 自适应工作台：

- **左侧滑轨 (WorkspaceSidebar)**：管理 Workspace、线程和类型化资产列表，提供 `全部/PDF/图片` 筛选、上传、处理状态与 Chat 证据范围选择；tablet/mobile 下转换为抽屉。
- **主画布 (Chat / Notes / Settings)**：默认展示多资产 Chat，输入区显示全部资产或显式 Asset 范围；Notes 与 Settings 作为同级工作视图切换。
- **Evidence Viewer**：点击侧栏资产、citation 或笔记来源时按需打开，按 locator 使用 PDF 或 Image renderer；桌面端可拖拽调宽并保留 Chat 最小宽度，也可展开为全宽阅读模式。
- **移动端证据层**：Chat 默认占满工作区，资产列表和 Evidence Viewer 分别覆盖主画布并保留明确返回动作，不允许横向溢出。

默认主链为 `选择资产范围 -> 提问或启动 Research -> 阅读回答/Artifact -> 点击引用 -> 核验证据 -> 返回追问或沉淀笔记`。当前 PDF/Image 已支持页、区域和图片 Evidence；后续模态沿同一主链增加页面、时间段、关键帧或结构化定位。

## 8. 版本演进

### 8.1 V0 基础框架

- Workspace CRUD
- PDF 上传
- 文档状态机
- 基础 PDF 浏览
- 数据库与对象存储打通

### 8.2 V1 可用闭环

- PDF 解析、chunk、embedding、索引
- Workspace 内检索
- Chat + citations
- 笔记与标签基础能力
- Prompt 配置基础能力

### 8.3 V2 检索质量与可复现部署（已完成）

- OCR 质量评估与版面能力升级
- PostgreSQL lexical + Dense 的 hybrid/RRF，并经过质量、warm-up 和并发延迟门禁（已完成）
- 仅在 RRF 仍存在明确质量缺口时评估 rerank
- structured output 抽取模板
- 索引重建与配置管理

### 8.4 V3 多模态 PDF + 独立图片（已完成）

- 批准 Asset/Representation/ContentUnit/Embedding、locator、API 与迁移合同
- 页面布局、段落区域和 OCR bbox
- 表格结构与表格问题
- 图片/图表区域、描述与必要时的视觉召回
- 独立图片上传、OCR/caption、区域检索和查看
- `pdf_page/pdf_region/image_region` 类型化 citation 与 Viewer 精确高亮
- 按文本、扫描页、表格、图表、独立图片和无答案问题分层评测

### 8.5 V4 受控 Research Workflow（工程基线已完成）

- 固定、版本化、可恢复的 Research Run
- bounded 多 Agent fan-out/join、Verifier、Critic、Synthesizer
- HITL、SSE replay、Artifact、Claim/Evidence provenance
- Evaluation Dashboard 和工程运行证据

### 8.6 V5 多模态、多模型与多 Agent 产品化（当前主线）

- generation、embedding、vision、ASR 等 capability provider/profile
- Markdown/HTML、后续批准的文档、Audio、Video 等模态增量接入
- 跨模态检索、引用、查看和知识产物沉淀
- Quick Answer 与受控 Research 协作体验
- 多模型、多模态、多 Agent 的统一 Workspace 主链

### 8.7 后置质量与用户验证

- R803/后续模型质量评估
- M404 真实用户任务和重复使用验证
- Beta 与正式发布判断

## 9. V1 范围内必须有的功能

- 多 Workspace 管理
- Workspace 独立知识库
- Workspace 独立 Prompt
- Workspace 独立聊天历史
- Workspace 独立标签
- Workspace 独立笔记
- PDF 上传、解析、建索引
- PDF 浏览
- Workspace 内问答与引用回跳

## 10. 非目标

以下内容不属于 V1：

- 多人协作与权限系统
- 自动工作流编排
- 大规模 agent orchestration
- 跨 Workspace 联合检索
- 重型报表与复杂运营后台

当前战略非目标还包括：

- 通用 Agent 平台、无限递归委派、拖拽 Workflow 或自由插件市场
- 在没有用户任务和成本边界时一次性承诺所有模态覆盖
- 未经新版本审批修改已经落地的 Asset/Evidence 核心表、locator 含义或 Citation/NoteSource 保存语义
- 以模型名称、Agent 数量、GraphRAG、Milvus 或统一向量空间作为产品卖点
- 把 Omnilabel 标注/预测/数据集分析当作普通格式扩展；它需要独立用户研究和结构化分析架构

## 11. 成功标准

V1 成功的最低标准是：

- 用户能创建多个 Workspace，并看到它们的数据彼此隔离
- 用户能上传 PDF，并在数分钟内看到文档进入可检索状态
- 用户能在 Workspace 内提问，并获得带引用的回答
- 用户能点击引用跳回原文页码
- 用户能把引用内容沉淀为笔记，并用标签管理

V5 功能完成还需要满足：

- 至少两套已配置 generation provider/model 可以在产品链路中切换
- PDF/Image 与新增模态都能完成接入、ready、检索、引用、查看、删除和恢复
- Quick Answer 与受控 Research 可以共享多模态 Evidence，并保留类型化 locator
- Research 支持并行、审批、失败分支重试和 Artifact/Note 沉淀

后置产品有效性证据包括：

- citation 打开核验率和引用支持率
- 页面、区域、时间段或关键帧定位准确率
- 回答转笔记率和证据复用率
- 用户完成真实研究任务所需时间相对手工流程的变化
- Workspace 周回访和同一项目的重复使用

## 12. 当前建议

当前功能闭环、可复现部署、V3 PDF/Image 纵向链路和 V4 Evidence Research 工程基线已经建立。V5 先推进 provider/profile、多模态适配器和受控多 Agent 协作；Quick Answer 保持默认与既有保存语义，Research 继续使用冻结 Workflow/Prompt/Asset scope/provider profile。

多模型 provider 选择、跨模态 locator 和新模态数据/API 合同需要单独记录影响和审批，不能通过文档先行假设已经实现。R803 模型质量评估和 M404 真实用户任务后置为发布优化证据；在它们完成前，产品保持 `internal_preview`，但不停止 V5 功能建设。V5 当前规格见 `specs/v5/multimodal-agent-product/`。
