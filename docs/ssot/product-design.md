# Citeframe 产品设计

## 1. 产品定位

Citeframe 是一个面向需要反复审阅论文、技术规范、评测报告和方案文档的 AI/软件工程师与技术研究者的证据型研究工作台。

`Citeframe` 是统一的产品、GitHub 仓库、本地目录和私有 npm scope 品牌。名称强调 citation 与 evidence framing，不绑定 PDF；内部 Python 包、`AI_PDF_*` 环境变量、数据库和对象存储 bucket 继续作为稳定运行标识，不随品牌迁移。

它不是单一的 PDF Chat，而是围绕 `Workspace` 组织的文档处理与知识工作环境。每个 Workspace 都拥有独立的知识库、独立 Prompt、独立聊天历史、独立标签、独立笔记，以及独立的索引配置与后续扩展能力。

核心目标不是提供一次性 PDF Chat，而是帮助用户基于多份复杂 PDF 与图片形成技术判断：先得到答案或结构化结论，再核验准确页码或图像区域，并把结论与证据沉淀在同一个项目上下文中。

当前版本状态：V1 可用闭环、Chat-first 工作台、V2-A Hybrid/RRF、阶段 9 可复现部署基线、V3 Phase 1-3 以及 Phase 4 M401-M403B 均已完成；21-case 工程/全栈 Evidence、7-case 真实模型、销卷恢复、500k/700k 检索容量和 PNG/JPEG/WebP 生产 Image 门禁全部通过。运行时已迁移到 Asset/Evidence 稳定内核，PDF 与 Image 均进入生产 registry；M404 真实用户价值仍为 `not_evaluable`，产品继续标记内部预览。

## 2. 目标用户

### 2.1 第一目标用户

- 需要基于多份论文、技术规范、评测报告、方案文档或技术图片做技术判断的 AI/软件工程师
- 需要反复核验原文证据并积累研究结论的技术研究者

`学习项目` 和 `面试展示` 是当前仓库的工程验证价值，不是产品第一用户画像。合同、财务、法律、泛个人学习和标注团队不是当前第一阶段市场。

### 2.2 核心 JTBD

当用户需要基于多份长 PDF 与图片形成判断、比较或可复用结论时，系统应帮助其快速获得有原文支持的答案，立即核验准确证据位置，并把结论与证据留在 Workspace 中，减少手工翻找、重复查证和散落笔记。

### 2.3 核心使用场景

- 为不同研究问题或技术项目创建 Workspace，例如 `RAG 评测`、`推理服务选型`、`模型安全调研`
- 上传多份 PDF 与图片，建立该 Workspace 的专属知识库
- 在 Workspace 内进行检索、问答、结构化抽取与笔记沉淀
- 通过引用回跳 PDF 页/区域或图片区域，保证答案可追溯
- 对多份资产进行比较、抽取和结论复用，而不是只进行单文档闲聊

### 2.4 护城河假设

- 证据保真：检索结果、回答和笔记可以稳定回到原始页码，并在多模态 PDF 阶段演进到精确区域
- 质量飞轮：真实失败样本、分层黄金集和定位/支持率评测持续约束检索与回答质量
- 上下文积累：Workspace 内的问题、证据、笔记和用户确认结果形成可复用研究资产

Chat UI、支持格式数量或接入某个模型本身不构成产品护城河。

## 3. 产品原则

- Workspace 是顶层隔离边界，任何知识、聊天、标签、笔记都不能串库
- 引用必须可追溯，答案不能只给结论不指向原文
- 问答是默认主任务，PDF/图片是按需展开的证据与精读层；不能让固定 Viewer 压缩多资产问答空间
- 问答是交互入口，不是最终价值；最终价值是形成可核验、可复用的技术结论
- 先做确定性 RAG，再做复杂 Agent 能力
- 先把上传、解析、索引、浏览、检索、引用、笔记闭环跑通，再扩展自动化
- V1 优先保证体验完整，而不是功能堆叠

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

一个 Asset 是上传到某个 Workspace 的 PDF 或图片，包含：

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

## 6. 端到端主流程

### 6.1 Workspace 建立流程

1. 用户创建 Workspace
2. 填写名称、描述、可选 Prompt
3. 进入空 Workspace 首页
4. 系统引导用户上传第一份 PDF

### 6.2 文档入库流程

1. 用户上传 PDF
2. 文件存入对象存储
3. 创建文档记录与任务记录
4. 后台执行解析
5. 生成 chunk 与 embedding
6. 索引完成后将文档标记为 `ready`
7. 文档可被浏览、检索、问答引用

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

默认主链为 `选择资产范围 -> 提问 -> 阅读回答 -> 点击引用 -> 核验证据 -> 返回追问或记笔记`。PDF 支持划词提问/记笔记和区域 Evidence；独立图片框选已接通 Ask AI、直接 Note、输入 Evidence 恢复与 frozen Viewer 跳转，M403B 后 PNG/JPEG/WebP 生产入口已启用。

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

### 8.5 Workspace 深化（后续）

- Prompt 版本管理
- 会话摘要
- 保存视图
- 工作区首页摘要
- 多 provider embedding 切换

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

- 在 V3 同时接入音频、视频和标注数据
- 把模态扩展做成可上传任意文件的动态插件市场
- 未经新版本审批修改已经落地的 Asset/Evidence v1 核心表、locator 含义或 Citation/NoteSource 保存语义
- 以模型名称、Agent、GraphRAG、Milvus 或统一向量空间作为产品卖点
- 把 Omnilabel 标注/预测/数据集分析当作普通格式扩展；它需要独立用户研究和结构化分析架构

## 11. 成功标准

V1 成功的最低标准是：

- 用户能创建多个 Workspace，并看到它们的数据彼此隔离
- 用户能上传 PDF，并在数分钟内看到文档进入可检索状态
- 用户能在 Workspace 内提问，并获得带引用的回答
- 用户能点击引用跳回原文页码
- 用户能把引用内容沉淀为笔记，并用标签管理

下一阶段产品有效性还需要验证：

- citation 打开核验率和引用支持率
- 页码/区域定位准确率与无证据拒答率
- 回答转笔记率和证据复用率
- 用户完成真实研究任务所需时间相对手工流程的变化
- Workspace 周回访和同一项目的重复使用

## 12. 当前建议

当前功能闭环、可复现部署、V3 PDF/Image 纵向链路和 V4 Evidence Research 确定性工程基线已经建立。Quick Answer 保持默认与既有保存语义；Deep Research 仅在用户显式选择后创建独立 Run，并使用冻结 Workflow/Prompt/Asset scope/provider profile。

R800 scripted provider 工程门通过不等于真实模型质量或用户价值通过。R803 真实模型成对质量与 M404 目标用户任务仍是独立门禁；未完成时保持 `internal_preview`。Audio、Video 与文档类新模态均需单独立项和价值门；Omnilabel 的业务模型继续独立设计。V4 裁决与当前状态见 `specs/v4/evidence-research-workflow/`。
