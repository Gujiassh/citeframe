# V5 多模态 AI 知识工作台与 Agent 协作实施计划

当前阶段索引：V5-B/V5-C 的实现不得只依据本文件的阶段描述；字段、状态、API、locator、lane ownership 和验收以 [`README.md`](README.md)、[`open-decisions.md`](open-decisions.md)、[`v5b-detailed-spec.md`](v5b-detailed-spec.md)、[`v5c-detailed-spec.md`](v5c-detailed-spec.md)、[`implementation-lanes-v5bc.md`](implementation-lanes-v5bc.md) 和 [`verification-matrix-v5bc.md`](verification-matrix-v5bc.md) 为准。

## 1. 实施策略

V5 采用 capability-first 顺序：先把多模型接入、多模态处理和多 Agent 协作做成真实可用的产品能力，再集中进行模型质量评估和真实用户验证。R803/M404 继续保留为后置证据，不作为每个功能切片的前置门。

V3/V4 已完成的 Asset/Evidence、Citation、NoteSource、Quick Chat、Research ledger、SSE、HITL、恢复和 Evaluation Dashboard 是复用基线。V5 不重新迁移这些核心合同。

## 2. 阶段路线

### V5-A：Provider 与模型能力层

目标是让生成、Embedding、视觉理解和 ASR 等能力可以按 profile 选择和审计。

交付：

- capability registry 与 provider adapter 边界
- 生成 provider、Embedding provider、视觉 provider、ASR provider 的配置模型
- 多 provider/model 的服务端选择、健康检查、超时和明确失败
- Workspace/Run 使用的 provider profile 快照与非机密配置指纹
- Web 设置和运行信息中的当前能力/模型展示
- 保持 Quick Chat、Research 和旧 Citation/NoteSource 语义不变

退出条件：至少两套生成 profile 可以在同一产品链路中切换；缺少能力、配置漂移和 provider 错误都有可理解的失败状态；现有 PDF/Image 回归通过。

### V5-B：多模态资料扩展

目标是把 Asset/Evidence 入口扩展到新的资料类型，而不是只增加上传后缀。

交付顺序：

1. PDF/Image 共用链路整理和能力缺口收口。
2. Markdown/HTML 等文档类资料：解析、结构保留、文本检索和来源定位。
3. Audio：转写、说话人/段落、时间段 locator、播放/跳转和 Evidence Chat。
4. Video：转写、字幕、关键帧/镜头、时间段或 frame locator、Evidence Viewer。

每种模态单独完成 modality brief、数据/API contract、adapter、Representation、ContentUnit、locator codec、Viewer、检索和恢复测试后才进入生产 registry。

退出条件：已启用模态可以从上传到 ready、检索、引用、查看、删除和恢复；混合 Workspace 不改变既有 PDF/Image 语义。

### V5-C：多 Agent 协作产品化

目标是把现有固定 Research executor 变成用户可理解、可控制的协作体验。

交付：

- Quick/Research 入口和运行状态统一
- Planner、Researcher、Verifier、Critic、Synthesizer 的角色输入输出和共享 Evidence contract
- 有界并行、分支重试、取消、人工审批和恢复
- Research timeline、Evidence bundle、冲突清单和 Artifact 阅读
- 多模型 capability 选择与每个 Run 的 provider/model 快照
- Workspace 权限、预算和工具 allowlist 在所有 Agent 分支上保持一致

退出条件：用户可以启动一次复杂研究、理解每个阶段、处理审批/失败并拿到有证据来源的 Artifact；Quick Chat 不被 Research 侵入。

### V5-D：端到端整合与工程稳定

目标是将多模型、多模态和多 Agent 组合成一个稳定工作区。

交付：

- 混合模态资产范围、检索、引用和笔记
- provider/model 配置、任务状态、成本和失败原因的统一展示
- Web 桌面/移动端主路径
- API/Worker/Web 重启恢复、删除、权限和备份恢复
- 运行手册、部署 profile 和开发者文档

退出条件：完整功能链路通过工程回归，产品可以作为内部预览持续使用。

### V5-E：模型质量与用户价值

V5-D 完成后再推进，不阻塞前四个阶段：

- R803 或新版质量套件按模态、任务和 provider/model 分层运行
- 保留旧失败证据，不覆盖历史 campaign
- M404 真实用户任务和重复使用验证
- 根据真实证据决定 Beta/公开发布，而不是用工程绿灯替代质量或用户价值

## 3. 依赖和边界

- V5-A 是 V5-B/V5-C 的共同依赖；模态 adapter 不直接实现 provider 选择。
- V5-B 复用 Asset/Evidence/Citation/NoteSource，不将 UI runtime 状态写入持久化模型。
- V5-C 复用 V4 Research ledger 和固定 executor，不建设通用 Agent runtime。
- 新模态、新 provider 和保存语义变更分别记录 contract、迁移影响和审批状态。
- 质量评估可以并行准备测试工具，但不能把未完成的评分结果写成产品功能失败。

## 4. 当前优先级

1. V5-A Provider 与模型能力层
2. V5-B 多模态资料扩展
3. V5-C 多 Agent 协作产品化
4. V5-D 端到端整合与工程稳定
5. V5-E 模型质量与用户价值
