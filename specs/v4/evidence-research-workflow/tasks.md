# V4 Evidence Research Workflow 任务提案

## 当前状态

- [x] V3 M403A 完成 binary ANN S2 与完整 canonical
- [x] V3 M403B 经批准后完成 Image 生产启用
- [x] V3/V4 形成经授权的 contract snapshot commit A 与 approval record commit B（A=`466e5a3`；B 为本记录所在 commit）
- [x] V4 数据/API/状态机方案获得明确批准（2026-07-27；`AP001-AP012` 推荐默认，无例外；不含实现授权）

## R000 需求发现前置

- [x] RD001 形成多模态优先级与受控 Deep Research 用户流程草案（`requirements-discovery.md`，未批准）
- [x] RD002 Owner 批准产品主线、下一模态路线、Quick/Deep、HITL、Artifact 非自动保存与 Agent/tool 边界（2026-07-25；不含字段/API 实现授权）
- [x] RD003 关闭 `requirements-discovery.md` 第 11 节的逐段当前态文档漂移清单；`m403b_deploy_config` 于 2026-07-25 完成 code-backed independent re-review

## R000 合同

- [x] R000-D01 输出 `data-state-contract-draft.md`（冻结的审批前输入）
- [x] R000-D02 输出 `api-event-tool-contract-draft.md`（冻结的审批前输入）
- [x] R000-D03 输出 `r000-approval-package.md`，合并为 `AP001-AP012`（冻结的审批前输入）
- [x] R001 冻结固定 DAG 与 Agent/Tool 输入输出 schema
- [x] R002 冻结 Run/Step/Attempt/Event/Artifact/Claim/Evidence/HumanDecision/ToolCall/ProviderCall/BudgetLedger 状态与关系
- [x] R003 冻结 Workflow/Prompt version 和历史重放语义
- [x] R004 完成权限、删除、取消、备份恢复和成本边界评审
- [x] R005 定义现有 Chat/Citation/NoteSource 不变 oracle
- [x] R006 输出字段级 schema、唯一键/幂等键、事件 payload allowlist 和 API error matrix
- [ ] R007 完成 R000 审批闭环
  - [x] R007-A Owner 批准 `AP001-AP012` 推荐默认，无例外
  - [x] R007-B 在工作树完成 `r000-approval-record.md`，记录逐项决定、输入 hash、合同/测试映射和未授权边界
  - [x] R007-C 取得授权并形成不含自引用的 contract snapshot commit A（`466e5a3`）
  - [x] R007-D 回填 commit A SHA，以 approval record commit B 固化审批记录与规格状态

## R100 Evaluation-first

- [x] R101 建立复杂研究 case、failure taxonomy 和评分规则
- [x] R102 生成相同 Asset scope/provider/model 的 Quick Answer baseline
- [x] R103 定义 claim support、locator accuracy、conflict 和 refusal 指标
- [x] R104 定义并行、恢复、token/cost 和 HITL 工程指标
- [x] R105 生成可重放的 Quick baseline 与 Research fixture manifest/hash（`docs/evals/artifacts/r100-v1/`）

## R200 运行账本

- [ ] R201 实现 WorkflowVersion、PromptVersion、PlanRevision 与 ExecutionSnapshot
- [ ] R202 实现 ResearchRun、ResearchStep、StepAttempt、ResearchEvent 与 IdempotencyRecord
- [ ] R203 实现 ResearchArtifact、Claim/Evidence/ArtifactClaim provenance、typed locator clone 与 MinIO 存储
- [ ] R204 实现 HumanDecision、RetryRequest、ToolCall/EvidenceHandle、BudgetLedger/ProviderCall 与等待/恢复状态
- [ ] R205 完成 Alembic、downgrade 限制、dump/restore 和跨 Workspace 测试

R200/R300 必须等待 R000 approval、两阶段 Git recovery point 和 R100 exit gate，并取得单独实现授权。R000/R100/R200/R300/R400/R500/R600/R700/R800 的完成判定必须分别绑定 spec、plan、tasks、测试、运行 artifact 和 review 记录；不能只勾选代码任务。

## R300 执行器

- [ ] R301 接入 LangGraph 或经评审的成熟图执行库
- [ ] R302 实现 Planner 和结构化计划校验
- [ ] R303 实现 bounded parallel Researcher fan-out/join
- [ ] R304 实现 Evidence-only Tool registry
- [ ] R305 实现 Verifier、Critic 和 fail-closed claim gate
- [ ] R306 实现 Synthesizer 和 ArtifactPublisher
- [ ] R307 通过 R200 账本 service/ports 编排预算、provider usage、attempt 和取消；不拥有 ORM/migration

## R400 可靠性

- [ ] R401 实现持久化 SSE 事件协议和 Last-Event-ID 重放
- [ ] R402 实现计划审批和冲突裁决
- [ ] R403 实现 lease/heartbeat、timeout、retry 和失败分支恢复
- [ ] R404 验证 API/Worker 重启和客户端断线恢复
- [ ] R405 验证重复请求不产生重复业务记录或 Artifact

## R500 Web

- [ ] R501 增加 Quick/Research 模式选择
- [ ] R502 实现只读 DAG/步骤时间线和并行状态
- [ ] R503 实现 HITL 审批界面
- [ ] R504 实现 ResearchArtifact 阅读和 Evidence Viewer 跳转
- [ ] R505 完成桌面/移动端 Playwright

## R600 Observability

- [ ] R601 增加 run/step/tool/provider OpenTelemetry spans
- [ ] R602 增加 Prometheus 质量、性能、成本和恢复指标
- [ ] R603 增加扁平结构化日志和 trace correlation
- [ ] R604 评估 Langfuse 可替换适配器

## R700 Evaluation Dashboard

- [ ] R701 实现 suite/run/case/claim 数据接口
- [ ] R702 实现 Quick/Research 和 Workflow/Prompt version 对比
- [ ] R703 实现质量、延迟、成本、并行和恢复图表
- [ ] R704 保持工程质量、真实模型和 M404 用户价值证据分层

## R800 验收

- [ ] R801 完成 Agent/tool/prompt-injection/权限 Critical review
- [ ] R802 完成并行、HITL、失败恢复和 Artifact provenance 运行证据
- [ ] R803 完成单 Agent/多 Agent 成对质量报告
- [ ] R804 完成架构文档、运行手册和 5 分钟演示脚本

## 明确不做

- [ ] 不做拖拽 Workflow 编辑器
- [ ] 不做自由插件或插件市场
- [ ] 不做自动长期记忆
- [ ] 不做通用 Agent 平台
