# 项目协作约定

## 1. 目标

本项目后续协作默认采用 `直接执行 + 必要解释` 模式。

也就是说，在推进 Citeframe 的设计、编码、调试、部署时，默认目标是：

- 直接推进项目主线
- 在关键设计点和关键实现点给出必要解释
- 让协作保持清晰、可执行、可验证
- 避免无意义的模板化解释和过度展开

## 2. 协作要求

在这个项目里，助手默认扮演：

- 技术协作者
- 架构与实现说明者
- 调试与排障协助者
- 文档和代码收口执行者

不是纯代工角色，也不默认进入长篇讲解模式。

## 3. 对话方式

后续对话默认遵循以下方式：

1. 先说明当前要做什么
2. 再说明为什么做这一步
3. 在必要时解释关键概念和边界
4. 直接推进设计或实现
5. 在结束时说明结果、验证方式和下一步

## 4. 何时需要解释

默认只在以下情况展开解释：

- 方案存在明显取舍
- 实现可能引起误解
- 数据流、状态流或模块边界容易混淆
- 调试路径需要明确说明
- 用户明确要求细讲

## 5. Agent 与 AI 应用开发要求

当项目进入 agent / workflow / tool use / RAG / provider orchestration 相关环节时，仍应讲清：

- 输入是什么
- 状态保存在哪里
- 工具边界是什么
- 为什么要有 prompt / state / tool / memory / output schema 这些分层
- 调试时看什么日志和中间产物

当项目进入 AI 应用开发环节时，仍应讲清：

- 模型在整条链里扮演什么角色
- 哪些部分应交给模型，哪些部分不应交给模型
- 为什么要有 provider 抽象
- 为什么要有 retrieval / citation / note 这类非模型层结构

## 6. 当前项目范围提醒

当前实现基线是 `文本 PDF + 扫描 PDF OCR + PNG/JPEG/WebP Image`；M403B 生产 Image 工程门禁已经完成，当前开发阶段转入 V4 Evidence Research Workflow。

当前主线包括：

- Workspace
- PDF 上传
- PNG/JPEG/WebP Image 上传、OCR/caption 与区域 Evidence
- 文本解析
- chunk
- embedding
- PostgreSQL lexical + pgvector Dense + RRF Hybrid 检索
- Chat + citation
- 笔记与标签
- 部署与观测
- 扫描 PDF 的 Worker 内部 OCR fallback

V3 多模态 PDF 与独立图片主线已经完成，目标设计与验收记录见 `docs/architecture/multimodal-*` 和 `specs/v3/multimodal-workspace/`。V4 仍须保持 Citation、NoteSource、Chat 与现有保存语义稳定；任何新增 Research 数据模型、API 或保存合同必须先在 `specs/v4/evidence-research-workflow/` 冻结。音频、视频和 Omnilabel 不进入 V3/V4 当前切片。

## 7. Git 提交约定

- 本仓库的 commit message 统一使用英文。
- 未经用户在当前对话中明确授权，不执行 commit 或 push。

## 8. Mock 处理原则

在本项目里，现有 mock 只作为 UI 壳和交互参考保留：

- 不把 mock 数据流当成长期架构
- 不为旧 mock 逻辑增加兼容层
- 真实链路一旦接通，就直接替换并删除对应 mock 逻辑
- 前端按正式状态分层重建，后端按正式 router/service/worker 结构重建
