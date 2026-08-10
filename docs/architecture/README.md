# 架构文档

本目录用于存放工程实现层的架构设计文档。

文档分工：

- `../ssot/product-design.md`：产品边界、模块划分与版本范围
- `../ssot/system-architecture.md`：系统级高层架构裁决
- `detailed-system-architecture.md`：V1/V2 历史详细架构规划快照；当前开发不得跳过文件顶部的 legacy 状态说明
- `feature-map.md`：系统功能地图与拆分入口
- `database-design.md`：当前数据库 head、表分组、字段职责、约束、恢复 oracle 与变更门禁
- `database-er-legacy-document.mmd`：V3 Asset/Evidence 迁移前的 Document-era ER 历史快照，不是当前 schema
- `database-er.mmd` / `database-er.svg`：V1 目标全景关系图历史快照，不是当前 schema
- `api-contracts.md`：浏览器、BFF、FastAPI 之间的接口契约设计
- `job-state-machine.md`：V1 Document 入库状态机历史设计；当前 Asset job 合同以数据库/API/Worker 文档为准
- `auth-workstream.md`：已完成认证链路的历史模块任务拆分与执行顺序
- `implementation-roadmap.md`：V5 capability-first 项目实施路线与阶段目标
- `implementation-progress.md`：当前实施进度、下一步与阶段状态
- `research-workflow-runtime.md`：V4 Research runtime 边界、锁序、验证与故障处理 runbook
- `../research/product-strategy-2026-07.md`：`555.txt` 战略调研、风险判断与 skill 结论
- `../research/user-task-validation-2026-07.md`：第一用户复杂 PDF 任务验证协议、指标和立项门禁
- `evidence-contract-rfc.md`：已批准的 Evidence v1 合同、迁移裁决和不可破坏不变量
- `evidence-migration-impact.md`：Evidence 合同迁移、回滚、历史回放、删除/重索引和备份恢复影响设计
- `multimodal-workspace-interaction-design.md`：PDF + 图片工作区信息架构、交互状态和响应式设计
- `multimodal-asset-target-design.md`：Asset/Representation/ContentUnit/Embedding、PDF/Image locator 和迁移目标
- `multimodal-api-data-contract-draft.md`：已批准并实施的 V3 历史 Contract Draft，保留字段级迁移推导
- `modality-extension-contract.md`：后续音频、视频和结构化文件接入时保持核心模型与主链不变的扩展协议
- `../../specs/v2/retrieval-quality/`：已完成的 V2-A 检索质量需求、计划和任务
- `../../specs/v2/deployment-baseline/`：已完成的阶段 9 部署、观测、恢复和入口基线
- `../../specs/v3/evidence-contract/`：用户验证与早期 Evidence 合同发现记录
- `../../specs/v3/multimodal-workspace/`：已完成的 PDF + 图片 V3 需求、计划和任务；合同已批准，Phase 1-4 M401-M403B 已完成，M404 保持独立 Beta 门
- `../../specs/v4/evidence-research-workflow/`：V4 Research Workflow 的已批准合同、实施计划、任务和历史验收证据
- `../../specs/v5/multimodal-agent-product/`：当前多模型、多模态、多 Agent 主线规格、计划和任务

建议阅读顺序：

1. `../ssot/product-design.md`
2. `implementation-roadmap.md`
3. `implementation-progress.md`
4. `../../specs/v5/multimodal-agent-product/`
5. `../ssot/system-architecture.md`
6. `database-design.md`
7. `api-contracts.md`
8. `modality-extension-contract.md`
9. `research-workflow-runtime.md`
10. `../../specs/v4/evidence-research-workflow/`
11. 历史追溯需要时再读取 `detailed-system-architecture.md`、`job-state-machine.md` 和 `auth-workstream.md`

当前开发优先阅读 V5 规格、实施路线、实施进度、产品/系统 SSoT 和现有 Research runtime。V3 PDF/Image 与 V4 R000-R800 是完成基线；R803/M404 是后置验证，不是当前功能主线。
