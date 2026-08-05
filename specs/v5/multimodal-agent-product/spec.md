# V5 多模态 AI 知识工作台与 Agent 协作规格

## 状态

- 阶段：主动开发主线
- 目标：先完成可用的多模态、多模型和多 Agent 功能，再进行模型质量评估和真实用户验证
- 基线：V1/V2、V3 PDF/Image、V4 R000-R800 工程合同已经完成；V3/V4 的历史证据和保存语义继续有效
- 后置门：R803 真实模型质量评估和 M404 真实用户价值验证不再阻塞 V5 功能开发，但仍是后续 Beta/发布判断依据

## 1. 产品目标

Citeframe 是一个自托管的多模态 AI 知识工作台。它将不同类型的资料统一放入 Workspace，完成解析、理解、检索、问答、研究和证据沉淀；用户可以在回答、Research Artifact 和笔记中回到原始资料的具体位置。

“全模态”是长期产品方向，不代表第一轮一次性接入所有格式。V5 采用逐模态交付：每种模态都必须有明确的输入、处理表示、检索通道、类型化 locator、查看方式和失败语义。

## 2. 目标范围

### 2.1 多模型与 Provider

- 生成、视觉理解、Embedding、ASR 等能力通过 capability-based provider contract 接入。
- 模型和 provider 通过受控 profile 选择，不在业务代码中散落模型名称分支。
- 支持为不同能力配置多个 provider/model，并在运行时记录实际 profile、版本和非机密配置指纹。
- API key、endpoint 和隐私策略只存在于服务端配置或 secret boundary，不能进入 Workspace 数据、Prompt、Artifact 或日志。
- 现有 Quick Chat、Citation、NoteSource 和历史 Run 的保存语义保持不变；涉及持久化字段或 API contract 的扩展必须单独形成合同和迁移影响说明。

### 2.2 多模态资料

V5 的模态顺序如下：

1. 保持 PDF、PNG/JPEG/WebP Image 的生产链路可用，并把共享 Asset/Evidence 能力整理成新增模态的稳定入口。
2. 优先接入文档类资料（Markdown/HTML 以及后续批准的 Office 文档），统一文本、结构和来源定位。
3. 在有明确任务边界后接入 Audio：转写、说话人/段落信息和 `audio_range` 时间段 Evidence。
4. 在有明确任务边界后接入 Video：转写、字幕、关键帧/镜头和 `video_range` 或 frame Evidence。

每个新模态必须单独提交 modality brief，说明用户任务、Representation、ContentUnit、locator、Viewer、检索通道、成本和失败恢复；不能只增加 MIME 类型。

### 2.3 多 Agent 协作

- 保留 Quick Answer 作为低延迟默认入口。
- Research 模式提供固定、类型化、受限并行的协作流程：Planner、Researcher、Verifier、Critic、Synthesizer 和 Artifact Publisher。
- Agent 只能使用注册的 Evidence 工具和 capability provider，不得直接访问 ORM、对象存储、Shell、任意网络或未批准插件。
- 协作过程需要展示可理解的阶段、进度、等待和失败分支；不把 Agent 数量或框架名称作为产品卖点。
- 共享内容以冻结的 Evidence、Claim、Artifact 和运行快照为准；不持久化隐藏推理。
- 支持分支并行、单分支重试、人工审批、取消、重启恢复和成本上限。

## 3. 功能完成定义

V5 的“功能完成”先看端到端可用性，不以模型质量分数作为前置条件：

- 用户可以选择并使用至少两套已配置的生成 provider/model，且 provider 失败不会破坏历史引用和保存语义。
- 生成、Embedding、视觉理解和 ASR 能力按 provider capability 进行校验；缺少能力时明确失败，不静默降级。
- PDF/Image 继续可上传、处理、检索、引用和恢复；新模态按单独 brief 逐个进入 ready。
- 多模态检索结果能进入同一 Workspace Chat 和 Research 流程，并返回对应类型的 Evidence locator。
- 用户可以启动 Research，看到计划、并行分支、证据、审批、失败重试和最终 Artifact。
- 既有 Quick Chat、Citation、NoteSource、删除和恢复合同保持回归通过。

## 4. 非目标

- 通用 Agent 平台、无限递归委派、拖拽式 Workflow 编辑器或自由插件市场
- 让模型直接决定权限、预算、Workspace 范围或持久化事实
- 为了支持更多模型而复制一套独立业务链路
- 在没有用户任务和成本边界的情况下，一次性承诺所有音频、视频、Office 和结构化数据格式
- 在功能建设阶段强制完成 R803 质量评估或 M404 用户验证
- 未经单独批准改变既有 Asset/Evidence、Citation、NoteSource、Chat 或保存合同

## 5. 后置验收

功能链路完成后，再按独立证据层推进：

- 工程验证：单元、集成、Playwright、恢复和安全边界
- 模型质量：R803 或新版按 provider/model、模态和任务分层评估
- 用户价值：M404 真实目标用户任务、复用和结论采用情况
- 发布判断：功能完成、工程稳定、模型质量和用户价值分开记录，不互相冒充
