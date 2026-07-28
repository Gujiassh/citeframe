# 实施路线

## 1. 当前结论

Citeframe 已完成 V1 可用闭环、Chat-first 工作台、V2-A Hybrid/RRF 生产验收和阶段 9 单机生产基线，不再处于 mock 或“先搭骨架”阶段。

当前主线调整为：

`可复现 PDF 基线（已完成） -> PDF + 图片工作区重设计与合同 -> 多模态 PDF -> 独立图片 -> Beta 用户验证`

Chat 继续是主任务画布；右侧已切换为按 locator 打开的 Evidence Viewer。Asset/Evidence 受控迁移、Citation/NoteSource 快照、Chat assetScope 和多模态 PDF region 已完成，当前进入独立图片纵向闭环。

## 2. 已完成基线

| 阶段 | 内容 | 状态 | 完成口径 |
| --- | --- | --- | --- |
| 1-6 | 定位、前端、鉴权、上传、Worker、PDF/OCR | 已完成 | Workspace 隔离、真实 PDF、OCR blocks、页面与 chunk 已接通 |
| 7 | Embedding 与检索 | 已完成 | pgvector、PostgreSQL lexical、页级 RRF 与显式 Dense/Hybrid 已接通 |
| 8 | Chat 与知识沉淀 | 已完成 | 流式回答、citation、消息分支、笔记、标签和 Chat-first 工作台已接通 |
| V2-A | 检索质量 | 已完成 | 40 条真实评测、warm-up、延迟和 4 并发门禁通过，默认 Hybrid |
| 9 | 部署、日志与观测 | 已完成 | 锁定镜像、迁移 gate、Prometheus、备份销卷恢复、Caddy 与全业务 smoke 通过 |

历史规格保留在 `specs/v1/`、`specs/v2/retrieval-quality/` 和 `specs/v2/deployment-baseline/`。

## 3. 已完成：V3 重设计与合同迁移

V3 范围已确认为多模态 PDF + 独立图片，以下设计与破坏性合同迁移已经完成：

1. 资产栏从 Document 列表升级为 PDF/Image Asset 列表。
2. Chat 增加冻结的资产证据范围，右侧升级为通用 Evidence Viewer。
3. 批准 Asset/Representation/ContentUnit/Embedding 稳定内核与封闭模态注册协议。
4. 批准 `pdf_page / pdf_region / image_region`、坐标空间和类型化子表。
5. 批准 Asset/Citation/NoteSource/Chat API、历史回放、删除和备份恢复语义。

完成门禁：目标设计已明确批准；Asset/Evidence migration、旧/新 Citation/NoteSource payload、dump/restore 与消息范围快照已有自动化 oracle。真实用户验证延期到 Beta，不阻塞内部实施。

## 4. Now：PDF + 图片纵向闭环

按一个完整用户链推进，不先抽象所有模态：

1. 已建立稳定 Asset 内核和模态注册表，并机械迁移现有 PDF/page/chunk/tag/citation/note source。
2. 页面几何、OCR bbox、`pdf_page/pdf_region` citation 与 PDF region overlay 已完成。
3. 已修复并重新验收表格、图表和页内图片区域：组合覆盖旋转/非对称 CropBox，空间去重候选，可靠关联 caption，并验证字符范围不重复 embedding。
4. 已完成 dormant 独立图片方向归一化、OCR、caption、区域 ContentUnit、`image_region` citation 和 Image Viewer。
5. 已实现图片框选 Ask AI、直接 Note、消息输入 Evidence 与 frozen Viewer 跳转，M304B Critical 已通过并关闭 M304。
6. M305 已融合文本 Dense、lexical、OCR/caption 候选和 Asset 范围过滤。
7. M401-M403B 已完成。M403A current-chain、cosine + binary 双索引和 binary64/3N fresh canonical 已通过：S0/S1/S2 全门通过，S2 9/9 Recall=`1.00`、load/index `2062.742s`、并发 p95 `246.531ms`。M403B 已完成 PNG/JPEG/WebP 生产上传、immutable-source failure/retry、检索/Evidence、长期 Worker 桌面/移动浏览器链、Image-enabled PostgreSQL/MinIO 销卷恢复与完整 artifact 校验，工程门禁 `releaseGatePassed=true`。

完成门禁：内部 PDF/图片黄金集达标；历史页码 citation 仍可回放；重处理不改变已保存证据含义；备份恢复通过。

## 5. Beta 与 Later

- Beta 前完成至少 5 名目标用户、20 个真实任务和 5 份复杂资产的验证；未完成时只发布内部预览。
- V4 Evidence Research Workflow 的 R000-R800 确定性工程基线已完成：固定、版本化、可并行、可恢复、可审批、可观测和可评测的 Research workflow 通过真实 PostgreSQL/MinIO 发布验收。
- V4 已包含 Evaluation Dashboard、Prompt/Workflow Version、ResearchArtifact、独立 Streaming、Observability、Human in the Loop、真并行和失败恢复；不包含拖拽 Workflow、自由插件和自动长期记忆。
- 下一门是 R803 经明确批准的真实 provider Quick/Research 成对质量，以及独立 M404 目标用户价值；两者未完成前保持 `internal_preview`。
- Audio：ASR、说话人和时间段 locator 独立立项。
- Video：镜头、关键帧、字幕和时间段 locator 独立立项。
- Omnilabel：作为独立 discovery/edition/integration；先验证标注团队、权限、数据集 schema、预测对比和 SQL/分析查询语义。

每种模态必须有单独用户价值、数据合同、评测集和成本门禁，不能以“格式覆盖面”打包上线。
后续模态应复用已实现的注册、Asset、retrieval scope、Evidence、Citation/NoteSource 和 Viewer shell 协议；不得再次迁移核心模型。

## 6. 持续非目标

- 未经验证的一次性全模态平台化
- 没有质量缺口就接 reranker、GraphRAG 或统一向量空间
- 为规模话题提前迁移 Milvus
- V4 Evidence Research Workflow 之外的通用 Agent/LangGraph 平台
- TinyBERT、LoRA、DPO 等与核心证据任务无关的模型训练
- 未批准的持久化、Citation API 或保存语义变更
