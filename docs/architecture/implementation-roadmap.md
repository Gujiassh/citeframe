# 实施路线

## 1. 当前结论

Citeframe 已完成 V1/V2 基础闭环、V3 PDF/Image Evidence 主链和 V4 R000-R800 Research 工程基线。项目现在从“工程和评估先行”切换为“功能先行”：先完成多模型、多模态和多 Agent 协作能力，再进行模型质量评估和真实用户验证。

当前产品定位：

> Citeframe 是一个自托管的多模态 AI 知识工作台，用于统一组织资料、检索和理解内容、协作完成研究，并保留可回到原始资料的证据。

“全模态”是长期方向，V5 采用逐模态交付，不能把尚未接入的 Audio、Video 或 Office 宣称为当前能力。

## 2. 已完成基线

| 阶段 | 内容 | 状态 | 说明 |
| --- | --- | --- | --- |
| V1 | Workspace、PDF、OCR、Embedding、Chat、Citation、Notes | 已完成 | 真实 Web/API/Worker 链路已接通 |
| V2-A | PostgreSQL lexical + Dense + RRF Hybrid | 已完成 | 生产默认 Hybrid，部署和观测基线完成 |
| V3 | Asset/Evidence、PDF region、独立 Image、混合检索 | 已完成 | PDF、PNG/JPEG/WebP 已进入生产 registry |
| V4 R000-R800 | Research ledger、固定多 Agent、HITL、SSE、恢复、Evaluation Dashboard | 已完成 | 确定性工程门和 PostgreSQL/MinIO 恢复通过 |
| R803 | 真实模型成对质量 | 后置 | formal v1 已冻结失败，v2 不阻塞功能开发 |
| M404 | 真实用户价值 | 后置 | 在功能链路完成后再进行 |

V3/V4 的历史合同、运行证据和失败 artifact 保持不可变；新主线见 [`specs/v5/multimodal-agent-product/`](../../specs/v5/multimodal-agent-product/)。

## 3. V5-A：Provider 与模型能力层

先把模型接入做成可替换能力，而不是让业务代码绑定单一模型：

- generation、embedding、vision、ASR 使用 capability registry。
- provider/model 通过受控 profile 选择，运行时保存实际 profile、版本和非机密配置指纹。
- 当前已接入 OpenAI Responses 与 DeepSeek Anthropic generation adapter，并对缺失 key、HTTP/JSON/SSE 错误、超时边界和 provider metrics 有明确语义；至少两套可配置 profile、配置漂移和完整能力 registry 仍在 V5-A 后续切片。
- Web 设置、Chat 和 Research 显示当前使用的能力 profile。
- API key、endpoint、隐私策略留在 server-side secret boundary。

## 4. V5-B：多模态资料扩展

每种模态都要完成完整纵向闭环：上传 -> 解析/理解 -> Representation/ContentUnit -> 检索 -> Evidence locator -> Viewer/播放 -> Chat/Research -> 删除/恢复。

优先顺序：

1. 保持 PDF/Image 生产链稳定，整理共享 Asset/Evidence 入口。
2. 接入 Markdown/HTML 等文档类资料。
3. 接入 Audio：转写、说话人/段落、时间段定位。
4. 接入 Video：字幕、转写、关键帧/镜头和时间定位。

新模态必须有独立 brief、数据/API contract、adapter、locator codec、Viewer、检索和恢复测试，不能只增加文件扩展名。

## 5. V5-C：多 Agent 协作产品化

在 V4 固定执行器上做用户可用的协作体验：

- Quick Answer 继续作为低延迟默认入口。
- Research 提供 Planner、Researcher、Verifier、Critic、Synthesizer 和 Artifact Publisher。
- 支持有界并行、证据共享、冲突审批、单分支重试、取消和重启恢复。
- Web 展示计划、阶段进度、证据、冲突、失败和最终 Artifact。
- Agent 只能访问注册 Evidence 工具和 capability provider，不建设通用插件/无限递归平台。

## 6. V5-D：端到端整合与工程稳定

- 混合模态 Workspace、资产范围和统一 Chat/Research 入口。
- 多模型 profile、任务状态、成本和失败原因统一展示。
- 桌面/移动端主路径、部署 profile、运行手册和故障诊断完善。
- API/Worker/Web 重启、权限、删除、备份恢复和历史 Citation/NoteSource 回归。

完成 V5-D 后，产品可以作为功能完整的内部预览持续使用。

## 7. V5-E：后置质量与用户验证

功能完成后再集中推进：

- R803 或新版模型质量套件，按模态、任务和 provider/model 分层。
- M404 真实目标用户任务和重复使用验证。
- Beta/公开发布判断。

工程门、模型质量门和用户价值门必须分开记录，任何一层都不能冒充另一层。

## 8. 持续边界

- 不建设通用 Agent 平台、无限递归委派、拖拽 Workflow 或自由插件市场。
- 不让模型直接决定权限、预算、Workspace 范围或持久化事实。
- 不为了扩展模态而重做 Asset/Evidence/Citation/NoteSource 核心合同。
- 不在没有用户任务和成本边界时一次性承诺所有格式。
