# V4 Evidence Research Workflow 实施计划提案

## 0. 与当前主线衔接

1. M403A binary ANN S2 diagnostic 与新的完整 S0/S1/S2 canonical 已完成并关闭。
2. M403B 已经单独批准并完成，Image 数据库目录、API registry、Worker adapter、caption 配置和 Web 上传入口已同步启用。
3. V3 SSoT、测试与运行证据已同步；contract snapshot commit A=`466e5a3` 与 approval record commit B 已形成。
4. V4 R000-R800 确定性工程基线已完成，且未修改 Quick、Citation、Chat、NoteSource 或保存语义。

M404 真实用户验证继续推进。它不阻塞内部技术演示开发，但未完成时 V4 仍是 `internal_preview`，不得宣称用户价值已验证。

当前 canonical 为 `docs/evals/artifacts/r800-v1/deployment-20260728-v4/`：全部场景、真实 PostgreSQL/MinIO 备份恢复、对象字节/hash 与最终清理通过。scripted provider 只形成工程证据，R803 真实模型成对质量仍保持 `not_evaluable`。

## 1. R000 合同与语义 Oracle

- `requirements-discovery.md` 的产品方向已获批；Owner 于 2026-07-27 批准 R000 字段、状态机、API、Research SSE、权限、保留/删除、成本和迁移影响合同。
- 获批输入为 `data-state-contract-draft.md`、`api-event-tool-contract-draft.md` 和 `r000-approval-package.md` 的冻结 hash；批准事实与边界见 `r000-approval-record.md`，原输入保留审批前状态文字。
- 已冻结固定 DAG、节点输入输出、状态机、事件协议和预算语义。
- 已冻结 Workflow/Prompt version、Run/Step/Event/Artifact/HumanDecision 数据合同。
- 已冻结现有 Asset scope、EvidenceLocator、Citation、NoteSource 和 Chat 语义不变条件。
- 明确 LangGraph 只负责无状态固定图执行且不配置 checkpointer；PostgreSQL 业务账本与 immutable Artifact 是恢复和审计的唯一事实来源。
- 已完成持久化、权限、删除、取消、备份恢复和版本重放影响评审并取得明确批准。

R001-R007 已由以下获批交付物与 commit A/B 关闭；下一阶段为 R100 Evaluation-first：

- 字段级 schema：实体字段、枚举、必填/可空、唯一键、外键、版本字段、敏感字段和保留期限。
- 状态迁移表：Run/Step/HumanDecision 的合法迁移、终态、取消、超时、失败分支和恢复 checkpoint。
- 事件合同：持久化 `seq`、事件类型、payload allowlist、重复事件、`Last-Event-ID` 重放和订阅权限。
- Research event stream 必须与现有 Chat SSE 分离：独立 endpoint、事件命名空间、鉴权和 `Last-Event-ID` 重放语义；不得通过“扩展 Chat SSE”改变 Quick Answer 合同。
- API 合同：create/read/cancel/stream/decision/artifact 的请求、响应、错误、幂等键和跨 Workspace 拒绝矩阵。Evaluation persistence/API 延后到 R700 独立合同。
- 证据与 Artifact provenance：每个 claim、locator、sourceVersions、Artifact bytes/hash 和生成 Step 的绑定关系。
- 变更影响包：Alembic upgrade/downgrade、dump/restore、删除/保留、Quick Answer 回归和 Citation/NoteSource/Chat 不变 oracle。
- 评审记录：数据合同、权限、provider/tool boundary、成本上限、prompt-injection policy 和人工批准结果。

## 2. R100 Evaluation-first Baseline

- 从现有黄金集和真实 PDF baseline 中构造复杂研究任务，不把原有 retrieval case 直接冒充 Agent 质量证明。
- 覆盖比较、综合、冲突、证据不足和明确拒答。
- 冻结可重放的 Quick baseline；R100 不要求尚未实现的多 Agent 运行。
- 冻结后续 Quick/Research 成对执行所需的相同 Asset scope、provider/model、标签和评价规则；实际多 Agent 执行在 R300/R400 后进入 R800/R700。

R100 的退出条件是：同一 fixture、Asset scope、provider/model 下，Quick baseline、Research case、claim/evidence 标注、拒答规则、失败 taxonomy 和评分脚本均可重放；未完成前不能进入真实模型质量结论。

R100 已于 2026-07-27 通过。Canonical 输入、scorer、测试和报告见 `docs/evals/r100-evaluation-first.md` 与
`docs/evals/artifacts/r100-v1/`；报告明确保持 `modelQualityEvaluated=false` 和 `userValueValidated=false`。

## 3. R200 运行账本与版本

- 实体范围以获批 data contract 为准：WorkflowVersion、PromptVersion、PlanRevision、ExecutionSnapshot、ResearchRun、ResearchStep、StepAttempt、RetryRequest、ResearchEvent、ResearchArtifact、HumanDecision、ToolCall、EvidenceHandle、BudgetLedger、ProviderCall、IdempotencyRecord、Claim/Evidence/ArtifactClaim 及其关系。
- Artifact bytes 进入 MinIO，PostgreSQL 保存 metadata、hash、provenance 和状态。
- 事件先持久化后推送，保证重连和审计使用同一事实源。

实现结果：R200 已完成，数据库 head 为 `e8f1a2b3c4d5`。API service 持有全部 ORM/事务/原子状态迁移，Artifact bytes 进入 MinIO；R800 v4 的空部署恢复验证了账本与对象身份。

R200 与 R300 只有在 R000 获批、两阶段 Git recovery point 已形成、R100 exit gate 通过、字段/API/事件接口已冻结且存在可执行 schema/contract tests 后才可另行授权。API/迁移 lane 拥有全部业务账本、ORM、migration 和原子 service；R300 Worker 只消费获批 service/ports，不得拥有或编辑表、ORM、migration，也不得自行推断账本行为。

## 4. R300 固定多 Agent 执行器

- 实现 Planner、Researcher fan-out、Verifier、Critic、Synthesizer、ArtifactPublisher。
- Agent 只能调用注册的 Evidence search/load 工具，不直接访问 ORM、对象存储或任意网络。
- 使用受限并发、provider semaphore、run/step 预算和 join barrier。
- 保存 step attempt、工具输入输出摘要、Evidence locator IDs 和 provider usage；不保存模型思维链。

实现结果：使用固定拓扑、类型化 port 的 `BoundedResearchExecutor`，不引入 LangGraph 或通用 Agent runtime。PostgreSQL 继续是唯一业务事实源，锁顺序统一为 `Attempt -> Step -> Run -> call -> BudgetLedger`。

## 5. R400 Streaming、HITL 与失败恢复

- 实现独立 Research event stream，支持 `Last-Event-ID` 重放，不修改现有 Chat SSE。
- 增加计划审批和冲突裁决两个受控暂停点。
- 实现 cancel、timeout、bounded retry、checkpoint、lease/heartbeat 和失败分支恢复。
- 验证 API/Worker 重启、客户端断线、provider timeout 和重复提交下的幂等持久化。

## 6. R500 Web Research Run 体验

- 在 Chat 输入区提供明确的 Quick/Research 模式选择。
- Research 运行页展示只读 DAG/步骤时间线、并行状态、审批请求、Evidence 数量、错误和 Artifact。
- 继续复用 Evidence Viewer 打开 locator，不新增解释性营销模块或通用低代码画布。
- Artifact 提供 Markdown 阅读、Evidence 跳转和结构化 trace 导出。

## 7. R600 Observability

- 使用 OpenTelemetry 关联 run/node/tool/provider/DB spans。
- 复用 Prometheus 输出运行数、成功率、step latency、retry、token/cost 和并发指标。
- 日志使用扁平字段：`tag run_id= step_id= attempt= status= duration_ms=`。
- 观测字段、低基数指标、失败隔离和 Langfuse 边界冻结在 `r600-observability-contract.md`；Langfuse 只可作为未来 OTLP/开发消费端，不加入当前运行依赖或事实源。

## 8. R700 Evaluation Dashboard

- R700 不消费 R000 的候选 Evaluation DTO；独立 persistence/import/API/dashboard 合同已冻结在 `r700-evaluation-contract.md`。
- 可信离线 importer 原子写入 immutable suite/run/case/claim rows；浏览器只读且仅 Workspace owner 可见。
- 展示 suite -> run -> case -> claim/evidence failure 的逐层下钻。
- 支持 Workflow/Prompt version 和 Quick/Research 成对比较。
- 保存报告输入 hash、运行环境、provider/model 和原始 Artifact hash。
- 合成工程门、真实模型质量门和 M404 用户价值门保持分层显示。

## 9. R800 Critical Hardening 与面试演示

- 验收分层、威胁 oracle、重启/恢复场景和成对报告规则冻结在 `r800-acceptance-plan.md`。
- 完成权限、跨 Workspace、prompt injection/tool boundary、Evidence provenance 和成本失控审查。
- 完成并行时间重叠、unsupported claim 拒绝、HITL、断线恢复、进程重启恢复和 Artifact 去重演示。
- 完成桌面/移动端运行轨迹、Evidence 跳转和 Evaluation Dashboard Playwright 证据。
- 形成 5 分钟可重复演示脚本和架构决策记录。

实现结果：确定性工程门禁已通过，Critical review、运行手册与演示脚本分别位于 `docs/evals/r800-critical-review.md`、`docs/architecture/research-workflow-runtime.md` 和 `docs/evals/r800-demo-script.md`。R803 真实模型质量不在 scripted R800 中冒充完成。

## 依赖选择

- 编排：固定、类型化 `BoundedResearchExecutor`；不引入 LangGraph checkpoint 或通用 Agent runtime，PostgreSQL 账本负责恢复与审计。
- 业务账本：PostgreSQL/Alembic。
- Artifact：现有 MinIO/object storage。
- 事件：持久化 ResearchEvent + SSE。
- 观测：OpenTelemetry + 现有 Prometheus；Langfuse 只作为可替换的开发观测适配器。
