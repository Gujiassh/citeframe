# V5-C 多 Agent 协作产品化详细规格

## 状态与边界

状态：`draft-for-approval`。

本文是 V4 delta 的字段级和验收级冻结候选。除已明确的 V5-A 和 V4 基线外，涉及 timeline 是否独立投影、artifact visibility、budget detail、pricing、top-k 和 R800 scope 的内容都是 proposed，必须在 `open-decisions.md` 取得批准后才可成为 worker contract。

## 1. 产品目标

用户可以：

1. 从 Quick Answer 或显式 Research 入口开始任务；
2. 理解 Research 当前阶段、并行分支和等待原因；
3. 审批计划、处理冲突、重试单个失败分支、取消运行；
4. 查看 Evidence、Claim verification、conflict report 和最终 Artifact；
5. 看见本次 run 使用的冻结 provider/model/profile，而不是当前 Settings 值；
6. 在失败、断线、刷新、Worker 重启后继续得到一致的持久状态。

产品化不包括：动态 graph、无限递归 Agent、自由插件、模型修改拓扑、隐式写 Note、模型决定权限/预算/Workspace、隐藏推理持久化。

## 2. V4 基线与 V5 差量

| 能力 | V4 已有事实 | V5-C 允许的 delta |
|---|---|---|
| Run/Step/Attempt ledger | 已有闭集状态和 DB truth | 只增加产品投影/缺口测试；不重命名状态 |
| Fixed DAG | planner → approval → researcher* → join → verifier → critic → conflict? → synthesizer → publisher | 展示拓扑和 branch grouping；不开放动态 graph |
| Evidence tools | `evidence.search`, `evidence.load` | 展示调用产生的 Evidence bundle；不新增任意工具 |
| Agent I/O | Current V4 production uses `GenerationResearchAgents.DEFAULT_AGENT_RESULT_SCHEMAS` plus runtime mapping; `research-agent-results-v1` strict schema is evaluator/contract material, not an approved production binding | V5-C must inventory current production shape first; any strict schema promotion requires OD-C8 and a versioned runtime change |
| HITL | plan approval / conflict resolution | 完整化控制可见性、disabled reason、optimistic concurrency |
| Retry/cancel/recovery | 单步重试、cancel_requested、lease reclaim | 把现有行为变成可理解的 Web flow 和回归矩阵 |
| Provider snapshot | V5-A 已冻结 proposed/execution precedence | 消除展示缺口；不加 selector |
| Cost/budget | planning/execution ledgers、reserve/reconcile | 展示 limits/consumed/estimated；pricing 缺失 fail-closed |
| SSE | event allowlist + cursor replay | timeline projection 和 reconnect acceptance；不改变事件语义 |
| Artifact | plan/evidence/verification/conflict/final kinds | visible/internal policy、drill-down；不改变 artifact bytes |

## 3. 入口与状态模型

### 3.1 Quick 与 Research 的边界

- Quick Answer 是低延迟默认入口，继续使用既有 Chat message/SSE/Citation/NoteSource 语义。
- Research 是显式启动的独立 Run，拥有自己的 plan、execution snapshot、steps、attempts、events、decisions、artifacts、claims 和 evidence snapshots。
- 不把 Quick Chat message 强行包装为 Research Run；不把 Research intermediate claims 写入 Chat message。
- Web 可以共享 mode selector、workspace scope 和错误展示组件，但业务 truth 和 save path 保持分离。

### 3.2 Durable Run statuses

使用现有 closed set：

```text
planning
awaiting_plan_approval
queued
running
awaiting_human_decision
awaiting_retry
cancel_requested
completed
failed
cancelled
```

终态只有 `completed | failed | cancelled`，必须有 `finishedAt`。`cancel_requested` 不是终态；idle worker/reclaimer 负责完成 cancel。Web stream state (`idle | connecting | live | reconnecting | history_unavailable | contract_error`) 是 runtime-only，不能写入 Run status。

### 3.3 Step/Attempt statuses

```text
Step: pending | queued | running | waiting | succeeded | failed | cancelled | skipped
Attempt: running | succeeded | failed | timed_out | abandoned | cancelled
```

只有 plan/conflict gates 可以等待 HumanDecision；只有 `researcher` 有 branchKey。除 create（其并发控制由 workspace/run idempotency contract 和初始 state version 负责）外，所有 mutation 必须携带 `expectedStateVersion`，server 在正确锁序下拒绝 stale write。

## 4. Typed role I/O

权威基线分两层：当前 production runtime 是 `apps/worker/src/ai_pdf_worker/research_runtime_agents.py` 的 `DEFAULT_AGENT_RESULT_SCHEMAS`、prompt variable binding 和 runtime mapping；`apps/worker/src/ai_pdf_worker/research_agent_schemas.py` 的 `research-agent-results-v1` 是严格 evaluator/contract schema，当前不是已批准的 production binding。OD-C8 关闭前，本节只冻结 current production shape，不声称 strict V1 已上线。

### Planner

输入：当前 production prompt contract 的 `question`、`frozenAssetScope`、`planningLimits` 和 `planOutputSchema`。`planning/execution policy`、provider/profile 和 retrieval policy 只有在现有 prompt binding 已包含或 OD-C8 批准新版本后才能加入，不得由 product spec 先行扩充。

当前 production output 的 canonical minimum shape 是：

```json
{
  "summary": "non-empty",
  "knownGaps": ["..."],
  "estimatedProviderCalls": 1,
  "subproblems": [
    {
      "question": "...",
      "assetIds": ["asset-id"],
      "expectedEvidence": ["..."]
    }
  ]
}
```

`estimatedProviderCalls >= 1`；1–16 subproblems；运行时/API 从返回顺序 materialize subproblem identity/order。strict `additionalProperties=false`、token/cost estimates 是否进入 production，需要 OD-C8；在批准前不能把 evaluator strictness 当成当前 production behavior。

### Researcher

当前 production output 的 canonical minimum shape 是：

```json
{"claims":[{"text":"...","evidenceHandleIds":["handle-..."]}]}
```

运行时用 server-generated UUID 创建 canonical `DraftClaim`，模型不输出 claim ID。每个 claim 至少一个 evidence handle；`evidenceHandleIds` 必须来自该 branch 的 `evidence.search/load` tool call。没有任何 search handle 时，现有 runtime 在模型调用前以 `no_evidence_found` 失败；这不是通过空 claims 静默成功的产品路径。若 OD-C8 批准 strict V1，必须再冻结 extra-field rejection、版本化 validator 和 prompt binding。

### Verifier

输入是 join 后所有 researcher claims + Evidence snapshots，模型输出完整同集合 claim IDs：

```json
{"claims":[{"id":"server-claim-id","status":"supported|unsupported"}]}
```

缺少 claim、重复 claim、未知 claim 或 unsupported 被写成 supported 都是 contract failure。Verifier 不能补写新事实。

### Critic

只输出 conflict claim IDs：

```json
{"conflictClaimIds":["server-claim-id"]}
```

每个 ID 必须属于 verified claim set；不能在 critic 阶段篡改 Evidence 或直接决定最终结论。

### Synthesizer

只从 verified claims 做选择：

```json
{
  "factClaimIds": ["server-claim-id"],
  "unresolvedClaimIds": ["server-claim-id"]
}
```

最终 fact 必须 `verification=supported` 且 `conflict=none`。冲突 claim 只能进入 conflict/unresolved policy 允许的 section；Synthesizer 不能把自由生成的未验证事实注入 final report。

### Schema synchronization rule

`research_runtime_agents.py`、`research_executor_contracts.py`、API completion validation、Web fixtures 和本节必须以 current production V2 contract 为准，除非 OD-C8 批准 strict schema promotion。任何字段变更必须新建 schema version，更新 prompt binding、validator、runtime adapter、API persistence mapping、fixtures 和 focused tests，不能只改文档示例。

### Artifact Publisher

只发布由 server-side claim/evidence/provenance 校验通过的 artifact。模型输出不是持久化真相；publisher 以 API/DB records 和 immutable artifact bytes 为准。

## 5. Evidence、Claim、Artifact 与 join

### 5.1 Evidence handle scope

每个 handle 必须绑定：

```text
workspace_id
run_id
execution_snapshot_id
owner_step_id
branch_key?
tool_call_id
locator/evidence snapshot
processing_generation
representation_id
index_version
```

`evidence.load` 只能加载同 Workspace、同 Run、同 execution snapshot、已授权且有 immutable EvidenceSnapshot 的 handle。源已删除时仍可读取已保存的 excerpt/locator/sourceVersions snapshot，但 `sourceAvailable=false`，不得读取或打开当前 source bytes；current search 不得把 deleted Asset 作为候选。current index/generation 链不匹配时 fail-closed；这与“历史 snapshot 可读、当前 viewer/source 不可用”是两套语义。

### 5.2 Join contract

Join 是固定 control step，不是自由 Agent。它必须：

1. 等待所有 materialized researcher branches 终态；
2. 成功 branch 的 output schema 通过验证；
3. branch evidence handle 清单与 DB tool-call ledger 一致；
4. 失败 branch 按 retry policy 进入 `awaiting_retry` 或终止，不偷偷丢掉；
5. 重新执行/恢复时使用持久化 branch state，不依赖进程内 ThreadPool；
6. 同一个 execution 只能有一个有效 verifier input set；重复 finalize 必须幂等。

### 5.3 Artifact visibility

推荐固定 visibility：

| kind | 用户可见 | 用途 |
|---|---:|---|
| `research_plan` | 是 | 计划审批和回顾 |
| `evidence_bundle` | 是 | Researcher/branch evidence 阅读 |
| `verification_result` | 否，internal | 诊断/验证记录；不进入默认 user artifact union。若未来需要用户查看，必须新增 API/Web visibility decision |
| `conflict_report` | 是（有冲突时） | 决策输入 artifact |
| `trace_export` | 是，仅限 redacted/time-limited diagnostics | 现有 user artifact union；不能包含 secrets/raw requests/hidden reasoning |
| `execution_checkpoint` | 否，internal | 恢复/审计 |
| `final_report` | 是 | 最终 Artifact |

不新增 artifact kind 只为满足 UI 排版；`trace_export` 的现有 user visibility、redaction 和 time-limited retention 继续遵守 V4 contract。若 V5-C 要改变其 visibility、字段或默认 UI 入口，必须在 OD-C2 记录 additive API/security/retention decision。

## 6. Provider/profile 与 budget

### 6.1 Frozen profile

- create/planning revision 冻结 proposed planning/execution profile；
- approve 时重新校验 frozen asset/generation/index、workflow/prompt、profile fingerprint；
- approved execution snapshot 是 Research worker 唯一 provider truth；
- Web approved run 只读 execution snapshot；无 execution 且 plan proposed 时才读 proposed revision；不回退 current Settings；
- worker reserve/send 前检查实际 profile fingerprint；漂移返回 `research_provider_config_drift`，不调用 provider。该 code 必须在 Research safe-failure map 中保留 machine code、标记 non-retryable，并在 API/Worker/Web fixture 中验证；不能被未知-code fallback 改写为泛化失败后丢失 operator meaning。
- 一个 execution 仍是一组 server-resolved generation + embedding profile；不允许一个 branch 自选 provider。

### 6.2 Budget invariants

Planning 与 execution 使用独立 ledger。每次 provider/tool call 必须：

1. 使用 frozen limits；
2. reserve before send；
3. 超限在 send 前 fail-closed；
4. 成功/失败/timeout/unknown outcome reconcile；
5. retry 复用同一 run budget，不增加隐藏预算；
6. `max_parallel_researchers` 是硬上限；
7. pricing 缺失时不能估算为零或复用其他 provider 价格。

Web 至少展示 estimated/consumed cost、provider/tool calls、usage final 和 budget exceeded/failure reason。金额使用现有 `MoneyMicrounits`，不把 floating point cost 写入持久化。

## 7. Permissions 与控制动作

| 动作 | 默认权限 | 预条件 | 结果 |
|---|---|---|---|
| create | Workspace member | ready scope、concurrency、valid question | `planning` run |
| plan approve/revise | run creator | pending decision、hash/state version match | approve materializes fixed DAG；revise creates next revision |
| conflict decision | run creator | bound conflict artifact/hash/state match | exclude or unresolved; unsupported cannot become supported |
| retry branch/step | run creator | awaiting_retry、retryable code、budget left | only selected failed branch requeued |
| cancel | creator; owner can emergency cancel cost/security | non-terminal + state version | `cancel_requested` then `cancelled` |
| read | Workspace member | workspace/run membership | DTO filtered by authorization |

HumanDecision action、inputArtifactSha256、inputSnapshotSha256、request number 和 expected state version 必须一起校验。重复提交必须返回同一决定结果或明确 idempotent conflict，不得创建第二个 branch/decision。

## 8. Web 产品 projection

### 8.1 Timeline

Timeline 是 Events 的只读投影，不是新 truth。每行至少包含：

```text
seq
createdAt
kind
phase: planning|approval|research|verification|conflict|synthesis|publication|run
status
stepId?
branchKey?
artifactId?
safeFailure?
```

按 server seq 排序；SSE reconnect 通过 cursor replay；缺历史返回 `history_unavailable`，不拼接本地猜测状态。相同 seq 不重复渲染，unknown event fail-closed。

### 8.2 Branch and step view

Researcher branches 按 `branchKey` 分组，展示 question/subproblem、status、attempt、evidence count、provider/tool calls、failure 和 retry availability。Branch order 使用 plan order，不用完成时间排序。

### 8.3 Controls

按钮可见性和 disabled reason 必须由 `canManageResearchRun` + run/step/decision state 决定：

- 非 creator 不显示 approve/revise/retry/conflict decision；
- cancel 在 terminal 隐藏；`cancel_requested` 显示不可重复提交；
- retry 只针对 retryable failed step；embedding/provider drift 不提供自动 retry；
- conflict action 只绑定当前 `conflict_report` artifact/hash；
- malformed frozen profile 显示 unavailable，不显示 current Settings 替代值；
- mobile 保证 controls 不遮挡 timeline、artifact 或 evidence。

### 8.4 Artifact/evidence drill-down

Final report 的每个 fact/conclusion/unresolved/conflict section 必须能定位到 Claim，再定位到已公开的 EvidenceSnapshot、evidence locator 和 sourceVersions。EvidenceHandle 是内部运行时/ledger 关联，不在默认 user DTO 暴露。打开已删除源时展示 snapshot，不执行 Viewer。Evidence bundle 只显示 allowlisted excerpt/locator/sourceVersions，不显示 raw provider request、secret 或 hidden reasoning。

## 9. 失败、取消、恢复与幂等

- provider/tool/schema/permission/fingerprint failures 按稳定 SafeFailure code 映射；raw exception 不进入用户 DTO；
- provider drift、embedding index mismatch、unsupported claim 是 non-retryable，除非 policy 明确允许 operator action；
- transient provider timeout/network failure 可在 `RETRYABLE_FAILURE_CODES` 内单分支 retry；
- cancel_requested 不发布 final_report，除非已经完成并原子提交 final artifact；“cancel then final”必须由 DB state transition 防止；
- Worker lease reclaim 将 abandoned attempt 记录后按 cancel/requeue 规则继续；不重复扣 hidden budget；
- membership removal 按现有 contract cancel run；
- SSE 断线、浏览器刷新、API/Worker 重启后从 DB events/artifacts 重建，不依赖 in-memory state；
- idempotency key + expected state version 覆盖 create、decision、cancel、retry；重复请求不重复 materialize DAG、artifact 或 final report。

## 10. V5-C gates

| Gate | 必须完成 | 禁止事项 |
|---|---|---|
| C-G0 | V4 baseline inventory、A006/A007 residual map、dirty docs disposition | 重做 V4 executor |
| C-G1 | pure-productization delta、OD-C1/C2/C3/C4/C5/C8 approved | 默默改变 ledger/schema、top-k、pricing 或 R800 scope |
| C-G2 | Quick/Research entry、status/control projection freeze | 统一两套 save model |
| C-G3 | current production role I/O/join/Evidence/Claim/Artifact rules、OD-C3/C4/C8 approved | worker 自行扩展 output/schema 或把 evaluator schema 当 production binding |
| C-G4 | timeline/branch/control/retry/cancel/approval Web path | 只测静态 rendering |
| C-G5 | desktop/mobile, SSE replay, conflict/artifact comprehension | 用本地猜测替代 server seq |
| C-G6 | permission/budget/tool/provider Critical review | 把 provider secret/fingerprint preimage 放 UI/log |
| C-G7 | Quick independence + full API/Worker/Web + production-start E2E | 以 R803/M404 冒充功能 gate |

## 11. C001-C008 实现任务

- **C001 Entry/status**：冻结 mode boundary、run status projection、control matrix；验证 Quick SSE 与 Research DTO 不串链。
- **C002 Typed I/O**：把 worker schema、artifact payload、Web display type 逐项对齐；禁止 `dict[str, Any]` 绕过。
- **C003 Provider snapshot**：补齐 execution/proposed source fixture、profile labels、pricing/fingerprint drift；不加 selector。
- **C004 Evidence/Claim/join**：补齐 branch handle scope、join set、claim provenance、artifact visibility；验证 no cross-branch evidence。
- **C005 Control flows**：approve/revise/conflict/retry/cancel/recover 的 state/permission/idempotency UI and API tests。
- **C006 Presentation**：timeline、branch grouping、failure、artifact and evidence drill-down；desktop/mobile smoke。
- **C007 Boundary audit**：workspace, membership, allowlist, budget, provider drift, secret/log boundary；Critical review。
- **C008 Regression**：Quick Chat、Citation、NoteSource、Research save/restore、A007 contract 和 production-start E2E 全绿。
