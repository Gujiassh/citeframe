# V4 Evidence Research Workflow 数据与状态合同草案

> 状态：**UNAPPROVED / 未批准**。
>
> 本文件只是 R000 字段级数据与状态机提案，不是 schema、migration、API、SSE、
> Worker 或 Web 实现授权。Owner 对 `requirements-discovery.md` D001-D007 的产品方向批准，
> 不等于批准本文件中的任何表、字段、枚举、删除、保留或外部 provider 语义。
> 在本文件第 14 节的 Owner 决策全部关闭并形成独立 approval record 前，不得据此修改代码。

## 1. 范围与依据

本草案只覆盖 Deep Research 的业务账本、不可变版本、状态恢复和 claim-level Evidence provenance。
Quick Answer 的 Chat、Citation、NoteSource、Evidence Viewer 和保存语义保持原样。

当前事实依据：

- Workspace 是全部数据、权限、查询和恢复的隔离边界。
- Asset 软删除保留身份，清理源对象与可重建内容；历史 Citation/NoteSource 依靠自身快照继续解释。
- `EvidenceLocator` 使用已注册的 `locator_kind/version` 和类型化 detail/regions，不保存任意 locator JSON。
- Chat 的 `all_ready | selected` 在请求时解析为明确的 Asset 顺序快照。
- Citation、MessageInputEvidence 和 NoteSource 复制 Asset 展示、processing generation、Representation、parser 和 index 快照。
- PostgreSQL 是业务事实来源；MinIO 保存对象 bytes；备份在停写窗口同时覆盖 PostgreSQL 与 MinIO。
- 恢复只进入空 PostgreSQL/Redis/MinIO，先验证闭集 SHA-256，再恢复并执行 migration/readiness/语义回放。

本草案不会把 `requirements-discovery.md` 中的 `audio_range`、`video_range`、heading/anchor、
workbook/sheet/cell/range 等产品定位示例定义为 locator、字段或 API schema。V4 R000 只消费当前生产
注册表已经支持的类型化 Evidence 合同。

## 2. 提议的通用数据库约定

以下约定本身仍待批准：

- ID：沿用当前 ORM 的 36 字符 UUID 文本，不引入第二套 ID 编码。
- 时间：全部使用 UTC、timezone-aware timestamp。
- 状态：使用 `VARCHAR + CHECK`，不使用 PostgreSQL enum，便于显式迁移和合同 diff。
- SHA-256：64 位小写十六进制；由 canonical bytes 或 canonical JSON 计算。
- Workspace：所有运行子表都保留 `workspace_id`。新表之间优先使用 `(workspace_id, parent_id)`
  复合 FK；引用现有 Asset/User/Locator 时，service/query 仍必须同时校验 Workspace，不能只凭 UUID。
- JSONB：只允许用于有版本、closed-schema、payload allowlist 和 canonical hash 的 manifest/event/checkpoint；
  不允许保存任意模型对象、任意 locator、插件配置或思维链。
- 文本长度：问题、Prompt、claim、审批说明和错误详情使用 `TEXT`，但 API/Worker 必须另有明确字节上限。
- 金额：使用整数微单位和 ISO 4217 currency，禁止浮点金额。
- 不可变：版本、Artifact、已提交 Decision、Claim 文本、Evidence snapshot 和 Event 均 append-only。
- 业务删除：不依赖数据库级无边界 cascade 删除对象；MinIO 与 typed locator 的清理必须有显式顺序和恢复 oracle。

## 3. 提议枚举

### 3.1 Version availability

`active | retired`

- `active`：可被新 ResearchRun 引用。
- `retired`：不能被新运行引用，历史运行仍可读取和重放。
- 已被任何运行引用的版本内容不能修改；retire 只改变可用性，不改变版本内容。

### 3.2 ResearchRun status

`planning | awaiting_plan_approval | queued | running | awaiting_human_decision |
awaiting_retry | cancel_requested | completed | failed | cancelled`

- `completed / failed / cancelled` 是终态。
- `cancel_requested` 是持久化中间态，不等同于已经停止 provider/Worker。
- `awaiting_retry` 表示自动重试已耗尽但运行尚未被宣告失败；是否允许人工重试仍待 Owner 决定。
- 不设置 `recovering` 状态；重启恢复是对同一非终态运行重新取得 lease，不改变业务语义。

### 3.3 ResearchStep kind

`planner | plan_approval_gate | researcher | join | verifier | critic |
conflict_decision_gate | synthesizer | artifact_publisher`

这些是固定 DAG 的 closed set。`join` 和两个 gate 是控制节点，不伪装成 Agent。

### 3.4 ResearchStep status

`pending | queued | running | waiting | succeeded | failed | cancelled | skipped`

- `waiting` 只允许用于需要 HumanDecision 的 gate。
- `failed` 可以在合法重试时回到 `queued`；历史失败由 StepAttempt 保留。
- `succeeded / cancelled / skipped` 对该逻辑 Step 是终态。

### 3.5 StepAttempt status

`running | succeeded | failed | timed_out | abandoned | cancelled`

Attempt 全部是终态记录，除新建时的 `running` 外不回退。lease 过期的 Attempt 标为
`abandoned`，同一逻辑 Step 可以新建下一个 Attempt。

### 3.6 HumanDecision

Decision type：`plan_approval | conflict_resolution`

Decision status：`pending | submitted | expired | cancelled | superseded`

提议 action：

- `plan_approval`：`approve | request_revision | cancel_run`
- `conflict_resolution`：`exclude_conflicted_claims | keep_as_unresolved | cancel_run`

冲突裁决是否允许“接受某一方为事实”尚未批准。本草案默认不允许人工绕过 Verifier 把 unsupported claim
变成 supported。

### 3.7 Artifact kind and visibility

Artifact kind：

`research_plan | evidence_bundle | verification_result | conflict_report |
execution_checkpoint | final_report | trace_export`

Visibility：`user | internal`

- `verification_result/execution_checkpoint` 固定为 `internal`。
- `final_report` 固定为 `user`。
- `trace_export` 只允许经过脱敏、无思维链的结构化轨迹。

### 3.8 Claim and Evidence relationship

Claim verification：`pending | supported | unsupported`

Claim conflict：`none | conflicted | resolved_excluded | resolved_unresolved`

ClaimEvidence relation：`supports | contradicts`

最终报告的事实/结论只允许 `verification=supported, conflict=none`。`resolved_unresolved` 只允许进入
“未解决问题/证据缺口”章节；`conflicted/resolved_excluded/unsupported` 均不能进入最终事实/结论。

### 3.9 Retention class

提议候选：`workspace_lifetime | time_limited_diagnostics`

具体期限、默认值和用户删除权仍未批准，见第 14 节。

### 3.10 Idempotency and Evidence tool records

Idempotency operation：

`create_run | cancel_run | submit_plan_decision | submit_conflict_decision | retry_step`

Idempotency status：`in_progress | completed | failed`

Evidence tool name：`evidence.search | evidence.load`

Tool-call status：`requested | running | succeeded | failed | cancelled | abandoned`

Provider-call status：`reserved | sent | succeeded | failed | outcome_unknown | cancelled`

Provider usage source：`reserved | actual | estimated`

本节 3.2-3.10 的 Run status、Step kind/status、Decision type/action/status、Artifact kind/visibility、
Claim/Evidence relationship、idempotency operation/status、tool-call vocabulary、Provider-call status 和
Provider usage source 是 API/event 草案的 canonical data vocabulary。API reconciliation 应引用这些值，不得
另造同义枚举；只有发现具体不可满足的不变量并经 R000 review 批准后，才能先修改本草案再同步其他草案。

## 4. 不可变版本实体

### 4.1 `workflow_versions`

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | WorkflowVersion 身份 |
| `workflow_key` | varchar(64), NN | 稳定逻辑名，例如固定 Research DAG 名；不是运行时插件名 |
| `version_number` | integer, NN | 从 1 开始的单调版本 |
| `availability` | enum, NN | `active/retired` |
| `manifest_schema_version` | varchar(32), NN | closed manifest schema 版本 |
| `manifest_json` | JSONB, NN | 固定节点、依赖、gate、预算策略和 retry policy；禁止代码或任意工具定义 |
| `manifest_sha256` | char(64), NN | canonical manifest hash |
| `created_by_user_id` | UUID text, nullable, FK users | 交互式平台管理员发布时存在；普通 Workspace owner 不因此获得发布权 |
| `created_by_release_id` | varchar(128), nullable | 部署 release 自动发布时存在 |
| `created_at` | timestamptz, NN | 创建时间 |
| `retired_at` | timestamptz, nullable | availability 变为 retired 的时间 |

约束与索引：

- `unique(workflow_key, version_number)`。
- `created_by_user_id / created_by_release_id` 必须恰有一个非空；具体平台管理员身份来源仍待批准。
- `unique(manifest_sha256)` 是否跨 key 去重待决定；最低要求对同一 key/version 唯一。
- version 内容列插入后不可更新；只允许 `active -> retired`。
- manifest 只能引用注册的 Step kind、Evidence search/load 工具名和 Prompt binding key。

### 4.2 `prompt_versions`

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | PromptVersion 身份 |
| `prompt_key` | varchar(96), NN | 稳定逻辑名 |
| `version_number` | integer, NN | 从 1 开始 |
| `step_kind` | enum, NN | 允许消费该 Prompt 的固定 Step kind |
| `availability` | enum, NN | `active/retired` |
| `template_text` | text, NN | Prompt 模板；属于敏感内部配置 |
| `variables_schema_version` | varchar(32), NN | closed variable schema 版本 |
| `variables_schema_json` | JSONB, NN | 只描述 allowlisted 输入变量，不允许任意 payload |
| `template_sha256` | char(64), NN | canonical template + variables schema hash |
| `created_by_user_id` | UUID text, nullable, FK users | 交互式平台管理员发布时存在 |
| `created_by_release_id` | varchar(128), nullable | 部署 release 自动发布时存在 |
| `created_at` | timestamptz, NN | 创建时间 |
| `retired_at` | timestamptz, nullable | retire 时间 |

约束：

- `unique(prompt_key, version_number)`。
- `created_by_user_id / created_by_release_id` 必须恰有一个非空。
- 被运行或 WorkflowVersion 引用后内容不可更新。
- Prompt 不能包含 provider credential、Workspace secret 或用户数据样本。

### 4.3 `workflow_prompt_bindings`

该关系避免把 Prompt ID 作为任意 JSON 埋入 Workflow manifest。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `workflow_version_id` | UUID text, NN, FK workflow_versions | 版本 |
| `node_key` | varchar(96), NN | manifest 内稳定节点 key |
| `prompt_version_id` | UUID text, NN, FK prompt_versions | 不可变 Prompt |

主键：`(workflow_version_id, node_key)`。binding 行随 WorkflowVersion 一起不可变；Prompt step kind
必须与节点 kind 相容。

## 5. ResearchRun、PlanRevision 与批准时执行快照

### 5.1 `research_runs`

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | Run 身份 |
| `workspace_id` | UUID text, NN, FK workspaces | 强隔离边界 |
| `created_by_user_id` | UUID text, NN, FK users | 发起人；D006 的审批/取消主体 |
| `origin_thread_id` | UUID text, nullable, FK chat_threads | 仅用于从 Chat UI 返回 Run；不把 Run 存成 ChatMessage |
| `status` | Run status, NN | 业务状态 |
| `state_version` | bigint, NN, default 1 | CAS/optimistic concurrency；每次产生业务 Event 的 semantic mutation 递增 |
| `next_event_seq` | bigint, NN, default 1 | 同一事务分配持久化 Event seq |
| `current_plan_revision_id` | UUID text, nullable, FK research_plan_revisions | 最新 append-only PlanRevision；循环 FK 需 deferred 或后加约束 |
| `approved_execution_snapshot_id` | UUID text, nullable, UNIQUE, FK research_execution_snapshots | 只在有效 plan approve 事务创建一次 |
| `cost_currency` | char(3), NN | Create 时冻结的 Run 单一 ISO 4217 currency；所有 revision/execution ledger 必须相同 |
| `latest_checkpoint_artifact_id` | UUID text, nullable, FK research_artifacts | 最新安全 checkpoint；循环 FK 需 deferred 或后加约束 |
| `cancel_requested_by_user_id` | UUID text, nullable, FK users | 发起人或 owner |
| `cancel_reason_code` | varchar(64), nullable | closed reason code |
| `cancel_requested_at` | timestamptz, nullable | cancel_requested 时必填；不依赖 Event retention 推导 |
| `failure_code` | varchar(128), nullable | 终止或等待重试原因 |
| `failure_message` | text, nullable | 已脱敏、用户可理解；不得含 provider payload/secret |
| `archived_at` | timestamptz, nullable | UI 归档，不等于硬删除 |
| `created_at` | timestamptz, NN | 创建时间 |
| `started_at` | timestamptz, nullable | 首个执行 Step 开始 |
| `finished_at` | timestamptz, nullable | 终态时间 |
| `updated_at` | timestamptz, NN | 最后状态更新时间 |

约束与索引：

- `unique(workspace_id, id)` 供子表复合 FK。
- 索引 `(workspace_id, status, created_at)`、`(created_by_user_id, created_at)`。
- 终态必须有 `finished_at`；非终态 `finished_at` 必须为空。
- `cancel_requested` 必须有 `cancel_requested_by_user_id`。
- `cancel_requested` 必须有 `cancel_requested_at`；未请求取消时该字段为空。
- 分配 Event `seq`、递增 `next_event_seq` 与递增 `state_version` 必须和 semantic mutation 在同一事务。
- `planning/awaiting_plan_approval` 必须没有 approved execution snapshot。
- `queued/running/awaiting_human_decision/awaiting_retry/completed` 必须且只能有一个 approved execution snapshot。
- Run 只保存身份、状态和当前不可变记录指针。question/scope/config/budget 不直接放 Run，以免 plan revision 原地改写历史。

### 5.2 `research_plan_revisions`

每次初始规划或批准前的 question/scope/config 变化都创建新 PlanRevision。旧 revision、Planner Step、
plan Artifact 和 Decision 保留，不原位更新。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | PlanRevision 身份 |
| `workspace_id` | UUID text, NN | 与 Run 相同 |
| `run_id` | UUID text, NN, FK research_runs | Run |
| `revision_number` | integer, NN | 从 1 单调递增且有 Workflow 上限 |
| `supersedes_revision_id` | UUID text, nullable, FK research_plan_revisions | revision 1 为空，后续指向前一 revision |
| `created_by_user_id` | UUID text, NN, FK users | 初始发起人或提交 revision 的发起人 |
| `question_text` | text, NN | 该 revision 的敏感用户问题 |
| `scope_mode` | `all_ready/selected`, NN | 该 revision 请求的范围语义 |
| `proposed_workflow_version_id` | UUID text, NN, FK workflow_versions | 批准时拟冻结的 WorkflowVersion |
| `planner_prompt_version_id` | UUID text, NN, FK prompt_versions | 生成本 revision plan 的 PromptVersion |
| `proposed_generation_provider` | varchar(64), NN | planning audit 及拟执行 provider；不保存 key |
| `proposed_generation_model` | varchar(128), NN | planning audit 及拟执行 model |
| `proposed_provider_config_fingerprint` | char(64), NN | 非 secret 配置 hash |
| `proposed_pricing_version` | varchar(64), nullable | provider 没有版本化价格时为空 |
| `proposed_data_boundary_policy_version` | varchar(64), NN | 获批的外部数据边界版本 |
| `proposed_embedding_provider` | varchar(64), NN | 拟执行 retrieval provider |
| `proposed_embedding_model` | varchar(128), NN | 拟执行 retrieval model |
| `proposed_embedding_version` | varchar(64), NN | 拟执行 embedding version |
| `proposed_retrieval_strategy` | varchar(32), NN | 拟执行 strategy |
| `proposed_retrieval_top_k` | integer, NN | 大于 0 |
| `planning_max_provider_calls` | integer, NN | Planner provider call 上限，大于 0 |
| `planning_max_input_tokens` | bigint, NN | Planner input token 上限，大于 0 |
| `planning_max_output_tokens` | bigint, NN | Planner output token 上限，大于 0 |
| `planning_max_cost_microunits` | bigint, NN | Planner cost 上限，大于等于 0 |
| `planning_cost_currency` | char(3), NN | Planner ledger ISO 4217 currency |
| `planning_max_step_attempts` | smallint, NN | Planner 总 Attempt 上限，大于 0 |
| `planning_budget_policy_version` | varchar(64), NN | Planner budget policy 版本 |
| `planning_retry_policy_version` | varchar(64), NN | Planner retry policy 版本 |
| `planning_max_step_timeout_seconds` | integer, NN | Planner Step timeout，大于 0 |
| `planning_max_provider_timeout_seconds` | integer, NN | Planner provider timeout，大于 0 |
| `proposed_max_parallel_researchers` | smallint, NN | 大于 0 |
| `proposed_max_step_attempts` | smallint, NN | 大于 0，总 Attempt 上限 |
| `proposed_max_provider_calls` | integer, NN | 大于 0 |
| `proposed_max_tool_calls` | integer, NN | 大于 0；每个持久化 ToolCall attempt 行计一次 |
| `proposed_max_input_tokens` | bigint, NN | 大于 0 |
| `proposed_max_output_tokens` | bigint, NN | 大于 0 |
| `proposed_max_cost_microunits` | bigint, NN | 大于等于 0 |
| `proposed_cost_currency` | char(3), NN | ISO 4217 |
| `proposed_budget_policy_version` | varchar(64), NN | 预算规则版本 |
| `proposed_retry_policy_version` | varchar(64), NN | retry/backoff/error allowlist 版本 |
| `proposed_max_run_timeout_seconds` | integer, NN | 大于 0 |
| `proposed_max_step_timeout_seconds` | integer, NN | 大于 0 |
| `proposed_max_provider_timeout_seconds` | integer, NN | 大于 0 |
| `planning_snapshot_sha256` | char(64), NN | question、planning Asset 闭集、Planner 限额及拟执行版本/config/budget 的 canonical hash |
| `created_at` | timestamptz, NN | revision 创建时间 |

约束：

- `unique(run_id, revision_number)`、`unique(workspace_id, id)`。
- revision 内容全部不可变；`research_runs.current_plan_revision_id` 是唯一可变“当前”指针。
- `planning_cost_currency/proposed_cost_currency` 必须等于 Run `cost_currency`；新 revision 不允许换币种。
- 每次 revision 创建都重新验证 membership、Workflow/Prompt availability、provider policy 和 planning budget。
- revision 的 planning provider usage 由该 revision 的 BudgetLedger/ProviderCall 记录；Planner StepAttempt 只提供
  派生聚合，不计入尚不存在的 execution budget。

### 5.3 `research_plan_revision_assets`

Planner 也需要可重放的范围，因此每个 PlanRevision 在创建时保存其 planning-time resolved Asset 闭集。
该闭集不是最终 execution scope。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `plan_revision_id` | UUID text, NN, FK research_plan_revisions | PlanRevision |
| `workspace_id` | UUID text, NN | 与 Run/Asset 相同 |
| `asset_id` | UUID text, NN, FK assets | planning-time Asset |
| `asset_order` | integer, NN | planning-time 稳定顺序 |
| `asset_kind_snapshot` | varchar(64), NN | 展示快照 |
| `asset_title_snapshot` | varchar(255), NN | 展示快照 |
| `processing_generation_snapshot` | integer, NN | Planner 实际看到的代次 |
| `index_version_snapshot` | integer, NN | Planner 实际看到的 index 版本 |

主键 `(plan_revision_id, asset_id)`；`unique(plan_revision_id, asset_order)`。

### 5.4 `research_execution_snapshots`

一个 Run 最多一行。它只在发起人批准当前 PlanRevision 时创建，代表唯一 immutable execution input。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | ExecutionSnapshot 身份 |
| `workspace_id` | UUID text, NN | 与 Run 相同 |
| `run_id` | UUID text, NN, UNIQUE, FK research_runs | 一 Run 只能批准一次 execution snapshot |
| `approved_plan_revision_id` | UUID text, NN, UNIQUE, FK research_plan_revisions | 被批准 revision，必须是 Run current revision |
| `approval_decision_id` | UUID text, NN, UNIQUE, FK human_decisions | 有效 approve Decision |
| `approved_plan_artifact_id` | UUID text, NN, FK research_artifacts | 用户实际批准的 plan bytes |
| `approved_plan_artifact_sha256` | char(64), NN | 防 stale/tamper |
| `input_version` | integer, NN | 等于 approved revision number |
| `question_text` | text, NN | 从 approved revision 复制，不引用可变 Run 字段 |
| `scope_mode` | `all_ready/selected`, NN | 精确复制 approved PlanRevision scope mode |
| `workflow_version_id` | UUID text, NN, FK workflow_versions | 精确复制 approved PlanRevision 的 proposed WorkflowVersion |
| `generation_provider` | varchar(64), NN | 精确复制 approved PlanRevision proposed provider |
| `generation_model` | varchar(128), NN | 精确复制 approved PlanRevision proposed model |
| `provider_config_fingerprint` | char(64), NN | 非 secret config hash |
| `pricing_version` | varchar(64), nullable | 精确复制 approved PlanRevision |
| `data_boundary_policy_version` | varchar(64), NN | 精确复制 approved PlanRevision |
| `embedding_provider` | varchar(64), NN | 精确复制 approved PlanRevision proposed retrieval provider |
| `embedding_model` | varchar(128), NN | 精确复制 approved PlanRevision proposed retrieval model |
| `embedding_version` | varchar(64), NN | 精确复制 approved PlanRevision proposed embedding version |
| `retrieval_strategy` | varchar(32), NN | 精确复制 approved PlanRevision proposed strategy |
| `retrieval_top_k` | integer, NN | 大于 0 |
| `max_parallel_researchers` | smallint, NN | 大于 0 |
| `max_step_attempts` | smallint, NN | 自动加人工重试的总上限 |
| `max_provider_calls` | integer, NN | 大于 0 |
| `max_tool_calls` | integer, NN | 大于 0；精确复制 approved PlanRevision；每个 ToolCall attempt 计一次 |
| `max_input_tokens` | bigint, NN | 大于 0 |
| `max_output_tokens` | bigint, NN | 大于 0 |
| `max_cost_microunits` | bigint, NN | 大于等于 0 |
| `cost_currency` | char(3), NN | ISO 4217 |
| `budget_policy_version` | varchar(64), NN | 精确复制 approved PlanRevision |
| `retry_policy_version` | varchar(64), NN | 精确复制 approved PlanRevision |
| `max_run_timeout_seconds` | integer, NN | 大于 0；HITL 等待是否计时待决定 |
| `max_step_timeout_seconds` | integer, NN | 大于 0 |
| `max_provider_timeout_seconds` | integer, NN | 大于 0 |
| `execution_snapshot_sha256` | char(64), NN | approved plan、approval-time assets、versions/config/budget 的 canonical hash |
| `created_at` | timestamptz, NN | 等于 plan approval transaction 时间 |

整行插入后不可更新。Workflow/Prompt/provider/retrieval/budget/policy 字段必须从 approved PlanRevision
精确复制；审批事务只重新验证这些版本仍可用且符合政策，不能选择当前 active/newer 值。
`provider_config_fingerprint` 不是远程 provider 回执。

### 5.5 `research_execution_assets`

在 approval transaction 中验证并复制 approved PlanRevision 的执行 Asset。不能直接把 PlanRevisionAsset 行
作为 execution truth，也不能重新解释 `all_ready` 或写入当前最新 generation/index。

字段与 `research_plan_revision_assets` 同形，但父键为 `execution_snapshot_id`；主键
`(execution_snapshot_id, asset_id)`，并有 `unique(execution_snapshot_id, asset_order)`。

批准时不重新解析 `all_ready`。事务只逐项验证 approved PlanRevision 已冻结的 Asset 仍属于 Workspace、ready、
未删除且 current generation/index 未漂移；批准期间新增的 ready Asset 被忽略，只有新 PlanRevision 才能纳入。
成功后按 exact order/generation/index 复制 planning 闭集；任一已冻结 Asset 漂移都拒绝 stale approval。系统不能
静默扩大 scope 或把 Planner 未见过的 Asset/version 放进 execution。

### 5.6 `research_execution_prompt_versions`

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `execution_snapshot_id` | UUID text, NN, FK research_execution_snapshots | approved execution snapshot |
| `node_key` | varchar(96), NN | 固定 DAG 节点 |
| `prompt_version_id` | UUID text, NN, FK prompt_versions | approved WorkflowVersion immutable binding 中的精确 PromptVersion |

主键 `(execution_snapshot_id, node_key)`。approval transaction 只从 approved PlanRevision 指定的
WorkflowVersion immutable binding 复制完整 Prompt 闭集，并验证仍允许执行；不能选择 newer active Prompt。
后续 retire/管理配置不改变历史 execution。

## 6. Step、Attempt 与 checkpoint

### 6.1 `research_steps`

ResearchStep 是逻辑 DAG 节点；重试不能新建第二个相同逻辑 Step。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | Step 身份 |
| `workspace_id` | UUID text, NN | 与 Run 相同 |
| `run_id` | UUID text, NN, FK research_runs | Run |
| `plan_revision_id` | UUID text, nullable, FK research_plan_revisions | Planner/plan gate 必填 |
| `execution_snapshot_id` | UUID text, nullable, FK research_execution_snapshots | approval 后执行节点必填 |
| `step_key` | varchar(128), NN | Run 内确定性逻辑 key；fan-out 使用 Planner 产生的稳定 branch key |
| `step_kind` | Step kind, NN | 固定职责 |
| `branch_key` | varchar(128), nullable | server-issued opaque non-semantic 分支 ID；不得含 subproblem/question/Asset title |
| `status` | Step status, NN | 逻辑 Step 状态 |
| `state_version` | bigint, NN, default 1 | CAS |
| `prompt_version_id` | UUID text, nullable, FK prompt_versions | 控制节点可为空；Agent 节点必填 |
| `max_attempts_snapshot` | smallint, NN | 不超过 Run/Workflow 上限 |
| `current_attempt_number` | smallint, NN, default 0 | 已创建 Attempt 数 |
| `input_sha256` | char(64), nullable | canonical input refs/hash；不保存思维链 |
| `error_code` | varchar(128), nullable | 最近失败的 closed code |
| `error_message` | text, nullable | 脱敏摘要 |
| `queued_at` | timestamptz, nullable | 排队时间 |
| `started_at` | timestamptz, nullable | 首次开始时间 |
| `finished_at` | timestamptz, nullable | 逻辑终态时间 |
| `created_at` | timestamptz, NN | 创建时间 |
| `updated_at` | timestamptz, NN | 状态更新时间 |

约束：

- `unique(run_id, step_key)`、`unique(workspace_id, id)`。
- 索引 `(run_id, status, step_kind)`、`(run_id, branch_key)`。
- `researcher` 必须有 `branch_key`，其他 kind 默认无 branch key。
- `waiting` 只允许 gate kind。
- Planner/plan gate 必须只引用一个 PlanRevision；Researcher 及其后继节点必须只引用唯一 approved ExecutionSnapshot。
- Step input 只引用对应 planning/execution snapshot、上游 Artifact/Claim/Evidence ID 和 closed tool request，
  不保存模型隐藏推理。

### 6.2 `research_step_dependencies`

主键 `(step_id, depends_on_step_id)`。两边必须属于同一 Run/Workspace，禁止自依赖和运行时自由递归。
resolved DAG 必须与 WorkflowVersion manifest 和已批准 Planner fan-out 边界一致。

### 6.3 `research_step_attempts`

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | Attempt 身份 |
| `workspace_id` | UUID text, NN | 与 Step/Run 相同 |
| `step_id` | UUID text, NN, FK research_steps | 逻辑 Step |
| `attempt_number` | smallint, NN | 从 1 单调递增 |
| `status` | Attempt status, NN | 单次执行结果 |
| `lease_token_hash` | char(64), nullable | 只存 lease token hash |
| `worker_instance_id` | varchar(128), nullable | 运行实例标识，不是凭据 |
| `lease_expires_at` | timestamptz, nullable | running 时必填 |
| `heartbeat_at` | timestamptz, nullable | 最后心跳 |
| `input_sha256` | char(64), NN | Attempt 输入快照 hash |
| `output_sha256` | char(64), nullable | 成功输出 hash |
| `provider_call_count` | integer, NN, default 0 | 本 Attempt 已持久化调用数 |
| `tool_call_count` | integer, NN, default 0 | 本 Attempt 已持久化 Evidence tool 调用数 |
| `input_tokens` | bigint, NN, default 0 | 非负 |
| `output_tokens` | bigint, NN, default 0 | 非负 |
| `cost_microunits` | bigint, NN, default 0 | 非负；Planner 使用 PlanRevision currency，approval 后使用 ExecutionSnapshot currency |
| `checkpoint_artifact_id` | UUID text, nullable, FK research_artifacts | 本 Attempt 最后安全 checkpoint |
| `error_code` | varchar(128), nullable | closed error taxonomy |
| `error_message` | text, nullable | 脱敏摘要 |
| `started_at` | timestamptz, NN | 开始时间 |
| `finished_at` | timestamptz, nullable | 终态时间 |

约束：`unique(step_id, attempt_number)`。只有 `running` 可更新 heartbeat/lease；进入终态后不可更新。
`provider_call_count/tool_call_count/input_tokens/output_tokens/cost_microunits` 是从同一 Attempt 的
ProviderCall、ToolCall 与 BudgetLedger 派生的只读聚合，不是预算或恢复的权威事实源；聚合只能随账本
reserve/reconcile 同事务刷新。

其中 `tool_call_count` 按持久化 ToolCall attempt 行计数，不按 `tool_call_key` 去重；失败/abandoned 后创建更高
`call_attempt_number` 会再次消耗 frozen `max_tool_calls`，使 retry 成本可见且有界。

Cancel 与人工 retry 不接收自由 comment。Cancel 审计保存在 Run；人工 retry 审计保存在下述 append-only request。
需要自由说明的 plan/conflict 流程继续使用 HumanDecision `comment_text`。

外部 provider 不保证 exactly-once。系统只承诺 business ledger exactly-once：进程可能在 provider 已收费但本地未确认时重试，
必须在成本报告中标记这种不确定性，不能伪称 provider 调用绝对去重。

#### 6.3.1 `research_step_retry_requests`

每个已接受的人工 retry 保存 append-only 审计行；自动 retry 不创建本表记录。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | retry request 身份 |
| `workspace_id` | UUID text, NN | 与 Run/Step 相同 |
| `run_id` | UUID text, NN, FK research_runs | Run |
| `step_id` | UUID text, NN, FK research_steps | 被重排的逻辑 Step |
| `failed_attempt_number` | smallint, NN | API 输入的失败 Attempt |
| `requested_by_user_id` | UUID text, NN, FK users | 合法操作者 |
| `expected_run_state_version` | bigint, NN | 接受请求时校验的 CAS |
| `expected_step_state_version` | bigint, NN | 接受请求时校验的 CAS |
| `requested_at` | timestamptz, NN | 与 Step requeue/Event 同事务 |

`unique(step_id, failed_attempt_number)`；同一失败 Attempt 最多接受一次人工 retry。幂等 request/response 仍由
`research_idempotency_records` 保存并指向本行；retry request、Step/Run requeue 和 `step_queued` Event 必须同事务
提交。下一 Attempt 仍只在后续 `queued -> running` lease 事务创建，不能因用户请求提前伪造 running Attempt。

### 6.4 checkpoint 内容

`execution_checkpoint` Artifact 的 closed schema 只允许：Run/Step/Attempt ID、已完成节点 key、已发布 Artifact ID/hash、
Claim/Evidence ID、待执行节点和 state version。禁止保存 credential、任意模型消息历史、隐藏思维链或未验证的任意工具 payload。
LangGraph 或其他图执行器 checkpoint 不是业务真相；恢复时必须与 PostgreSQL Run/Step/Event 账本核对。

### 6.5 `research_tool_calls`

Researcher 的 `evidence.search/load` 必须有持久化调用记录。进程重启不能只依赖模型上下文中的临时 handle。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | ToolCall 身份 |
| `workspace_id` | UUID text, NN | 与 Run/Step 相同 |
| `run_id` | UUID text, NN, FK research_runs | Run |
| `execution_snapshot_id` | UUID text, NN, FK research_execution_snapshots | 工具只允许 approval 后执行 |
| `step_id` | UUID text, NN, FK research_steps | 必须是 Researcher Step |
| `attempt_id` | UUID text, NN, FK research_step_attempts | 发起调用的 Attempt |
| `tool_call_key` | varchar(160), NN | Step 内确定性、retry 可重放的逻辑 key |
| `call_attempt_number` | smallint, NN | 同一 logical tool call 从 1 递增 |
| `call_order` | integer, NN | Attempt 内稳定顺序 |
| `tool_name` | `evidence.search/load`, NN | closed registry name |
| `tool_version` | integer, NN | 当前固定为 1；API composite key 为 `tool_name.v{version}` |
| `status` | Tool-call status, NN | requested -> running -> terminal |
| `request_sha256` | char(64), NN | closed tool request canonical hash；不保存 raw prompt/query |
| `result_count` | integer, NN, default 0 | 非负；search 成功后等于持久化 handle 数 |
| `error_code` | varchar(128), nullable | closed code |
| `error_message` | text, nullable | 脱敏摘要 |
| `created_at` | timestamptz, NN | requested 时间 |
| `started_at` | timestamptz, nullable | running 时间 |
| `finished_at` | timestamptz, nullable | terminal 时间 |

约束：

- `unique(step_id, tool_call_key, call_attempt_number)`、`unique(attempt_id, call_order)`；
  partial `unique(step_id, tool_call_key) WHERE status='succeeded'` 保证每个逻辑 Researcher Step 最多一个成功结果闭集。
- ToolCall 的 Run/ExecutionSnapshot/Step/Attempt 必须同一 Workspace 和执行链。
- `requested -> running -> succeeded/failed/cancelled/abandoned`；terminal 不回退。
- 状态、result count、EvidenceHandle 与 BudgetLedger tool-call reconcile 同事务提交。ToolCall 是内部账本变化，
  不创建核心 ResearchEvent；用户可见进度只在 Step waiting/succeeded/failed 等业务边界发 Event。
- 不保存 raw prompt、模型思维链、完整 query、tool raw response 或 Evidence bytes。
- 已成功 search 的 handle mapping 是重放事实；重启后不得再次 search 并偷偷换一批结果。
- crash 中的 requested/running call 标为 abandoned，由整个 StepAttempt 按 frozen policy 重试；不恢复半个 tool response。

### 6.6 `research_evidence_handles`

Opaque Evidence handle 是数据库身份，不是可解析 locator 字符串。`evidence.search` 每个 bounded result 创建一行；
`evidence.load` 只能使用同一 Run、ExecutionSnapshot 和 Researcher Step 的 handle。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | 返回给 Agent 的 opaque handle；调用方不能解析 |
| `workspace_id` | UUID text, NN | 与 Run 相同 |
| `run_id` | UUID text, NN, FK research_runs | Run scope |
| `execution_snapshot_id` | UUID text, NN, FK research_execution_snapshots | frozen execution scope |
| `owner_step_id` | UUID text, NN, FK research_steps | 只允许该 Researcher branch load |
| `created_by_tool_call_id` | UUID text, NN, FK research_tool_calls | succeeded evidence.search |
| `evidence_snapshot_id` | UUID text, NN, FK research_evidence_snapshots | 已捕获的 immutable typed Evidence snapshot |
| `result_order` | integer, NN | search 结果稳定顺序 |
| `handle_fingerprint_sha256` | char(64), NN | run/execution/step/tool/evidence/order canonical hash |
| `created_at` | timestamptz, NN | 创建时间 |

约束：

- `unique(created_by_tool_call_id, result_order)`、`unique(run_id, handle_fingerprint_sha256)`。
- handle 不跨 Run、不跨 approval snapshot、不跨 Researcher branch；无权限或 scope mismatch 一律 fail closed。
- mapping 只保存 hash、ID、顺序和引用。Evidence 内容只存在既有受控 EvidenceSnapshot/Artifact，不复制到 tool-call payload。
- handle 只允许同一 Researcher 逻辑 Step/branch 使用；Verifier、Critic 和 Synthesizer 通过持久化
  EvidenceSnapshot/Claim/Artifact ID 协作，不跨 Step 传递 tool handle。

### 6.7 `research_tool_call_input_handles`

批量 `evidence.load` 使用显式关系表，不在 ToolCall 上保存单个 handle 或 JSON ID 数组。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `tool_call_id` | UUID text, NN, FK research_tool_calls | 必须是 `evidence.load` |
| `evidence_handle_id` | UUID text, NN, FK research_evidence_handles | 同 Run/ExecutionSnapshot/Researcher Step |
| `input_order` | integer, NN | `0..19`，保持请求顺序 |

主键 `(tool_call_id, evidence_handle_id)`；`unique(tool_call_id, input_order)`。`evidence.search` 必须为 0 行，
`evidence.load` 必须为 1..20 行。每个 handle 自身的 `created_by_tool_call_id` 已提供原 search provenance，
因此 ToolCall 不保存错误的单一 parent-search 指针。

### 6.8 `research_budget_ledgers`

每个 Planning revision 和 approved execution 各有独立预算账本。每个 revision 使用自己的 frozen planning 上限，
Run 的 `planningUsage` 是所有 revision ledger 之和；创建新 revision 不抹除或重置历史 consumption。最大 revision
数量对 planning 总成本形成第二层硬上限。硬上限检查不能靠聚合查询或进程内计数。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | BudgetLedger 身份 |
| `workspace_id` | UUID text, NN | 与 Run 相同 |
| `run_id` | UUID text, NN, FK research_runs | Run |
| `plan_revision_id` | UUID text, nullable, UNIQUE, FK research_plan_revisions | planning ledger |
| `execution_snapshot_id` | UUID text, nullable, UNIQUE, FK research_execution_snapshots | research ledger |
| `currency` | char(3), NN | 对应 snapshot 的 ISO 4217 currency |
| `state_version` | bigint, NN, default 1 | 预算 reserve/reconcile 的 CAS |
| `reserved_provider_calls` | bigint, NN, default 0 | 已预留且未释放的调用数 |
| `reserved_tool_calls` | bigint, NN, default 0 | 已预留且未 reconcile 的 ToolCall attempt 数 |
| `reserved_input_tokens` | bigint, NN, default 0 | 非负 |
| `reserved_output_tokens` | bigint, NN, default 0 | 非负 |
| `reserved_cost_microunits` | bigint, NN, default 0 | 非负 |
| `actual_provider_calls` | bigint, NN, default 0 | 已确认发送的调用数 |
| `actual_tool_calls` | bigint, NN, default 0 | 已进入 terminal 的 ToolCall attempt 行数 |
| `actual_input_tokens` | bigint, NN, default 0 | 已确认或保守估算 |
| `actual_output_tokens` | bigint, NN, default 0 | 已确认或保守估算 |
| `actual_cost_microunits` | bigint, NN, default 0 | 已确认或保守估算 |
| `usage_final` | boolean, NN, default true | 任一 outcome_unknown/estimated call 存在时为 false |
| `updated_at` | timestamptz, NN | 最后 reconcile 时间 |

`plan_revision_id / execution_snapshot_id` 必须恰有一个非空。每次 provider send 或 Evidence tool call 前锁定
ledger；planning ledger 只读取 PlanRevision 的 `planning_*` 限额，execution ledger 只读取 ExecutionSnapshot
限额并包含 tool-call cap。无法证明不超限时禁止调用。远端结果确认后
reconcile ProviderCall；ToolCall terminal 后按每个 `call_attempt_number` reconcile 一次 tool count，retry 新行再次
消耗 hard cap。outcome unknown/abandoned reservation 保守占用，
不能静默释放后再次消费预算。

### 6.9 `research_provider_calls`

每次可能产生远端调用或计费的发送都有独立账本行；StepAttempt usage 只是派生聚合，不是事实源。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | ProviderCall 身份 |
| `workspace_id` | UUID text, NN | 与 Run/Step 相同 |
| `run_id` | UUID text, NN, FK research_runs | Run |
| `budget_ledger_id` | UUID text, NN, FK research_budget_ledgers | planning 或 research ledger |
| `step_id` | UUID text, NN, FK research_steps | 发起节点 |
| `attempt_id` | UUID text, NN, FK research_step_attempts | 发起 Attempt |
| `logical_call_key` | varchar(160), NN | Attempt 内稳定逻辑调用 key |
| `send_attempt` | smallint, NN | 同一逻辑调用的第几次实际发送，从 1 开始 |
| `status` | Provider-call status, NN | reserve/send/remote outcome |
| `request_sha256` | char(64), NN | canonical request hash；不保存 raw prompt/body |
| `provider` | varchar(64), NN | 精确复制 snapshot |
| `model` | varchar(128), NN | 精确复制 snapshot |
| `provider_config_fingerprint` | char(64), NN | 非 secret config hash |
| `reserved_input_tokens` | bigint, NN | 非负估算 |
| `reserved_output_tokens` | bigint, NN | 非负估算 |
| `reserved_cost_microunits` | bigint, NN | 非负估算 |
| `actual_input_tokens` | bigint, nullable | provider 确认值 |
| `actual_output_tokens` | bigint, nullable | provider 确认值 |
| `actual_cost_microunits` | bigint, nullable | provider 确认或版本化价格计算值 |
| `usage_source` | Provider usage source, NN | reserved/actual/estimated |
| `usage_final` | boolean, NN | outcome_unknown 或 estimator 时为 false |
| `provider_response_id_hash` | char(64), nullable | 可用时只存 hash |
| `error_code` | varchar(128), nullable | closed、安全错误码 |
| `reserved_at` | timestamptz, NN | 本地 reserve 时间 |
| `sent_at` | timestamptz, nullable | 实际开始网络发送 |
| `finished_at` | timestamptz, nullable | terminal/unknown 记录时间 |

约束：`unique(attempt_id, logical_call_key, send_attempt)`。`reserved -> sent -> succeeded/failed/outcome_unknown`；
发送前取消可 `reserved -> cancelled`。只有 transient policy 明确允许且预算仍足够时，outcome_unknown 才能创建
更高 `send_attempt`；旧 reservation 仍计入成本不确定性。

### 6.10 `research_idempotency_records`

所有公开 mutation 使用同一持久化机制覆盖 create/cancel/plan/conflict/retry，不靠进程缓存。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | record 身份 |
| `workspace_id` | UUID text, NN | 幂等作用域 |
| `actor_user_id` | UUID text, NN, FK users | 当前认证用户 |
| `operation` | Idempotency operation, NN | closed mutation |
| `canonical_resource_path` | varchar(512), NN | 不含 query/body/secret |
| `idempotency_key` | varchar(128), NN | 16..128 printable ASCII |
| `request_sha256` | char(64), NN | canonical request body hash |
| `status` | Idempotency status, NN | in-progress/completed/failed |
| `http_status` | smallint, nullable | completed/failed 时存在 |
| `result_resource_id` | UUID text, nullable | Run/Decision/Step 等主要结果 |
| `response_schema_version` | varchar(32), nullable | closed response snapshot schema |
| `response_json` | JSONB, nullable | 只保存该 mutation 的获批 response allowlist |
| `created_at` | timestamptz, NN | 首次请求时间 |
| `completed_at` | timestamptz, nullable | 结果冻结时间 |
| `expires_at` | timestamptz, NN | 获批安全重试窗口结束 |

`unique(actor_user_id, workspace_id, operation, canonical_resource_path, idempotency_key)`。同 key + 同 hash
返回冻结结果；同 key + 不同 hash 返回冲突。response 不得含 Prompt、Evidence 正文、secret 或 MinIO key。
过期记录的清理不能早于客户端/Worker 的最大合法 retry window，具体期限待 Owner 批准。

## 7. 持久化事件

### 7.1 `research_events`

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | Event 身份 |
| `workspace_id` | UUID text, NN | 与 Run 相同 |
| `run_id` | UUID text, NN, FK research_runs | Run |
| `seq` | bigint, NN | Run 内从 1 单调递增 |
| `event_type` | varchar(64), NN | closed allowlist |
| `event_schema_version` | varchar(32), NN | payload schema 版本 |
| `step_id` | UUID text, nullable, FK research_steps | Step event 才存在 |
| `attempt_id` | UUID text, nullable, FK research_step_attempts | Attempt event 才存在 |
| `dedupe_key` | varchar(160), NN | 同一业务动作稳定 key |
| `payload_json` | JSONB, NN | 按 event_type 的 closed allowlist |
| `created_at` | timestamptz, NN | 持久化时间 |

约束：

- `unique(run_id, seq)`、`unique(run_id, dedupe_key)`。
- Event 与对应状态变化必须在同一数据库事务提交；先持久化，后推送。
- SSE `Last-Event-ID` 只映射这个持久化 `seq`，与现有 Chat SSE 完全分离。
- payload 只允许状态、计数、ID、时间、reason code、进度百分比和 Artifact hash；不允许 question、Evidence excerpt、
  Prompt、审批说明、provider raw body、模型输出或 secret。

提议 event type 最小 allowlist：

`run_created | run_status_changed | step_queued | step_started | step_waiting |
step_succeeded | step_failed | attempt_abandoned | approval_requested |
decision_submitted | cancel_requested | artifact_published | run_completed |
run_failed | run_cancelled`

增加 event type 必须版本化，不得把未知 payload 静默解释为现有事件。

## 8. Artifact、Claim 与 Evidence provenance

### 8.1 `research_artifacts`

Artifact 行只在 bytes 已上传、size/hash 已校验后发布。临时对象不进入业务表，失败时清理临时 prefix。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | Artifact 身份 |
| `workspace_id` | UUID text, NN | 与 Run 相同 |
| `run_id` | UUID text, NN, FK research_runs | Run |
| `generated_by_step_id` | UUID text, NN, FK research_steps | 生成 Step |
| `generated_by_attempt_id` | UUID text, NN, FK research_step_attempts | 成功 Attempt |
| `artifact_kind` | Artifact kind, NN | closed kind |
| `visibility` | `user/internal`, NN | 产品可见性 |
| `logical_key` | varchar(160), NN | Run 内确定性发布 key，用于 retry 去重 |
| `schema_version` | varchar(32), NN | 结构化 Artifact schema；Markdown 也需 report schema version |
| `object_key` | varchar(1024), NN | Research 独立 MinIO namespace |
| `content_type` | varchar(255), NN | 精确 Content-Type |
| `byte_size` | bigint, NN | 大于等于 0 |
| `content_sha256` | char(64), NN | immutable bytes hash |
| `workflow_version_id` | UUID text, NN, FK workflow_versions | provenance |
| `direct_prompt_version_id` | UUID text, nullable, FK prompt_versions | 直接生成该 Artifact 的 Agent Prompt；控制节点 Artifact 可为空 |
| `generation_provider` | varchar(64), nullable | provider 生成 Artifact 时必填 |
| `generation_model` | varchar(128), nullable | 同上 |
| `supersedes_artifact_id` | UUID text, nullable, FK research_artifacts | 计划修订等显式版本链；不覆盖旧 bytes |
| `retention_class` | Retention class, NN | 保留策略 |
| `expires_at` | timestamptz, nullable | time-limited 才允许有值 |
| `created_at` | timestamptz, NN | 发布时间 |

约束：

- `unique(run_id, logical_key)`、`unique(object_key)`。
- 索引 `(run_id, artifact_kind, created_at)`、`(workspace_id, retention_class, expires_at)`。
- Artifact 插入后不可更新或原位覆盖；新版本使用新行和 `supersedes_artifact_id`。
- Run 只能有一个有效 `final_report` logical key；只有 `final_report` publish 必须与 Run `completed` 同事务完成。
  中间 Artifact 必须与其生成 Step 状态和对应 Event 同事务发布，不能提前把 Run 标为 completed。

`research_artifact_prompt_versions` 保存所有影响 Artifact 的 Prompt，而不只保存直接生成节点：

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `artifact_id` | UUID text, NN, FK research_artifacts | Artifact |
| `node_key` | varchar(96), NN | Run frozen DAG 节点 |
| `prompt_version_id` | UUID text, NN, FK prompt_versions | 影响该 Artifact 的 PromptVersion |

主键 `(artifact_id, node_key)`。approval 后 Artifact 的每个 binding 必须存在于同一 Run 的
`research_execution_prompt_versions`；`direct_prompt_version_id` 也必须出现在该关系中。approval 前的
`research_plan` Artifact 只允许绑定其 PlanRevision 的 `planner_prompt_version_id`。这样 final report 可以追溯
Planner、Researcher、Verifier、Critic 和 Synthesizer 的全部 Prompt versions，而不是只记录最后一个节点。

### 8.2 `research_claims`

归一化 Claim 是必要的：只有这样才能证明 Verifier 拒绝的 claim 未进入最终 Artifact，并把每个发布事实绑定到 Evidence。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | Claim 身份 |
| `workspace_id` | UUID text, NN | 与 Run 相同 |
| `run_id` | UUID text, NN, FK research_runs | Run |
| `claim_key` | varchar(160), NN | Run 内稳定 key |
| `claim_order` | integer, NN | Planner/Researcher 输出顺序 |
| `statement_text` | text, NN | 不可变事实陈述，敏感 Workspace 内容 |
| `statement_sha256` | char(64), NN | canonical statement hash |
| `produced_by_step_id` | UUID text, NN, FK research_steps | Producer |
| `verification_status` | Claim verification, NN | 默认 pending |
| `verified_by_step_id` | UUID text, nullable, FK research_steps | supported/unsupported 时必填 |
| `verification_reason_code` | varchar(64), nullable | closed reason；不是自由模型解释 |
| `conflict_status` | Claim conflict, NN | 默认 none |
| `critic_step_id` | UUID text, nullable, FK research_steps | conflicted 时必填 |
| `created_at` | timestamptz, NN | 创建时间 |
| `verified_at` | timestamptz, nullable | verification 终态时间 |

约束：`unique(run_id, claim_key)`、`unique(run_id, claim_order)`。
Claim 文本不可更新；Verifier 只能执行 `pending -> supported/unsupported` 一次。HumanDecision 不得把
`unsupported` 改成 `supported`。

### 8.3 `research_evidence_snapshots`

每条 Research Evidence 必须创建一份独立、不可变的现有 `EvidenceLocator` 快照：复制公共 locator 行和其当前已注册的
类型化 detail/regions，然后由本表唯一引用。不得保存 locator JSON，不得从 MIME、名称或“第一个字段”猜 kind。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | Research Evidence snapshot 身份 |
| `workspace_id` | UUID text, NN | 与 Run/Asset/Locator 相同 |
| `run_id` | UUID text, NN, FK research_runs | Run |
| `captured_by_step_id` | UUID text, NN, FK research_steps | search/load 来源 Step |
| `evidence_locator_id` | UUID text, NN, UNIQUE, FK evidence_locators | 独立克隆的 typed locator |
| `asset_id` | UUID text, NN, FK assets | Asset 软删除后保留 |
| `asset_kind_snapshot` | varchar(64), NN | 展示快照 |
| `asset_title_snapshot` | varchar(255), NN | 展示快照 |
| `excerpt_snapshot` | text, NN | 支持 claim 的最小必要 excerpt |
| `processing_generation_snapshot` | integer, NN | 与 locator/Representation 一致 |
| `representation_id_snapshot` | UUID text, NN | 与现有 Citation envelope 同义 |
| `parser_version_snapshot` | varchar(64), NN | 同义 |
| `index_version_snapshot` | integer, NN | 同义 |
| `retrieval_channel` | varchar(64), NN | 已注册 channel，不是 locator kind |
| `source_fingerprint_sha256` | char(64), NN | typed locator + sourceVersions + excerpt 的 canonical fingerprint |
| `created_at` | timestamptz, NN | 捕获时间 |

约束：`unique(run_id, source_fingerprint_sha256)`、`unique(evidence_locator_id)`。

Locator clone 必须通过当前注册 codec 复制；目前只可能是生产已批准的 `pdf_page/pdf_region/image_region`。
未来新模态必须先通过独立 modality contract，不能因为本表存在而自动进入 Research。

### 8.4 `research_claim_evidence`

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `claim_id` | UUID text, NN, FK research_claims | Claim |
| `evidence_snapshot_id` | UUID text, NN, FK research_evidence_snapshots | Evidence |
| `evidence_order` | integer, NN | Claim 内稳定顺序 |
| `relationship` | `supports/contradicts`, NN | Verifier 判定 |
| `assessed_by_step_id` | UUID text, NN, FK research_steps | Verifier |

主键 `(claim_id, evidence_snapshot_id)`；`unique(claim_id, evidence_order)`。两边必须同一 Run/Workspace。

### 8.5 `research_artifact_claims`

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `artifact_id` | UUID text, NN, FK research_artifacts | 只允许 final_report、verification_result 或 conflict_report |
| `claim_id` | UUID text, NN, FK research_claims | 发布 Claim |
| `claim_order` | integer, NN | Artifact 内顺序 |
| `section_kind` | `fact/conclusion/unresolved/conflict`, NN | closed Artifact section |

主键 `(artifact_id, claim_id)`；`unique(artifact_id, claim_order)`。合法矩阵：

- `final_report + fact/conclusion`：只允许 `verification=supported, conflict=none`；
- `final_report + unresolved`：只允许 `verification=supported, conflict=resolved_unresolved`；
- `verification_result`：只允许 verification 已进入 `supported/unsupported` 终态；
- `conflict_report + conflict`：只允许 `verification=supported, conflict=conflicted`。

`resolved_excluded` 和 `unsupported` Claim 永远不能关联 final_report。Publisher 事务必须 fail closed 校验上述状态、
Evidence relationship、Run/Workspace 和 Artifact bytes 中的 claim marker 集合完全一致。不能只靠 Markdown citation token 猜绑定。

## 9. HumanDecision

### 9.1 `human_decisions`

一行表示一个持久化审批请求及其最终处理，不把审批只留在 Event payload。

| 字段 | 类型/可空 | 提议语义 |
| --- | --- | --- |
| `id` | UUID text, NN, PK | Decision request 身份 |
| `workspace_id` | UUID text, NN | 与 Run 相同 |
| `run_id` | UUID text, NN, FK research_runs | Run |
| `gate_step_id` | UUID text, NN, FK research_steps | waiting gate |
| `decision_type` | Decision type, NN | plan/conflict |
| `request_number` | integer, NN | 同 gate 从 1 递增 |
| `status` | Decision status, NN | 默认 pending |
| `state_version` | bigint, NN, default 1 | CAS |
| `input_artifact_id` | UUID text, NN, FK research_artifacts | 用户看到并裁决的 plan/conflict report |
| `input_artifact_sha256` | char(64), NN | 防止 stale approval |
| `input_snapshot_sha256` | char(64), NN | plan Decision 复制当前 PlanRevision planning hash；conflict Decision 复制 approved ExecutionSnapshot hash |
| `requested_at` | timestamptz, NN | 请求时间 |
| `expires_at` | timestamptz, nullable | 是否启用审批超时待 Owner 决定 |
| `decided_by_user_id` | UUID text, nullable, FK users | pending 时为空 |
| `action` | action enum, nullable | submitted 时必填，且必须匹配 decision_type |
| `comment_text` | text, nullable | 敏感；限制长度；不进入普通日志/Event |
| `decided_at` | timestamptz, nullable | submitted 时必填 |

约束：

- `unique(gate_step_id, request_number)`。
- Decision mutation 的重复提交由 `research_idempotency_records` 关联 `result_resource_id=Decision.id`；Decision 行不重复保存客户端 key。
- pending 才能提交；submitted 内容不可更新。
- plan approval 的 `decided_by_user_id` 必须等于 Run 发起人。Workspace owner 的成本/安全终止走 cancel，
  不能伪造发起人的 plan approval。
- 提交前重新校验 membership、角色、Decision pending、Artifact hash、type-specific input snapshot 和 state_version。

### 9.2 `human_decision_claims`

冲突裁决若针对部分 Claim，使用关系表而不是 JSON ID 列表：

`(decision_id, claim_id, disposition)`，主键 `(decision_id, claim_id)`；`disposition` 只允许
`exclude | leave_unresolved`。是否需要其他 disposition 待 Owner 决定。

## 10. 合法状态迁移

### 10.1 Run

| From | To | 条件 |
| --- | --- | --- |
| create | `planning` | Run、PlanRevision、planning Asset/Prompt/config/budget snapshot、BudgetLedger 与 `run_created` Event 同事务落库 |
| `planning` | `awaiting_plan_approval` | Planner Step succeeded，research_plan Artifact 已校验发布，pending Decision 已创建 |
| `planning` | `cancel_requested/failed` | 用户/owner 取消，或 Planner 超限失败 |
| `awaiting_plan_approval` | `queued` | 发起人提交有效 `approve` |
| `awaiting_plan_approval` | `planning` | 发起人 `request_revision`；旧 Planner/gate/Artifact/Decision 保持终态，按有界 revision number 冻结新的 question/scope/config/version/budget 和 planning Asset 闭集 |
| `awaiting_plan_approval` | `cancel_requested` | 发起人取消或 owner 因成本/安全终止 |
| `queued` | `running` | 第一批可执行 Step 被 lease |
| `queued` | `cancel_requested/failed` | 取消或不可恢复调度错误 |
| `running` | `awaiting_human_decision` | Critic 发布 conflict_report，Decision/gate 同事务进入 waiting |
| `running` | `awaiting_retry` | 一个必需分支耗尽自动 retry，且失败类型允许人工 retry |
| `running` | `cancel_requested` | 接受合法 cancel CAS |
| `running` | `completed` | final_report bytes/hash、Artifact、ArtifactClaim 和完成 Event 同事务通过 |
| `running` | `failed` | 不可恢复错误、预算/策略门失败、无合法最终 Artifact |
| `awaiting_human_decision` | `queued/running` | 有效 conflict Decision；只排队受影响后继节点 |
| `awaiting_human_decision` | `cancel_requested/failed` | cancel 或审批过期策略决定失败 |
| `awaiting_retry` | `queued` | 合法人工 retry，预算未耗尽，只重排失败逻辑 Step |
| `awaiting_retry` | `cancel_requested/failed` | 用户取消或明确结束 |
| `cancel_requested` | `cancelled` | 不再创建新 Step/Attempt，所有在途 Attempt 已终止或 lease 已回收 |

禁止：终态离开；`failed -> queued`；`cancelled -> running`；`completed -> cancel_requested`；
未批准计划直接进入 researcher；没有 final Artifact 进入 completed。

在 plan approval 前，question、scope、Workflow/Prompt、provider/model 或预算变化必须创建同一 Run 的新
append-only PlanRevision，不能原地修改旧 revision。approved ExecutionSnapshot 创建后，任何这些变化都必须
取消当前非终态 Run 并创建新 Run。

### 10.2 Step and Attempt

| From | To | 条件 |
| --- | --- | --- |
| Step `pending` | `queued` | 所有依赖 succeeded，Run 允许执行，预算/取消检查通过 |
| Step `pending` | `skipped/cancelled` | 分支由合法 Decision 排除，或 Run 取消 |
| Step `queued` | `running` | 原子创建下一 Attempt 与 lease |
| Step `running` | `succeeded` | Attempt succeeded，输出 Artifact/Claim/Evidence 已提交 |
| Step `running` | `waiting` | 仅 gate；pending HumanDecision 已提交 |
| Step `running` | `failed` | Attempt failed/timed out/abandoned，错误和 Event 已记录 |
| Step `failed` | `queued` | retry policy/人工 retry 允许，`current_attempt_number < max_attempts_snapshot` 或明确人工扩展规则 |
| Step `queued/running/waiting/failed` | `cancelled` | Run cancel；已 succeeded Step 不改写 |
| Step `waiting` | `succeeded` | 有效 HumanDecision submitted |
| Step `waiting` | `failed/cancelled` | Decision expired 或 Run cancel |

lease 过期时：当前 Attempt `running -> abandoned`，逻辑 Step `running -> failed`，随后按同一 frozen policy
决定 `failed -> queued` 或让 Run 进入 `awaiting_retry/failed`。不得把同一 Attempt 重新标为 running。

### 10.3 HumanDecision

- `pending -> submitted`：合法操作者、action、Artifact hash、Run snapshot、CAS 全部通过。
- `pending -> expired`：仅在批准的 timeout policy 下。
- `pending -> cancelled`：Run cancel。
- `pending -> superseded`：计划修订或新的 conflict report 产生新 request；旧 request 永远不能提交。
- `submitted/expired/cancelled/superseded` 均为终态。

Decision 状态变化、gate Step、Run 状态和对应 Event 必须同一事务提交。

### 10.4 Cancel 与 publish 竞态

- cancel 仅能 CAS 非终态 Run 到 `cancel_requested`。
- ArtifactPublisher 只能在 Run 仍为 `running` 且没有 cancel request 时提交 final publish 事务。
- cancel CAS 先成功：Publisher 必须回滚并清理未发布临时对象。
- publish/completed 事务先成功：后续 cancel 必须返回“已经完成”，不能改写 completed 或删除 Artifact。

## 11. Snapshot、replay 与幂等

### 11.1 Snapshot/replay

- Run 创建及每次 revision 事务冻结一个 PlanRevision：question、planning Asset 闭集及顺序、generation/index、
  proposed Workflow/Prompt/provider/retrieval/budget/policy 和 `planning_snapshot_sha256`。
- 有效 plan approval 事务只复制并批准该 revision 的 exact snapshot，创建唯一 ExecutionSnapshot；审批后不可更新。
- 每个 Research Evidence 捕获时复制已注册 typed locator、ordered regions、Asset 展示和 sourceVersions。
- Asset 后续 reprocess 不改变 PlanRevisionAsset、ExecutionAsset 或 ResearchEvidenceSnapshot。
- Prompt/Workflow retire 不改变历史引用；版本内容不能覆盖。
- Artifact bytes/hash 不可变；报告重放读取 ArtifactClaim -> Claim -> ClaimEvidence -> ResearchEvidenceSnapshot -> typed locator。
- Event replay 以 PostgreSQL `(run_id, seq)` 为唯一事实，不读取内存队列补历史。
- 编排器恢复必须比较 checkpoint、Run state_version、Step/Attempt 终态和 Event seq；不一致时 fail closed，
  不能选“第一个可用状态”。
- 不持久化模型思维链。重放只恢复结构化计划、工具 Evidence ID、验证结果、Decision 和 Artifact。

### 11.2 Idempotency

- 所有公开 mutation：以 `research_idempotency_records` 的 actor/workspace/operation/path/key 唯一；相同 key 但
  不同 canonical input hash 必须冲突，相同 hash 返回冻结结果。
- Step：`run + step_key` 唯一；Planner 重放不得重复 fan-out Step。
- Attempt：`step + attempt_number` 唯一；lease token 只存 hash。
- Event：`run + seq` 和 `run + dedupe_key` 双唯一；状态和 Event 同事务。
- Decision：pending request 只允许一个有效提交；重复 idempotency key 返回原 Decision。
- Evidence：`run + source_fingerprint_sha256` 唯一；同一 Run 不复制等价 locator/excerpt 多次。
- Claim：`run + claim_key` 唯一；retry 必须复用或一致重放 Claim，不产生第二份语义相同记录。
- Artifact：`run + logical_key` 唯一；retry 不覆盖对象、不重复发布。
- Tool：`step + tool_call_key + call_attempt_number` 唯一；成功 search 的 handle 闭集不在重启后替换。
- Provider：每次 send 使用 ProviderCall 行和 BudgetLedger 原子 reserve/reconcile；只保证本地业务账本
  exactly-once，不保证远端计费 exactly-once，`outcome_unknown/usage_final=false` 必须显式记录。

### 11.3 原子边界

以下必须是单个数据库事务；每个包含业务 Event 的事务都同时递增 Run `state_version/next_event_seq`。MinIO bytes
使用“临时上传 -> hash 校验 -> DB publish -> 清理临时对象”的补偿流程：

1. Run + PlanRevision + planning assets/config + BudgetLedger + `run_created` Event。
2. Step lease + Attempt + Run `state_version/next_event_seq` + `step_started` Event。
3. Provider send 前 BudgetLedger reserve + ProviderCall；回执时 ProviderCall + BudgetLedger reconcile。
4. BudgetLedger tool-call reserve/reconcile + ToolCall + batched input/result handles + Evidence snapshot；内部 ToolCall 事务不创建 ResearchEvent。
5. Step success + Claim/Evidence/Artifact metadata + Step/Run counters + Event。
6. Plan approve Decision + exact ExecutionSnapshot/assets/prompts/BudgetLedger + gate Step + Run status + Event。
7. 其他 Decision submit + gate Step + Run status + Event。
8. Final Artifact + ArtifactClaims + Run completed + completion Event。
9. Manual RetryRequest + Step requeue + Run/Step versions + `step_queued` Event；下一 Attempt 由后续 lease 事务创建。

## 12. 权限、敏感数据、删除与恢复

### 12.1 权限和 trust boundary

- 所有读取/写入先验证当前用户 Workspace membership。
- D006 已批准：发起人批准计划、取消自己的运行；Workspace owner 可因成本或安全终止任意运行。
- owner 终止必须记录 actor、reason、时间和输入 state version，不能伪造成发起人的 HumanDecision。
- Agent 只能通过注册的 Evidence search/load tool；不能直连 ORM、MinIO、Shell、任意网络或未批准 provider。
- Asset 内容、Evidence excerpt、用户问题和 provider 输出全部是不可信数据，不能修改权限、budget、tool allowlist 或 Workflow。
- Verifier 输出不是权限来源；HumanDecision 也不能绕过 cross-Workspace 或 typed locator 校验。

### 12.2 敏感字段

敏感 Workspace 内容：

- `question_text`、Prompt template、Artifact bytes、Claim text、Evidence excerpt、Decision comment。
- 这些内容不得进入普通 Event payload、flat log、metric label、trace attribute 或 provider request fingerprint 明文。
- Event/log 只记录 ID、状态、计数、reason code、duration/token/cost。
- credential、session、internal token、provider API key、完整 provider request/response 永不持久化到 Research 表/Artifact。
- PromptVersion 及 internal Artifact 的读取权限不能默认等同普通 Research Artifact。

外部 provider 可接收哪些问题/Evidence、是否允许图片 crop、数据区域、retention/训练条款和用户提示仍待 Owner 批准。

### 12.3 Asset 删除

提议与 Citation/NoteSource 对齐：

- 删除 Asset 时继续清理源与 Representation object bytes、可重建 ContentUnit/Embedding、PDF page 和 Image geometry；
  Asset/Representation 身份及当前合同要求保留的历史行不被 Research 改写，也不删除 ResearchRun/Claim/Artifact。
- ResearchEvidenceSnapshot 的 Asset 标题、excerpt、sourceVersions 和 cloned typed locator 保留。
- `sourceAvailable` 运行时变为 false；Artifact 仍可读，但 Viewer 不尝试打开已删除 bytes，也不按同名 Asset 猜替代源。
- Research Evidence locator/detail/regions 不能被 Asset cleanup 当作可重建 locator 删除。

这是对现有 Asset 删除语义有影响的新增消费者，必须经 Owner 单独批准并加入 delete cleanup 回归。

### 12.4 Run/Artifact 保留和删除

提议默认：

- v1 先支持 `archived_at` 隐藏，不提供单 Run 硬删除，直到 retention/privacy policy 获批。
- Workflow/Prompt version、submitted Decision、final Artifact、Claim/Evidence provenance 与审计 Event 至少保留到 Workspace 生命周期结束。
- `execution_checkpoint/trace_export` 可使用限时 diagnostics retention，但不得先于可恢复 Run 到期。
- cancelled/failed Run 仍保留错误、Decision、Event 和已发布中间 Artifact，不能改写成未发生。

若批准硬删除，顺序必须显式处理依赖环：阻止新执行 -> cancel/reap leases -> 删除 MinIO Research objects并验证 ->
清空 Run/Attempt checkpoint FK -> 删除 ArtifactClaim/ArtifactPrompt/HumanDecisionClaim/ClaimEvidence -> 删除 Decision/Event ->
删除 Artifact -> 删除 Claim -> 记录 locator ID 后删除 ResearchEvidenceSnapshot -> 删除对应 typed details/regions/header ->
删除 ToolCallInputHandle/EvidenceHandle/ToolCall/ProviderCall/BudgetLedger/IdempotencyRecord ->
删除 StepRetryRequest/Attempt/StepDependency/Step -> 删除 ExecutionPromptVersion/ExecutionAsset/ExecutionSnapshot ->
删除 PlanRevisionAsset/PlanRevision -> 删除 Run。
任何对象清理失败必须留下可重试 tombstone；tombstone 本身需要单独批准的字段合同，不能先删 DB 行造成对象泄漏。

### 12.5 备份与恢复

- Research PostgreSQL 表进入现有 custom `pg_dump`；Research Artifact/checkpoint bytes 进入同一停写窗口的 MinIO mirror。
- backup SHA256SUMS 必须是闭集，恢复仍只进入空数据库、空 bucket、空 Redis。
- 恢复后先验证 migration head/readiness，再比较 Run/PlanRevision/ExecutionSnapshot/Step/Attempt/ToolCall/
  ProviderCall/BudgetLedger/Idempotency/Event/Decision/Artifact/Claim/Evidence 行、顺序、Artifact bytes SHA-256、
  typed locator/detail/regions 和 planning/execution snapshot hash。
- 恢复时处于 `running` 的 Attempt 不能由新 Worker 复用旧 token 或直接继续。系统必须等待 lease 到期，或通过经批准的
  restore recovery policy 显式失效旧实例 lease，再把 Attempt 标为 abandoned，并按 frozen retry policy 恢复。
- `awaiting_plan_approval/awaiting_human_decision` 恢复后必须保持等待同一 Decision，不创建新请求或重复审批。
- `completed/failed/cancelled` 恢复后不得产生新 Step、Event 或 Artifact。
- 至少一个正式 oracle 必须覆盖：三条真实重叠 Researcher、一个失败分支 retry、一个 HITL wait、API/Worker 重启、
  销卷恢复、Asset 删除后 Artifact/Evidence 回放和最终零资源残留。

## 13. Quick Answer 不变 oracle

任何 R000/R200 实施都必须证明：

1. Quick Answer 仍是默认；普通问题不会创建 ResearchRun 或隐式升级。
2. 现有 Chat request、`assetScope`、Message scope snapshot、MessageInputEvidence、Citation 和 NoteSource 字段/含义不变。
3. 现有 Chat SSE 仍是 `meta -> delta* -> citations -> done/error`；ResearchEvent 不进入 Chat stream。
4. Chat 历史分支、编辑、失败回放、citation numbering 和 sourceVersions 不变。
5. Citation -> Note 仍只接受真实当前 Workspace Citation；Research Artifact 不自动写 Note。
6. Evidence Viewer 仍只按注册 typed locator 调度；Research 不增加 candidate locator kind。
7. Asset 删除、reindex、reprocess 后现有 Citation/NoteSource 回放语义不变。
8. 新 migration 只增加已批准的 Research 表/约束及必要 locator retention 关系，不给 Quick 表增加必填字段。
9. Quick 与 Deep 的记录、事件、失败和 Artifact 不能互相伪装；Deep final report 不是 Chat assistant message。
10. V3/M403B backup/restore oracle 加入 Research 前后均保持全等，不能用新 oracle 替换旧回归。

## 14. 实施前 Owner 必须裁决

以下全部仍是 open，不得由实现 Agent自行决定：

| ID | Owner 决策 | 本草案推荐默认 |
| --- | --- | --- |
| O001 | 是否批准第 3 节完整 Run/Step/Attempt/Decision 状态与迁移 | 批准前先用状态表做逆向故障评审 |
| O002 | 计划 `request_revision` 是否可在同一 Run 内重跑 Planner | approval 前 question/scope/config/version/budget 变化都创建同一 Run 的新 PlanRevision；approval 后才必须新 Run |
| O003 | 自动 retry 耗尽后是否允许同一 Run 人工 retry，是否可增加 attempt/budget | 允许重试同一失败 Step但不增加 frozen budget；预算耗尽必须新 Run |
| O004 | HITL 等待是否计入 wall-time budget，Decision 是否自动过期 | 人工等待不计 provider wall-time；先不自动过期 |
| O005 | 冲突裁决的操作者和 action；是否允许人工把冲突 claim 认定为事实 | 发起人裁决；只能排除或保留为 unresolved，不能绕过 Verifier |
| O006 | 是否批准新增 ResearchClaim/Evidence/ArtifactClaim 归一化表 | 建议批准，否则无法证明 unsupported claim 未发布 |
| O007 | 是否批准为 Research Evidence 克隆当前 typed EvidenceLocator/detail/regions | 建议批准；禁止 locator JSON 和候选模态字符串 |
| O008 | Asset 删除后 Research Artifact/Evidence 的保留和 Viewer 行为 | 对齐 Citation/NoteSource：快照保留，source unavailable，Viewer 禁用 |
| O009 | Run/Artifact/Event/Prompt/Workflow 的 retention、per-run hard delete 与 Workspace 归档/删除语义 | v1 仅归档；业务 provenance 随 Workspace 生命周期保留；diagnostics 可限时 |
| O010 | 外部 provider 可接收的数据：question、excerpt、图片 crop、区域/retention/训练条款 | 仅发送冻结 scope 内最小必要内容；未批准图片/外网就 fail closed |
| O011 | provider/model 是每 Run 单一配置，还是允许每 node 不同配置 | v1 每 Run 单一 provider/model，降低重放和成本复杂度 |
| O012 | 预算字段、币种、价格快照、成本超限和远端重复计费的产品语义 | 整数微单位；超限 fail closed；明确外部调用可能 at-least-once |
| O013 | 是否批准逐 ProviderCall + BudgetLedger 作为预算、恢复和成本事实源 | 建议批准；StepAttempt aggregate 只做派生展示，不能支撑 outcome-unknown 与原子 reserve/reconcile |
| O014 | Event type/payload allowlist、Research SSE 权限与 Event retention | 批准第 7 节最小 ID/status/count payload；与 Chat SSE 完全分离 |
| O015 | Workflow/Prompt 谁可发布/retire，普通 member 是否可读取内部 Prompt/trace | 仅平台管理员或受控 deployment release 管理；Workspace owner 不自动获得全局版本发布权；普通 member 不读取 Prompt/internal Artifact |
| O016 | Deep Run 是否必须关联 Chat thread，thread archive 后如何显示 | origin thread 可空、只做导航；Deep 不是 ChatMessage |
| O017 | hard delete 时 cloned locator 与 MinIO object 的清理顺序/tombstone 机制 | 显式两阶段清理，不用无边界 cascade |
| O018 | V4 migration downgrade：可逆删除空表，还是有数据后只允许备份恢复 | migration 未承载数据时可 downgrade；有数据后 restore-first并显式阻止破坏性 downgrade |
| O019 | 备份中非终态 Run 的恢复策略、旧实例 lease 失效机制和 checkpoint schema | 新 Worker 禁止复用旧 token；决定等待 expiry 还是用 restore epoch 显式失效；Postgres 账本优先；checkpoint 只存结构化 ID/hash |
| O020 | error_message、Decision comment、Artifact/trace 的脱敏、加密和访问审计 | 不进日志/metric；MinIO/DB 加密与审计策略必须在 R000 安全评审关闭 |
| O021 | PlanRevision 与 ExecutionSnapshot 的冻结边界 | Create/每次 revision 冻结该 PlanRevision 的 planning snapshot；approval 校验并精确复制该 revision，创建唯一 ExecutionSnapshot，不解析 latest 配置或 Asset 版本 |

## 15. 本草案明确不授权

- 不授权创建任何表、migration、ORM、schema、endpoint、SSE、Worker DAG 或 UI。
- 不授权修改 Asset、Chat、Citation、NoteSource、EvidenceLocator、Note 保存或删除语义。
- 不授权 LangGraph checkpoint 成为业务事实源。
- 不授权任意网络、插件、Shell、ORM/MinIO 直连、动态代码或自动长期记忆。
- 不授权新增 locator kind、复制候选模态命名、保存任意 locator JSON 或任意 Agent payload。
- 不授权保存思维链、provider credential 或完整 provider raw request/response。
- 不授权自动写 Note、自动修改 Workspace 事实、Quick 自动升级或 Deep 自动降级。

下一步只能是：把本草案与 `api-event-tool-contract-draft.md` 作为同一 R000 合同包评审，关闭合并后的 Owner
决策，完成权限/安全/删除/恢复反向评审并形成独立 approval record。两份现有草案均保持 UNAPPROVED；只有
Owner 明确批准同一版本后，才能另行编写 migration contract 与实施任务。
