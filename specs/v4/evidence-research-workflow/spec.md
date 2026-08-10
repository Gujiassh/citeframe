# V4 Evidence Research Workflow 规格提案

> 当前策略说明（2026-08-03）：V4 R000-R800 是已完成的固定 Research/多 Agent 工程基线。后续产品顺序由 `specs/v5/multimodal-agent-product/` 接管：先多模型/provider profile，再多模态扩展，再多 Agent 协作产品化，最后进行 R803/M404。R803/M404 仍是后置验证，不阻塞 V5 功能开发；本文件中的 R000-D007、R100-R800 和历史评估结果保持不变。

## 状态

- 阶段：R000-R800 确定性工程基线已完成；R803 真实模型成对质量与 M404 目标用户价值仍未评估
- 工程门：R800 v4 在真实 PostgreSQL/MinIO、生产 API/Worker/Web 镜像和 scripted provider 上通过；`engineeringGate=pass`、`releaseGatePassed=true`
- 产品结论：M404 未完成前继续标记 `internal_preview`，本提案不替代真实用户价值验证
- 需求发现：[requirements-discovery.md](requirements-discovery.md) 的 D001-D007 已于 2026-07-25 获批；该批准不构成字段/API/保存合同或实现授权
- R000 批准：[r000-approval-record.md](r000-approval-record.md) 记录 Owner 于 2026-07-27 批准 `AP001-AP012` 推荐默认、无例外；commit A=`466e5a3`，approval record commit B 已形成；实现保持该冻结合同
- 冻结输入：[data-state-contract-draft.md](data-state-contract-draft.md)、[api-event-tool-contract-draft.md](api-event-tool-contract-draft.md) 与 [r000-approval-package.md](r000-approval-package.md) 保留审批前状态文字和获批 hash，不在原文件回填状态
- 运行证据：[`../../../docs/evals/r800-critical-review.md`](../../../docs/evals/r800-critical-review.md) 与 [`../../../docs/evals/artifacts/r800-v1/deployment-20260728-v4/`](../../../docs/evals/artifacts/r800-v1/deployment-20260728-v4/)

## 目标

在现有 Asset/Evidence、检索、Citation 和 Viewer 基础上，增加一个可选的深度研究模式。系统使用固定、版本化的多 Agent 工作流拆解复杂问题，并行检索证据，验证结论，经过必要的人工审批后生成可追溯的 Research Artifact。

默认 Quick Answer 单 Agent 链路保持不变。V4 不建设通用 Agent 平台。

## 工作流

```text
Planner
  -> Human plan approval
  -> Researcher fan-out (bounded parallelism)
  -> Verifier
  -> Critic / conflict detection
  -> Human decision when required
  -> Synthesizer
  -> ResearchArtifact (Run complete)
```

R700 Evaluation 是 Run 完成后的独立评测阶段，不是核心 DAG Step，也没有在 R000 获得 persistence/API 授权。Owner 后续授权的独立合同见 [r700-evaluation-contract.md](r700-evaluation-contract.md)：浏览器只读、owner 可见、可信离线导入，且不修改核心 Run/Event/Artifact 合同。

## 功能需求

- FR-001：用户显式选择 `quick_answer` 或 `deep_research`，系统不得隐式把普通问题升级为高成本研究运行。
- FR-002：Create/每次 revision 冻结 planning snapshot；批准只校验并精确复制其中 Workspace、Asset scope、Workflow/Prompt、provider/retrieval、policy 和预算为 ExecutionSnapshot，不解析 latest Asset/config。
- FR-003：Planner 只输出结构化研究计划；Researcher 按子问题和 Asset scope 通过注册工具检索，不直接访问数据库。
- FR-004：Researcher fan-out 必须在运行证据中证明真实时间重叠，并受并发与预算上限约束。
- FR-005：Verifier 对 claim 与 EvidenceLocator 的支持关系做 fail-closed 判定；未通过的 claim 不能进入最终报告。
- FR-006：Critic 记录冲突、缺口和无证据结论；需要人工裁决时运行进入持久化等待状态。
- FR-007：Human in the Loop 决策必须记录操作者、动作、时间、输入版本和可选说明，并从同一 checkpoint 恢复。
- FR-008：节点失败按版本化策略重试；超过上限后只重跑失败分支，不重复持久化已完成步骤和 Artifact。
- FR-009：运行事件使用持久化递增序号并通过 SSE 推送；客户端使用 `Last-Event-ID` 重连后不得缺失或乱序。
- FR-010：ResearchArtifact 使用独立命名空间，至少支持研究计划、Evidence bundle、验证结果、冲突清单和最终 Markdown 报告。
- FR-011：Artifact 保存 SHA-256、Content-Type、生成 Step、Workflow/Prompt versions、provider/model 和 Evidence provenance。
- FR-012：Prompt version 不可变；运行只引用冻结版本，后续编辑不得改变历史运行解释。
- FR-013：Observability 关联 `run_id / step_id / attempt / workflow_version / prompt_version`，提供 trace、结构化日志、延迟、token、成本、重试和 Evidence 数量。
- FR-014：Evaluation Dashboard 对同一 fixture、Asset scope、provider/model 下的单 Agent 与多 Agent 做成对比较。

## Evaluation Dashboard

至少展示：

- Evidence Recall/Precision
- Claim Support Rate
- unsupported claim 数量
- Citation locator accuracy
- 冲突发现率
- 完成率、重试率和恢复成功率
- 并行加速比、p50/p95 wall time
- token、provider 调用次数和成本
- Workflow/Prompt version 对比
- Human intervention 次数和等待时间

现有 40-case PDF baseline、21-case PDF/Image/mixed 工程集和 M404 用户任务分析只能作为输入来源；工程集通过不等于真实用户价值通过。

## 数据与 API 影响提案

实体、状态与关系范围以获批 data contract 为准，至少包含 Workflow/Prompt、PlanRevision/ExecutionSnapshot、Run/Step/Attempt/Event、Artifact/Claim/Evidence、Decision、Tool/Provider/Budget 与 Idempotency；API 覆盖 run/create/read/cancel/stream/decision/artifact。Evaluation persistence/API 使用后续获批的独立 R700 合同，不在 R000 内借用 Run 或 Artifact 临时拼装。

这些新合同已按 [r000-approval-record.md](r000-approval-record.md) 冻结并批准，commit A=`466e5a3` 与 approval record commit B 已形成。R100 fixture/scorer/Quick baseline exit gate 已通过，证据见 [`../../../docs/evals/r100-evaluation-first.md`](../../../docs/evals/r100-evaluation-first.md)。R200/R300 可以开始；不得改变现有 Asset、EvidenceLocator、Citation、NoteSource、Chat SSE 或保存语义来迁就工作流。

## 非目标

- 拖拽式 Workflow 编辑器
- 任意第三方插件、插件市场或运行时任意代码加载
- 自动长期记忆或模型思维链持久化
- 通用 Agent 角色/组织平台
- 自动写入 Note 或修改 Workspace 事实
- Audio/Video 接入
- 以 LangGraph、模型名称或 Agent 数量作为产品卖点

Research Memory 暂由经过验证的 ResearchArtifact、Citation 和用户主动保存的 Note 承担。

## 成功标准

- SC-001：默认 Quick Answer 的请求、持久化、Citation 和恢复行为保持不变。
- SC-002：至少一个复杂研究 case 产生三个真实并行 Researcher 分支，并在 trace 中证明执行时间重叠。
- SC-003：至少一个 unsupported claim 被 Verifier 拒绝且未进入最终 Artifact。
- SC-004：至少一个冲突进入人工审批，API/Worker 重启后可从原 checkpoint 恢复。
- SC-005：注入一个分支失败后仅该分支重试，最终无重复 Step、Event、Evidence link 或 Artifact。
- SC-006：SSE 断线重连后事件序列完整、单调且可重放。
- SC-007：最终报告中的每个事实 claim 都能回到冻结 EvidenceLocator；源 Asset 重处理不改写历史 provenance。
- SC-008：Dashboard 可复现同一批 case 的单 Agent/多 Agent质量、延迟、成本和恢复对比。

## 当前验收状态

- `SC-001`：通过 API/Worker/Web 全量回归保持 Quick、Citation、NoteSource 和保存合同不变。
- `SC-002`：R800 v4 provider timeline 记录 `maxActive=2`，三个 Researcher 分支真实重叠且未超过上限。
- `SC-003`：三个 unsupported Claims 均未进入最终 Artifact。
- `SC-004`：冲突 Decision 提交并在 API/Worker 重启链后恢复完成。
- `SC-005`：一次 transient provider failure 只产生一次分支 retry，最终 Artifact 唯一。
- `SC-006`：47 个持久化 Event 在 cursor 24 后完整重放 25-47。
- `SC-007`：最终 Claim/Evidence/Artifact provenance 与恢复前后对象字节/hash 通过。
- `SC-008`：Dashboard 与 immutable importer 已完成工程实现；真实模型 Quick/Research 成对质量报告仍为 `not_evaluable`，不能以 scripted provider 补齐。
