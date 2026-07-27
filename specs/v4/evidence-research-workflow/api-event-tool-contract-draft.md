# V4 Research API、事件与工具合同草案

## 0. 状态、范围与批准边界

- 状态：`draft_unapproved`。
- 建立日期：2026-07-25。
- 本文是 R000 评审输入，不是实现合同，不授权新增路由、表、字段、SSE、Worker 行为、provider 调用或对象存储内容。
- Owner 已批准 `requirements-discovery.md` 的 D001-D007 产品方向；该批准不覆盖本文的 API、事件、工具、权限、预算、保留或删除提案。
- 本文所有使用“必须”的表述，只描述“若本草案获批后的合同要求”。在 R000 approval record 明确引用获批版本前，全部内容保持未批准。
- 当前 Git `HEAD=9aa3bf27ec97a9c0da14cf9e57db38ca0e5a5c3c`，但工作树不是稳定恢复点；该 SHA 不能单独充当 R000 baseline。
- 本文只新增合同草案，不修改现有 Quick Chat、Citation、NoteSource、Asset、EvidenceLocator 或保存语义。

### 0.1 现有实现 oracle

本文基于以下已存在行为，而不是另造认证或 Chat 协议：

1. 浏览器只把签名 session cookie 交给同源 Next.js BFF；BFF 校验 session 后向 API 注入 `x-user-id` 与 `x-ai-pdf-internal-token`。浏览器不得直接提供或覆盖这两个 header。
2. API 只接受有效 internal token 与现有用户。Workspace 可访问性由 `workspace_memberships` 判定；不可访问或不存在的 Workspace 对资源查询统一表现为 `404`，避免枚举。
3. 当前 Workspace role 只有 `owner/member`；资源 creator 是独立于 role 的授权维度。
4. 当前 DTO 使用 camelCase JSON、UUID string、UTC ISO-8601 时间和 opaque cursor。
5. 当前 Quick Chat 使用 `POST /v1/workspaces/{workspaceId}/chat/stream`，事件为 `meta/delta/citations/done/error`，没有持久化 Research `seq` 或 `Last-Event-ID` 重放。

### 0.2 跨文档一致性门

`data-state-contract-draft.md` 是数据实体、状态机和持久化事件 vocabulary 的 canonical draft；本文只能定义其 API/BFF/SSE/tool projection，不能另造同义 enum。两份文件仍都未批准。

| 合同面 | Canonical source | 本文绑定 | 不一致处理 |
| --- | --- | --- | --- |
| Run/Step/Attempt 状态 | data draft 3.2-3.5、10.1-10.2 | 第 2、3、4 节 | 阻断 R000，不加转换别名 |
| HumanDecision type/action/status | data draft 3.6、9、10.3 | 第 2.3、4 节 | 阻断 R000，不猜旧 action |
| Artifact kind/visibility/provenance | data draft 3.7、8 | 第 5 节 | 阻断发布，不按 MIME 猜 kind |
| ResearchEvent type/payload/seq | data draft 7 | 第 8 节 | 阻断 SSE，不做双事件命名 |
| planning/research freeze timing | `requirements-discovery.md` D004 + 两份 R000 draft | 第 2.2、3.1、4.1 节 | create 冻结 planning execution；approve 冻结 research execution/scope |
| Evaluation | `spec.md` R700/R100 评测边界 | 第 6 节 | 独立 API surface，不加入核心 DAG Step kind |
| Quick invariants | 当前 code/API contract + data draft 13 | 第 12 节 | old/new oracle 不通过则禁止实现 |

最终 approval record 必须引用两份文件的同一 commit，并证明上述 enum/action/event allowlist 完全一致。

## 1. 合同约定

### 1.1 路径与 BFF

- API 前缀：`/v1/workspaces/{workspaceId}`。
- Research API 前缀：`/v1/workspaces/{workspaceId}/research-runs`。
- Web BFF 使用同路径语义的 `/api/workspaces/{workspaceId}/research-runs`。
- BFF 必须使用 `cache: no-store`，原样转发 API 状态码和 Research error envelope。
- Research SSE BFF 只转发 `Accept`、`Last-Event-ID` 及必要的响应流 header；不得转发浏览器提供的内部认证 header。
- 所有资源查询必须同时约束 `workspaceId` 与资源 ID；不能只凭全局 UUID 查询后再做展示层过滤。

### 1.2 JSON、ID 与校验

- JSON 字段使用 camelCase。
- `*Id` 是非空 UUID string；客户端不得从名称、顺序或“第一项”推断 ID。
- 时间是带时区的 UTC ISO-8601 string，例如 `2026-07-25T00:00:00Z`。
- SHA-256 是 64 位 lowercase hex string。
- 金额若获批，使用 Run 创建时冻结的单一 ISO 4217 `currency` + 整数 `amountMicros`，`1 currency unit = 1_000_000 micros`；不使用 JSON float，不跨币种求和。推荐 USD 只记录在审批包，最终币种、价格与计费基准仍是 Owner 待决项 `API-O004`。
- Request DTO 必须 `extra=forbid`；未知字段、未知 discriminator、重复 ID、非有限数和越界数值返回 `422`。
- Response 与 SSE payload 不得包含 provider secret、内部 URL、MinIO object key、数据库主键以外的内部关系、原始系统 prompt 或模型思维链。

### 1.3 通用 error envelope

Research endpoint 提议使用机器可读错误，不改变现有 endpoint 的错误形状：

```ts
type ResearchErrorResponse = {
  error: {
    code: string;                 // allowlist code
    message: string;              // 安全、面向用户，不含 prompt/asset 正文/secret
    requestId: string;
    retryable: boolean;
    details?: {
      field?: string;
      expectedVersion?: number;
      currentVersion?: number;
      retryAfterSeconds?: number;
    };
  };
};
```

通用映射：

| HTTP | code | 语义 |
| --- | --- | --- |
| 400 | `idempotency_key_required` / `invalid_event_cursor` | header 或 cursor 语法错误 |
| 401 | `auth_required` | BFF session 或 API internal/user 身份无效 |
| 403 | `research_permission_denied` | Workspace 可见，但 action 不允许 |
| 404 | `workspace_not_found` / `research_run_not_found` / `research_resource_not_found` | 不泄露其他 Workspace 资源 |
| 409 | `research_state_conflict` / `stale_state_version` / `stale_plan_snapshot` / `idempotency_key_reused` | 状态、快照、乐观锁或幂等冲突 |
| 410 | `research_event_history_unavailable` / `research_artifact_unavailable` | 已知资源不再可重放或读取 |
| 422 | `invalid_research_request` / `invalid_asset_scope` / `invalid_decision` / `research_execution_policy_unavailable` | 字段或已冻结 policy/profile 当前不可执行 |
| 429 | `research_concurrency_limit` / `research_budget_limit` | 工作区并发或预算策略拒绝 |
| 503 | `research_provider_not_configured` / `research_temporarily_unavailable` | 运行配置尚不可用 |

异步 provider、step 或恢复失败不把已经接受的 create/decision/retry HTTP 请求改写成同步 `5xx`；失败必须先持久化为 Run/Step/Event 事实，再由 read API 和 Research SSE 暴露安全错误码。

### 1.4 幂等与乐观并发

以下 mutation 必须携带 `Idempotency-Key`：create、cancel、plan-decision、conflict-decision、retry。值为 16-128 个可打印 ASCII 字符，不得包含用户正文或 secret。

提议语义：

1. 幂等作用域为 `(authenticatedUserId, workspaceId, operation, canonicalPath, Idempotency-Key)`；operation 只允许 `create_run/cancel_run/submit_plan_decision/submit_conflict_decision/retry_step`。
2. 服务端必须在 `research_idempotency_records` 保存 canonical request body hash、`in_progress/completed/failed` 状态、首次状态码、获批 response allowlist 与目标资源 ID；不得只靠进程缓存。
3. 同 key + 同 body 重放返回首次语义结果，并设置 `Idempotency-Replayed: true`；不得重复 Run、Decision、Step attempt、Event 或 Artifact。
4. 同 key + 不同 body 返回 `409 idempotency_key_reused`。
5. `expectedStateVersion` 提供 Run 乐观并发。版本不符返回 `409 stale_state_version`，不得执行部分副作用。
6. 幂等记录保留时长、Run 删除后的处理和是否允许客户端生成 UUID，均为 Owner 待决项 `API-O006`。

Endpoint 到 operation 的固定映射：create=`create_run`、cancel=`cancel_run`、plan decision=`submit_plan_decision`、conflict decision=`submit_conflict_decision`、retry=`retry_step`。canonical path 不含 query/body/secret。

## 2. 字段级公共 DTO

以下类型均为提案，尚未批准。

```ts
type ResearchRunStatus =
  | "planning"
  | "awaiting_plan_approval"
  | "queued"
  | "running"
  | "awaiting_human_decision"
  | "awaiting_retry"
  | "cancel_requested"
  | "completed"
  | "failed"
  | "cancelled";

type ResearchStepKind =
  | "planner"
  | "plan_approval_gate"
  | "researcher"
  | "join"
  | "verifier"
  | "critic"
  | "conflict_decision_gate"
  | "synthesizer"
  | "artifact_publisher";

type ResearchStepStatus =
  | "pending"
  | "queued"
  | "running"
  | "waiting"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "skipped";

type AssetScopeRequest =
  | { mode: "all_ready" }
  | { mode: "selected"; assetIds: string[] }; // 1..100 unique IDs, proposed limit

type FrozenAsset = {
  assetId: string;
  assetKind: string;
  assetTitle: string;
  processingGeneration: number;  // integer >= 1
  indexVersion: number;          // integer >= 1
};

type FrozenAssetScope = {
  frozenAt: string;
  assets: FrozenAsset[];         // stable order, unique assetId
};

type SafeFailure = {
  code: string;
  message: string;
  retryable: boolean;
  failedAt: string;
};
```

`all_ready` 在 Create 和每次 accepted revision 建立时解析为该 PlanRevision 的 planning-time 闭集。计划批准
不重新解析 `all_ready`：只逐项验证闭集内 Asset 仍 ready/not-deleted 且 generation/index 未漂移，再精确复制。
批准期间新增的 ready Asset 被忽略；只有新 revision 才能纳入。批准后工具只能读取 approved execution scope；
源删除后的可读性仍由 `API-O005` 决定。

### 2.1 Plan DTO

```ts
type ResearchPlanSubproblem = {
  id: string;
  order: number;                 // integer >= 0, unique per plan
  question: string;              // 1..4000 chars
  assetIds: string[];            // 0..100 unique；空数组明确表示整个 requested scope
  expectedEvidence: string[];    // 0..20 short labels, not locator/schema names
};

type ResearchPlan = {
  version: number;               // integer >= 1, immutable version
  status: "proposed" | "approved" | "superseded";
  inputSnapshot: PlanningInputSnapshot;
  summary: string;               // 1..4000 chars
  subproblems: ResearchPlanSubproblem[]; // 1..16, proposed limit
  knownGaps: string[];           // 0..20, each <= 1000 chars
  estimatedProviderCalls: number;
  estimatedInputTokens: number | null;
  estimatedOutputTokens: number | null;
  estimatedCost: MoneyMicrounits | null;
  planningUsage: BudgetUsage;
  createdAt: string;
  approvedAt: string | null;
};
```

`expectedEvidence` 只是用户可读标签，不能直接创建 locator kind、数据库字段或工具权限。Plan 不包含 prompt、模型思维链、任意 tool name 或 URL。

`ResearchPlan.status/approvedAt` 是只读 projection，不写回 immutable PlanRevision：当前 revision 且尚无
ExecutionSnapshot 时为 `proposed`；ExecutionSnapshot 的 `inputVersion` 等于该 plan `version` 时为 `approved`，
`approvedAt=ExecutionSnapshot.createdAt`；更早且未获批准的 revision 为 `superseded`。不得增加可变 PlanRevision
status 字段或按 Artifact 顺序猜状态。

### 2.2 Provider 与预算 DTO

```ts
type MoneyMicrounits = {
  currency: string;              // ISO 4217 uppercase code
  amountMicros: number;          // integer >= 0
};

type ProviderSnapshot = {
  generationProvider: string;
  generationModel: string;
  embeddingProvider: string;
  embeddingModel: string;
  embeddingVersion: string;
  retrievalStrategy: string;
  retrievalTopK: number;          // integer >= 1
  providerConfigFingerprint: string; // non-secret SHA-256
  pricingVersion: string | null;
  dataBoundaryPolicyVersion: string; // 只能引用获批 policy
};

type BudgetLimits = {
  maxProviderCalls: number;      // integer >= 1
  maxToolCalls: number;          // integer >= 1; each persisted ToolCall attempt counts
  maxInputTokens: number;        // integer >= 1
  maxOutputTokens: number;       // integer >= 1
  maxCost: MoneyMicrounits;
  maxParallelResearchers: number;// integer >= 1
  runTimeoutSeconds: number;     // integer >= 1
  stepTimeoutSeconds: number;    // integer >= 1
  providerTimeoutSeconds: number;// integer >= 1
  maxAttemptsPerStep: number;    // integer >= 1
};

type PlanningBudgetLimits = {
  maxProviderCalls: number;      // integer >= 1
  maxInputTokens: number;        // integer >= 1
  maxOutputTokens: number;       // integer >= 1
  maxCost: MoneyMicrounits;
  plannerTimeoutSeconds: number; // integer >= 1
  providerTimeoutSeconds: number;// integer >= 1
  maxPlannerAttempts: number;    // integer >= 1
};

type BudgetUsage = {
  providerCalls: number;
  toolCalls: number;              // persisted ToolCall attempt rows
  inputTokens: number;
  outputTokens: number;
  cost: MoneyMicrounits;
  usageFinal: boolean;
  measuredAt: string;
};

type PromptVersionRef = {
  nodeKey: string;
  promptVersionId: string;
};

type ExecutionConfigSnapshot = {
  workflowVersionId: string;
  promptVersions: PromptVersionRef[]; // stable nodeKey order
  provider: ProviderSnapshot;
  budgetPolicyVersion: string;
  retryPolicyVersion: string;
  limits: BudgetLimits;
};

type PlanningExecutionSnapshot = {
  workflowVersionId: string;
  plannerPromptVersionId: string;
  provider: ProviderSnapshot;
  budgetPolicyVersion: string;
  retryPolicyVersion: string;
  limits: PlanningBudgetLimits;
};

type PlanningInputSnapshot = {
  revisionNumber: number;        // integer >= 1
  question: string;
  requestedAssetScope: AssetScopeRequest;
  planningAssetScope: FrozenAssetScope; // Planner 实际可见的 generation/index；不是 execution truth
  planningExecution: PlanningExecutionSnapshot;
  proposedResearchExecution: ExecutionConfigSnapshot;
  snapshotSha256: string;        // canonical question/scope/assets/planning/proposed-research hash
  frozenAt: string;
};

type ApprovedResearchExecutionSnapshot = {
  id: string;
  inputVersion: number;          // approved Plan revision number
  approvalDecisionId: string;
  approvedPlanArtifactId: string;
  approvedPlanArtifactSha256: string;
  question: string;
  frozenAssetScope: FrozenAssetScope;
  execution: ExecutionConfigSnapshot;
  snapshotSha256: string;
  createdAt: string;
};
```

客户端不得提交 provider/model/base URL/API key，也不引用尚未批准的 profile 实体。V1 proposal 由服务端从部署期 approved defaults 解析 Provider/Budget snapshot；没有唯一、有效、带 data-boundary policy 的默认配置时 Create fail closed。币种、默认上限和外部数据边界仍由 `API-O003/API-O004` 决定。

Planner 在人工批准前已经需要 provider，因此存在两个不可混淆的 execution snapshot：

1. 每个 Plan revision 的 `inputSnapshot.planningExecution` 在 Create 或 revision 接受时冻结，只允许该 revision 的 Planner 使用；其 prompt/provider/budget/usage 必须可审计。
2. `researchExecution` 在 Plan approve 时冻结，只允许 Researcher 及其后续节点使用；不得用 planning snapshot 暗示整次 Research 已获批。
3. v1 的 `planningExecution` 与 `proposedResearchExecution` 必须引用同一 WorkflowVersion 和完全相同的
   ProviderSnapshot；它们只在 Prompt binding、budget/retry/timeout 和 usage 账本上分离。计划估算不等于
   research budget 已授权，也不能在 approval 时换 provider/config。

### 2.3 Step、Conflict 与 Decision DTO

```ts
type ResearchStep = {
  id: string;
  runId: string;
  kind: ResearchStepKind;
  key: string;                   // versioned DAG 内稳定 key
  branchKey: string | null;       // opaque non-semantic identifier
  status: ResearchStepStatus;
  stateVersion: number;
  currentAttemptNumber: number;  // integer >= 0; pending/queued 可为 0
  maxAttempts: number;           // frozen integer >= 1
  dependsOnStepIds: string[];
  evidenceCount: number;
  providerCalls: number;          // last committed business Event boundary
  toolCalls: number;              // last committed business Event boundary
  startedAt: string | null;
  finishedAt: string | null;
  failure: SafeFailure | null;
};

type HumanDecision = {
  id: string;
  runId: string;
  gateStepId: string;
  type: "plan_approval" | "conflict_resolution";
  status: "pending" | "submitted" | "expired" | "cancelled" | "superseded";
  requestNumber: number;
  stateVersion: number;
  inputArtifactId: string;
  inputArtifactSha256: string;
  inputSnapshotSha256: string;
  requestedAt: string;
  expiresAt: string | null;
  decidedByUserId: string | null;
  action:
    | "approve"
    | "request_revision"
    | "cancel_run"
    | "exclude_conflicted_claims"
    | "keep_as_unresolved"
    | null;
  comment: string | null;
  decidedAt: string | null;
};
```

谁能裁决 Conflict、是否需要更多 action，以及 pending Decision 是否过期均未获批，见 `API-O002/API-O004`。Conflict 的用户可见正文和 claims 来自 `inputArtifactId` 指向的 `conflict_report`，不在 Event/HumanDecision 中复制。HumanDecision 不能把 unsupported claim 改成 supported；`keep_as_unresolved` 只能进入未解决问题/证据缺口，不能进入 final report 的事实结论。在这些决定关闭前，Conflict decision 不能成为实现输入。

### 2.4 ResearchRun DTO

```ts
type ResearchRunSummary = {
  id: string;
  workspaceId: string;
  createdByUserId: string;
  question: string;
  status: ResearchRunStatus;
  stateVersion: number;          // every Event-producing business mutation increments
  requestedAssetScope: AssetScopeRequest;
  frozenAssetCount: number;
  costCurrency: string;          // Run-level frozen ISO 4217 currency
  currentPlanRevisionNumber: number | null;
  currentEventSeq: number;       // integer >= 0
  estimatedCost: MoneyMicrounits | null;
  consumedCost: MoneyMicrounits;
  createdAt: string;
  updatedAt: string;
  finishedAt: string | null;     // completed/failed/cancelled terminal time
};

type ResearchRunDetail = ResearchRunSummary & {
  frozenAssetScope: FrozenAssetScope | null;
  plan: ResearchPlan | null;
  researchExecution: ApprovedResearchExecutionSnapshot | null;
  planningUsage: BudgetUsage;
  researchUsage: BudgetUsage | null;
  steps: ResearchStep[];
  pendingDecisions: HumanDecision[];
  submittedDecisions: HumanDecision[];
  artifactCount: number;
  failure: SafeFailure | null;
  startedAt: string | null;
  cancelRequestedAt: string | null;
  cancelledAt: string | null;
};
```

List 只返回 `ResearchRunSummary`；read 才返回当前步骤、决策和执行快照。任何字段都不能通过“第一条 step/artifact”猜当前状态。

## 3. Run API

### 3.1 Create

`POST /v1/workspaces/{workspaceId}/research-runs`

```ts
type CreateResearchRunRequest = {
  question: string;              // trimmed, 1..12000 chars
  assetScope: AssetScopeRequest;
};

type CreateResearchRunResponse = {
  run: ResearchRunDetail;        // initial status = planning
};
```

- 需要 `Idempotency-Key`。
- 首次成功提议返回 `201` 与 `Location`；重放返回同一 Run。
- Create 只建立 Run，并原子冻结 revision 1 的 `PlanningInputSnapshot`（question、requested scope、稳定 Asset 顺序及 generation/index、受限 planning execution、proposed research execution、canonical hash），再排队生成计划；不批准计划、不创建 approved `researchExecution`、不开始 Researcher fan-out。
- `selected` 中每个 Asset 必须属于当前 Workspace、未删除且 ready；`all_ready` 必须在 Create 时解析为至少一个有稳定顺序的 ready Asset snapshot，否则 `422 invalid_asset_scope`。Create 后新进入 ready 或新 generation 的 Asset 不得静默加入该 revision。
- 是否允许同一用户/Workspace 同时拥有多个非终态 Run 为 `API-O009`。

### 3.2 List

`GET /v1/workspaces/{workspaceId}/research-runs?status={status}&createdBy=me|all&cursor={cursor}&limit={1..50}`

```ts
type ResearchRunListResponse = {
  items: ResearchRunSummary[];
  nextCursor: string | null;
};
```

- cursor 必须 opaque，排序提议为 `createdAt DESC, id DESC`。
- 是否允许普通 member 查看同 Workspace 其他人的 Run 为 `API-O001`；未决定前不得把 `createdBy=all` 实现为默认开放。

### 3.3 Read

`GET /v1/workspaces/{workspaceId}/research-runs/{runId}`

```ts
type ResearchRunDetailResponse = {
  run: ResearchRunDetail;
};
```

- Response header 提议返回 `ETag: "run-{runId}-v{stateVersion}"`。
- 其他 Workspace 的 runId 必须返回 `404 research_run_not_found`。

### 3.4 Cancel

`POST /v1/workspaces/{workspaceId}/research-runs/{runId}/cancel`

```ts
type CancelResearchRunRequest = {
  expectedStateVersion: number;
  reasonCode: "user_requested" | "cost" | "security" | "other";
};

type CancelResearchRunResponse = {
  run: ResearchRunDetail;
};
```

- 需要 `Idempotency-Key`。
- 首次接受提议返回 `202`；状态进入 `cancel_requested`，Worker 停止领取新工作。若外部 provider 不支持硬取消，当前调用可运行到 cancel/timeout 边界，但其结果不得推进状态、发布 Artifact 或启动后续调用；所有在途 Attempt 终止或 lease 回收后才能进入 `cancelled`。
- creator 可取消自己的非终态 Run；Workspace owner 可因 `cost/security` 终止任意 Run，沿用 D006。其他 member 返回 `403`。
- terminal Run 再次 cancel：同 key 重放首次结果；新 key 返回 `409 research_state_conflict`。
- Cancel 不是 delete，不删除事件、决策、已发布 Artifact 或审计记录。

## 4. Human Decision 与 Retry API

### 4.1 Plan decision

`POST /v1/workspaces/{workspaceId}/research-runs/{runId}/plan-decisions/{decisionId}`

```ts
type PlanRevisionInput = {
  question: string;               // trimmed, 1..12000 chars
  assetScope: AssetScopeRequest;
};

type PlanDecisionRequest = {
  expectedStateVersion: number;
  expectedDecisionStateVersion: number;
  inputArtifactSha256: string;
  inputSnapshotSha256: string;
  action: "approve" | "request_revision" | "cancel_run";
  comment: string | null;        // request_revision 时 required, 1..4000
  revision: PlanRevisionInput | null; // request_revision 时 required；其他 action 必须为 null
};

type PlanDecisionResponse = {
  decision: HumanDecision;
  run: ResearchRunDetail;
};
```

- 需要 `Idempotency-Key`。
- 只允许 Run creator；owner 若不是 creator 也不能替代批准计划或提交 revision。
- `approve` 必须验证 Plan artifact、`inputSnapshotSha256`、frozen Asset generation/index、Workflow/Prompt complete binding、provider/retrieval profile、pricing/data-boundary policy 和 budget/retry/timeout policy 仍可用且合规；成功后只精确复制 `inputSnapshot.proposedResearchExecution` 与 planning Asset 闭集，创建 immutable `researchExecution` 并进入 `queued`。不得重新解析 `all_ready`、抓取“当前最新” generation/index/config 或直接把可变指针当 execution truth。任一已冻结输入漂移返回 `409 stale_plan_snapshot`，policy/profile 不再允许则返回 `422 research_execution_policy_unavailable`，均不得产生部分副作用。
- `request_revision` 必须先把当前 pending Decision 提交为 terminal `submitted/action=request_revision`，再以请求中的 question/requested scope 和当前获批 server-side config/version/budget defaults 创建同一 Run 的新 append-only PlanRevision。旧 Plan Artifact 可被新 Plan Artifact 显式 supersede，但已 submitted Decision 不得改写成 superseded；任何旧 hash 都不能用于批准新 revision。最大修订次数和 planning 预算值为 `API-O008`。
- `cancel_run` 提交 Plan Decision 并进入 `cancel_requested`；其他阶段取消继续使用独立 cancel endpoint。
- Plan approve 后 question、Asset scope、Workflow/Prompt、provider/model 或 budget 变化必须取消当前 Run 并 Create 新 Run；不能再 request revision。

### 4.2 Conflict decision

`POST /v1/workspaces/{workspaceId}/research-runs/{runId}/conflict-decisions/{decisionId}`

```ts
type ConflictDecisionRequest = {
  expectedStateVersion: number;
  expectedDecisionStateVersion: number;
  inputArtifactSha256: string;
  inputSnapshotSha256: string;
  action:
    | "exclude_conflicted_claims"
    | "keep_as_unresolved"
    | "cancel_run";
  comment: string | null;        // <= 4000 chars
};

type ConflictDecisionResponse = {
  decision: HumanDecision;
  run: ResearchRunDetail;
};
```

- 需要 `Idempotency-Key`。
- `action` 必须匹配 pending `decisionId` 的 canonical `conflict_resolution` action allowlist；客户端不能提交自由状态、claim 或 Evidence ID 覆盖。
- 谁可以裁决 conflict、owner 是否能代裁决、是否保留全部三个 action 是 Owner 待决项 `API-O002`。未批准前本 endpoint 是 blocked draft。
- 重复 Decision、过期 `expectedDecisionStateVersion`、input Artifact hash 不符或 Run 非等待状态返回 `409`，不得覆盖原 Decision。

### 4.3 Retry failed branch

`POST /v1/workspaces/{workspaceId}/research-runs/{runId}/steps/{stepId}/retry`

```ts
type RetryResearchStepRequest = {
  expectedStateVersion: number;
  expectedStepStateVersion: number;
  failedAttempt: number;
};

type RetryResearchStepResponse = {
  run: ResearchRunDetail;
  step: ResearchStep;            // same logical Step requeued；lease 前 currentAttemptNumber 不变
};
```

- 需要 `Idempotency-Key`，首次接受提议返回 `202`。
- 只允许 Run=`awaiting_retry` 且 Step=`failed`、`expectedStepStateVersion` 和 `failedAttempt` 均匹配的 branch；不得重跑已成功依赖、重置整个 Run 或重复发布 Artifact。
- 新 attempt 必须遵守冻结 retry policy 和剩余预算。预算不足时 fail closed，不隐式提高上限或降级 Quick。
- 手动 retry 权限与是否允许对 provider-policy/security failure 重试属于 `API-O002/API-O004`。

## 5. Artifact API 与 provenance

### 5.1 DTO

```ts
type ResearchArtifactKind =
  | "research_plan"
  | "evidence_bundle"
  | "verification_result"
  | "conflict_report"
  | "execution_checkpoint"
  | "final_report"
  | "trace_export";

type UserVisibleResearchArtifactKind = Exclude<
  ResearchArtifactKind,
  "verification_result" | "execution_checkpoint"
>;

type ArtifactEvidenceRef = {
  evidenceLocatorId: string;
  assetId: string;
  assetKind: string;
  assetTitle: string;
  sourceAvailable: boolean;
  excerpt: string;
  locator: EvidenceLocatorDto;   // 复用已批准 locator union，不新增 kind
  sourceVersions: {
    parserVersion: string;
    processingGeneration: number;
    representationId: string;
    indexVersion: number;
  };
};

type ArtifactClaimEvidenceRef = {
  evidenceLocatorId: string;
  relationship: "supports" | "contradicts";
  order: number;
};

type ArtifactClaim = {
  id: string;
  text: string;
  verificationStatus: "supported" | "unsupported";
  conflictStatus: "none" | "conflicted" | "resolved_excluded" | "resolved_unresolved";
  sectionKind: "fact" | "conclusion" | "unresolved" | "conflict";
  evidence: ArtifactClaimEvidenceRef[]; // stable order
};

type ResearchArtifactSummary = {
  id: string;
  runId: string;
  stepId: string;
  kind: UserVisibleResearchArtifactKind;
  visibility: "user";
  logicalKey: string;
  schemaVersion: string;
  supersedesArtifactId: string | null;
  mediaType: "text/markdown" | "application/json";
  byteSize: number;
  sha256: string;
  evidenceCount: number;
  retentionClass: "workspace_lifetime" | "time_limited_diagnostics";
  expiresAt: string | null;
  createdAt: string;
};

type ResearchArtifactDetail = ResearchArtifactSummary & {
  workflowVersionId: string;
  promptVersions: PromptVersionRef[];
  directPromptVersionId: string | null;
  provider: ProviderSnapshot | null;
  claims: ArtifactClaim[];
  evidence: ArtifactEvidenceRef[];
};
```

Artifact 行只代表 bytes/hash 已校验并发布的 immutable 对象；未发布临时对象和 withheld 半成品不进入公开 DTO。
公开 Artifact DTO 是 data draft kind 的显式 `visibility=user` 子集，永不返回 `verification_result/execution_checkpoint`；
`final_report` 固定为 user，`trace_export` 必须先脱敏且不得含思维链。`final_report` 的 fact/conclusion 只允许
`supported + conflict=none`，unresolved 只允许 `supported + resolved_unresolved`；`unsupported/conflicted/
resolved_excluded` 不能进入最终事实/结论。`conflict_report` 的 claims 必须来自 normalized ArtifactClaim relation。

### 5.2 Endpoints

| Method | Path | Response |
| --- | --- | --- |
| GET | `/research-runs/{runId}/artifacts` | `{ items: ResearchArtifactSummary[] }`；普通产品调用只返回 `visibility=user` |
| GET | `/research-runs/{runId}/artifacts/{artifactId}` | `{ artifact: ResearchArtifactDetail }` |
| GET | `/research-runs/{runId}/artifacts/{artifactId}/content` | immutable bytes with exact `Content-Type`, `Content-Length`, `ETag=sha256` |

- API/BFF 通过权限保护的流返回 Artifact，不暴露 MinIO URL/object key。
- content hash、metadata 和 provenance 必须在发布前一致；不一致返回 `409/500` 并阻止发布。
- `sourceAvailable` 是读取时按当前 Asset 可用性计算的 response projection，不进入 immutable Artifact bytes/hash；它变化时不得改写 locator、sourceVersions、excerpt 或 claim snapshot。
- Internal Artifact 的平台审阅权限、`trace_export` 是否对用户开放、是否允许显式 delete 仍由 `API-O005/API-O007` 决定。

## 6. Deferred R700 Evaluation API shape

当前 data draft 没有 ResearchEvaluation 持久化实体，因此本节仅保留 R700/R100 的 field-level discovery shape，不属于 R000/R200 可实现 API。它不能注册路由、创建 Evaluation 状态或让浏览器触发模型评测；只有未来独立 Evaluation 数据合同获批后，才能决定是否采用下列 DTO。

```ts
type EvaluationStatus = "not_evaluable" | "queued" | "running" | "completed" | "failed";

type RatioMetric = {
  value: number | null;          // 0..1; null means not evaluable
  sampleCount: number;
  notEvaluableReason: string | null;
};

type ResearchEvaluation = {
  id: string;
  runId: string;
  status: EvaluationStatus;
  suiteId: string;
  caseId: string;
  fixtureManifestSha256: string;
  evaluatorVersion: string;
  baselineRunId: string | null;
  claimSupportRate: RatioMetric;
  evidenceRecall: RatioMetric;
  evidencePrecision: RatioMetric;
  locatorAccuracy: RatioMetric;
  conflictDetectionRate: RatioMetric;
  refusalCorrectness: RatioMetric;
  wallTimeMs: number | null;
  providerCalls: number;
  inputTokens: number;
  outputTokens: number;
  cost: MoneyMicrounits;
  engineeringGate: "not_evaluable" | "pass" | "fail";
  modelQualityGate: "not_evaluable" | "pass" | "fail";
  userValueGate: "not_evaluable" | "pass" | "fail";
  createdAt: string;
  completedAt: string | null;
  failure: SafeFailure | null;
};

type ResearchEvaluationResponse = {
  evaluation: ResearchEvaluation;
};
```

候选路径（deferred）：`GET /v1/workspaces/{workspaceId}/research-runs/{runId}/evaluation`

- M404 未完成时，`userValueGate` 必须保持 `not_evaluable`；工程或 scripted provider 结果不能改变它。
- scripted provider 只可证明编排；其结果不得使 `modelQualityGate=pass`。
- 在独立 R700 persistence/artifact contract 关闭前，该候选路径必须返回未注册（不存在），不能用 Run、Artifact 或临时内存状态拼装伪 Evaluation。
- Evaluation 是自动附着 Run、由评测 Artifact 投影，还是由内部审批任务创建，以及 Dashboard 的跨 Run list API，全部推迟到独立 R700 合同。

## 7. 权限矩阵

下表是提议。D006 已批准的 cancel/plan 权限可以作为产品输入；带 `OPEN` 的行仍需 Owner 裁决。

| Action | Run creator member | Other member | Workspace owner and creator | Workspace owner, not creator | 状态 |
| --- | --- | --- | --- | --- | --- |
| create | allow | allow | allow | allow | proposed |
| list/read run | allow | allow | allow | allow | `OPEN API-O001` |
| subscribe events | allow | allow | allow | allow | `OPEN API-O001` |
| read user-visible artifact | allow | allow | allow | allow | `OPEN API-O001` |
| approve/request plan changes | allow | deny | allow | deny | D006/D004 aligned |
| cancel `user_requested` | allow | deny | allow | deny | D006 aligned |
| terminate for `cost/security` | deny unless creator | deny | allow | allow | D006 aligned |
| decide conflict | proposed allow | deny | allow | proposed deny | `OPEN API-O002` |
| retry failed branch | proposed allow | deny | allow | proposed deny | `OPEN API-O002` |

所有 allow 都要求当前有效 Workspace membership。membership 被移除后，已有 SSE 必须断开，后续 read/action 返回 404 或 403；运行是否继续及由谁接管属于 `API-O010`。

## 8. 独立 Research SSE

### 8.1 Endpoint 与隔离

`GET /v1/workspaces/{workspaceId}/research-runs/{runId}/events`

- `Accept: text/event-stream`。
- 可选 `Last-Event-ID: <decimal seq>`；不接受 runId、UUID 或复合 cursor。
- BFF mirror：`GET /api/workspaces/{workspaceId}/research-runs/{runId}/events`。
- 这是独立 Research event stream。不得修改、复用或向现有 `/chat/stream` 注入 Research event。
- 响应 header：`Cache-Control: no-cache, no-store`、`Connection: keep-alive`、`X-Accel-Buffering: no`。
- 所有鉴权、run/workspace 匹配和 cursor 校验必须在发送 `200 text/event-stream` 前完成。

### 8.2 Event envelope、seq 与持久化顺序

每个业务事件先提交 PostgreSQL 账本，再推送同一行的序列化结果：

```text
id: 42
event: run_status_changed
data: {"schemaVersion":1,"eventId":"...","runId":"...","seq":42,"type":"run_status_changed","occurredAt":"...","data":{...}}

```

```ts
type ResearchEvent<TType extends string, TData> = {
  schemaVersion: 1;
  eventId: string;
  runId: string;
  seq: number;                   // per-run integer, starts at 1
  type: TType;                   // exactly equals SSE event field
  occurredAt: string;
  data: TData;
};
```

约束：

1. `(runId, seq)` 与 `eventId` 唯一；seq 单调连续，事务回滚不能留下空洞。
2. 提交状态变化与对应 Event 必须在同一事务；不能先推送后保存。
3. 交付语义是 at-least-once。客户端按 `(runId, seq)` 去重，不能按文本或时间去重。
4. `currentEventSeq` 是 Run 快照已包含的最高 seq。客户端收到更高 seq 或缺口必须停止应用并重连/read，不可猜状态。
5. `: keepalive` comment 不持久化、没有 id、不增加 seq，也不作为活动事实。
6. 不发送 token delta、prompt、思维链、raw tool output、Asset 正文或 provider secret。

### 8.3 Event allowlist

未列出的 event name 和字段禁止发送。增加 event 或字段必须提升合同版本并同步 Web validator/fixtures。

| event | `data` 字段 allowlist |
| --- | --- |
| `run_created` | `status`, `createdByUserId`, `runStateVersion` |
| `run_status_changed` | `previousStatus`, `status`, `runStateVersion`, `reasonCode|null` |
| `step_queued` | `stepId`, `stepKind`, `branchKey|null`, `attemptNumber`, `stepStateVersion`, `runStateVersion` |
| `step_started` | `stepId`, `stepKind`, `branchKey|null`, `attemptId`, `attemptNumber`, `stepStateVersion`, `runStateVersion` |
| `step_waiting` | `stepId`, `stepKind`, `decisionId`, `decisionType`, `stepStateVersion`, `decisionStateVersion`, `runStateVersion` |
| `step_succeeded` | `stepId`, `stepKind`, `attemptId`, `attemptNumber`, `evidenceCount`, `artifactIds`, `stepStateVersion`, `runStateVersion` |
| `step_failed` | `stepId`, `stepKind`, `attemptId`, `attemptNumber`, `reasonCode`, `retryable`, `stepStateVersion`, `runStateVersion` |
| `attempt_abandoned` | `stepId`, `attemptId`, `attemptNumber`, `reasonCode`, `stepStateVersion`, `runStateVersion` |
| `approval_requested` | `decisionId`, `decisionType`, `inputArtifactId`, `inputArtifactSha256`, `decisionStateVersion`, `runStateVersion` |
| `decision_submitted` | `decisionId`, `decisionType`, `inputArtifactId`, `inputArtifactSha256`, `action`, `actorUserId`, `decisionStateVersion`, `runStateVersion` |
| `cancel_requested` | `actorUserId`, `reasonCode`, `runStateVersion` |
| `artifact_published` | `artifactId`, `artifactKind`, `visibility`, `byteSize`, `sha256`, `runStateVersion` |
| `run_completed` | `status`, `finalArtifactId`, `runStateVersion` |
| `run_failed` | `status`, `reasonCode`, `retryable`, `runStateVersion` |
| `run_cancelled` | `status`, `reasonCode`, `runStateVersion` |

每个 `data` object 都执行 `extra=forbid`。其中 ID/string/time/hash 使用第 1-6 节约束；`runStateVersion/stepStateVersion/decisionStateVersion/attemptNumber/evidenceCount/byteSize` 是非负整数，`artifactIds` 是唯一 ID 数组，status/kind/decisionType/action/visibility 必须来自跨文档 canonical enum。`reasonCode` 必须来自获批 error taxonomy，不能直接透传 provider 文本。

`branchKey` 必须是 server-issued opaque non-semantic identifier，不得包含 subproblem/question/Asset title 或用户正文；
客户端只用它分组并行 Step，不解析业务含义。

Event payload 只携带状态、ID、计数、hash 和安全 reason code，不重复保存 question、Plan/Decision comment、Evidence excerpt、Artifact/claim text、provider raw output 或 tool raw output。客户端收到 `approval_requested` 后通过 read API 获取 Plan/Conflict；收到 `artifact_published` 后通过 Artifact API 获取 metadata/content。

Terminal 事实使用 `run_completed/run_failed/run_cancelled`，随后服务端可关闭连接。客户端必须再调用 read API 取得最终完整快照；不能仅凭最后一条 Event 拼装 Artifact 或 provenance。Evaluation 是独立 R700 API surface，不作为核心 ResearchEvent 或 Step kind。

### 8.4 首连、重连和异常 cursor

- 无 `Last-Event-ID` 等价于 cursor `0`，从 `seq=1` 重放并随后 tail 新事件。
- `Last-Event-ID=N` 只发送 `seq > N`。网络层仍可能重复交付已经发送的 bytes，客户端必须按 `(runId, seq)` 去重。
- 非十进制、负数或超出整数上限：`400 invalid_event_cursor`。
- cursor 大于当前 `currentEventSeq`：`409 research_state_conflict`，客户端先 read Run。
- cursor 早于仍保留的第一条 Event：`410 research_event_history_unavailable`。客户端可 read 当前快照，但不得声称获得无缺口审计历史。
- 断线不取消 Run；BFF/浏览器重连不创建新订阅记录或新业务 Event。
- API/Worker 重启后重放必须来自持久化 Event，不从内存状态重建 seq。
- Event 保留期限、最大首连重放量和 terminal Run 是否立即关闭 stream 属于 `API-O006`。

## 9. Evidence-only Tool Registry

这些是 Worker 内部工具合同，不是公开 HTTP API。Agent 只能收到 runtime 注入的 `runId/stepId/attempt/workspaceId/FrozenAssetScope`；模型不能提交或覆盖这些边界字段。

### 9.1 `evidence.search` schema v1

```ts
type EvidenceSearchInput = {
  query: string;                 // trimmed, 1..4000 chars
  assetIds: string[];            // 0..100; 空表示整个 FrozenAssetScope
  topK: number;                  // integer 1..20; server policy may lower
};

type EvidenceSearchHit = {
  evidenceHandle: string;        // opaque server-issued ID；Agent 不得解析或跨 branch 复用
  assetId: string;
  assetKind: string;
  assetTitle: string;
  excerpt: string;               // <= 2000 chars
  locator: EvidenceLocatorDto;
  sourceVersions: {
    parserVersion: string;
    processingGeneration: number;
    representationId: string;
    indexVersion: number;
  };
  score: number;                 // finite; ranking only, not confidence
};

type EvidenceSearchOutput = {
  queryHash: string;
  hits: EvidenceSearchHit[];
  truncated: boolean;
};
```

规则：assetIds 必须是 frozen scope 子集；检索必须约束 frozen generation/index；不允许 Workspace、provider、SQL、filter expression、URL 或任意 locator JSON 作为模型输入。

### 9.2 `evidence.load` schema v1

```ts
type EvidenceLoadInput = {
  evidenceHandles: string[];     // 1..20 unique handles
};

type LoadedEvidence = {
  evidenceHandle: string;
  assetId: string;
  assetKind: string;
  assetTitle: string;
  sourceAvailable: boolean;
  content: string;               // bounded normalized Evidence text/caption
  contentSha256: string;
  locator: EvidenceLocatorDto;
  sourceVersions: {
    parserVersion: string;
    processingGeneration: number;
    representationId: string;
    indexVersion: number;
  };
};

type EvidenceLoadOutput = {
  items: LoadedEvidence[];
};
```

Handle 必须由同一 Run、同一 approved ExecutionSnapshot、同一逻辑 Researcher Step/branch 的已成功
`evidence.search` ToolCall 产生。Attempt retry 可以重放该 Step 已持久化的成功 handle 闭集，但 sibling Researcher、
Verifier 或其他分支不能 load。Load 不接受 object key、representationId、locator、Asset filename 或 URL；runtime
从 `research_evidence_handles/research_tool_call_input_handles` 解析并重新验证 Workspace、ExecutionSnapshot、
Step、Asset、generation、representation 与权限。

### 9.3 Tool error

```ts
type EvidenceToolError = {
  code:
    | "tool_input_invalid"
    | "tool_scope_violation"
    | "evidence_handle_not_found"
    | "evidence_source_unavailable"
    | "evidence_version_unavailable"
    | "tool_budget_exhausted"
    | "tool_temporarily_unavailable";
  message: string;
  retryable: boolean;
};
```

工具失败不得静默扩大 scope、切到最新 generation、访问外网或让模型构造替代 Evidence。

### 9.4 Prompt-injection 与权限边界

1. 用户问题、Plan comment、Asset 文本、OCR、caption、检索 excerpt 和 provider output 全部是不可信数据。
2. Evidence 必须作为带明确 data delimiter 的内容传入模型；其中出现的“忽略规则”“调用工具”“访问 URL”等文字没有控制权。
3. Tool registry 只注册 canonical name `evidence.search/evidence.load`，每次请求另带内部 `schemaVersion=1`。未知工具名/version/字段、超限参数和跨 scope ID fail closed。
4. Agent 不得直接访问 ORM、MinIO、Shell、filesystem、任意网络、插件或 provider client；只有 orchestration runtime 可调用已批准 provider adapter。
5. Tool output 经过 schema 校验后才进入 prompt。任何非法 locator/sourceVersions 使整个 tool call 失败，不能过滤坏项后继续。
6. 每次调用必须映射到 `research_tool_calls`，状态只允许 `requested -> running -> succeeded/failed/cancelled/abandoned`；成功 search 的 handle 闭集持久化在 `research_evidence_handles`，重启后不能重新 search 偷换结果。audit 只包含 toolCallId、schemaVersion、run/execution/step/attempt、输入 canonical hash、输出 item IDs/hash、数量、耗时、错误码和预算使用；不保存思维链、完整 query 或 raw response。
7. Tool query 是否保存明文、excerpt/content 的审计保留范围及安全审阅访问权属于 `API-O005`。

## 10. Provider、预算、成本与 timeout

### 10.1 Provider boundary

- 运行只引用 server-side approved execution profile；客户端和 Agent 都不能提交 provider URL、model name、API key 或自定义 headers。
- Create/revision 冻结对应 planning `ProviderSnapshot`；计划批准时另行冻结 research `ProviderSnapshot`。后续配置变化不能改写历史 snapshot；恢复必须使用相同 provider/config fingerprint/version，或以不可恢复失败结束，不能换模型后伪装为同一 attempt。
- provider request 只能包含当前节点所需的最小问题、已批准 prompt version 和 scoped Evidence；不得发送整个 Workspace、无关 Asset、内部 object key 或用户认证信息。
- provider response、usage 和错误必须经过 adapter 校验；provider 返回的 tool 指令没有额外权限。
- 外部 provider 的数据保留、训练使用、地域、日志、DPA 和允许发送的 Evidence 类型均未批准，见 `API-O003`。在 policy 缺失时外部 execution profile 必须 fail closed。

### 10.2 Budget enforcement

1. 每个 provider/tool call 前检查剩余 calls、token、cost、wall time、并发与 attempt；无法证明在上限内时不发起调用。
2. retry 消耗同一 approved execution budget，不重置计数。每个 PlanRevision 有独立 frozen planning ledger；
   Run `planningUsage` 聚合所有 revision，创建 revision 不抹除历史 usage。revision 数量与具体上限属于 `API-O008`。
3. provider 报告 actual usage 时保存 actual；未返回时保存版本化 estimator 结果并令 `usageFinal=false`，不得显示成精确账单。
4. 价格表缺失或版本不匹配时，带 cost hard limit 的 Run 不得开始。
5. 达到硬上限后停止新工作，以 `budget_exhausted` 结束或进入待决状态；是否允许 top-up 是 `API-O004`，不得默认超额或自动降级 Quick。
6. `research_budget_ledgers/research_provider_calls/research_tool_calls` 是 reserve、reconcile、恢复和成本不确定性的
   事实源；Step/Attempt usage 与 Read DTO 的 BudgetUsage 只是派生聚合。
7. Read DTO 中的 BudgetUsage 只暴露聚合数，不暴露 prompt、provider request ID 或账单 secret；核心 Research SSE 不增加 data draft allowlist 之外的 budget event。
8. 公开 BudgetUsage 只投影到最近已提交的业务 Event 边界；provider/tool call 的中间 reserve/reconcile 不改变公开
   Run ETag，也不伪造核心 SSE event。Step terminal 事务刷新聚合、Run stateVersion 和 Event 后再对外可见。

### 10.3 Timeout 与 retry

- `providerTimeoutSeconds` 约束单次 provider 请求；`stepTimeoutSeconds` 约束 attempt；`runTimeoutSeconds` 约束整个 Run wall time。
- timeout 必须进入持久化 SafeFailure/Event，再释放 lease；客户端断线不影响 timeout。
- 只有版本化 retry policy allowlist 中的 transient error 可自动重试；validation、permission、scope、prompt-injection、budget 和 policy 错误不得自动重试。
- attempt 必须单调递增；同一 attempt 不得因 Worker 重启重复计费、重复 Event 或重复 Artifact。
- 具体默认秒数、并发数、attempt 上限和 backoff 属于 `API-O004`。

## 11. 保留、删除与源 Asset 删除

这些语义尚未获得 Owner 批准。本文只冻结不得违反的下限，并列出待决分支。

### 11.1 不得违反的下限

1. Cancel 不等于 delete；审计记录不得因取消同步消失。
2. 已发布 Artifact、Event、Decision、provider/budget snapshot 与 Evidence provenance 不得被源重处理原地改写。
3. 源 Asset 删除后不得偷偷绑定到新 Asset、最新 generation 或同名文件。
4. `sourceAvailable=false` 时 Viewer/load 必须 fail closed；UI 可以展示获准保留的快照，但不能假装原文仍可核验。
5. Workspace 隔离、membership 与备份/恢复必须覆盖 Research records 与 Artifact bytes；DB 和对象恢复后 hash/provenance/seq 必须一致。
6. 任何 hard delete 都应是 owner-only、异步、幂等、可审计，并定义 PostgreSQL/MinIO 的完成边界；本草案暂不定义 delete endpoint。

### 11.2 Owner 必须选择的保留策略

| 对象 | 候选策略 | 当前状态 |
| --- | --- | --- |
| Run/Step/Event/Decision metadata | 随 Workspace 保留，或 terminal 后固定期限 | `OPEN API-O005` |
| Published Artifact bytes | 随 Workspace 保留，或单独期限/显式 owner delete | `OPEN API-O005/API-O007` |
| Evidence excerpt/normalized content | 源删除后保留快照，或随源删除清除正文只留 hash/locator | `OPEN API-O005` |
| Artifact claim/report text | 源删除后继续可读并标 unavailable，或级联删除/withhold | `OPEN API-O005` |
| Tool audit/query | 只留 hash/计数，或限期保存 sanitized query | `OPEN API-O005` |
| ResearchEvent replay history | 与 Run 同寿命，或短期后返回 410 | `OPEN API-O006` |
| Idempotency record | 至少覆盖客户端安全重试窗口的固定 TTL | `OPEN API-O006` |
| External provider logs/data | 由 approved data boundary policy 定义 | `OPEN API-O003` |

在 `API-O005` 关闭前，不能声称“源删除后仍完全可解释”或“源删除会完整遗忘”；两种说法都需要具体 payload/object 验证 oracle。

## 12. Quick Chat 不变 oracle

R000 与后续实现必须用测试证明以下现有语义保持不变：

1. Quick endpoint 仍是 `POST /v1/workspaces/{workspaceId}/chat/stream`；Request 仍只有 `threadId/question/assetScope/selectionText/evidenceTargets/parentMessageId/editMessageId`，不得加入 Research mode、runId、budget 或 agent 字段。
2. Quick SSE 仍按 `meta -> delta* -> citations -> done`，失败为 `error`；不得增加 Research `id/seq/Last-Event-ID`，不得发送 Research event。
3. Quick 的 BFF session、internal header、HTTP error 与断流行为保持现状。
4. Quick 不因问题复杂、超时、provider failure 或无检索结果自动创建 ResearchRun；Deep 也不自动降级为 Quick。
5. ChatMessage、MessageRetrievalScope、MessageInputEvidence、MessageCitation、Citation 与 NoteSource 的字段、locator/sourceVersions 快照和保存语义不变。
6. Existing `assetScope` 解析、ready/deleted 边界、Evidence target Workspace/generation 校验和 `sourceAvailable` 行为不变。
7. ResearchArtifact 不自动写 Note、不替换 Chat message、不改变 thread active path；用户主动转 Note 需要未来单独获批合同。
8. Research 表/事件/对象迁移的 upgrade/downgrade 与 dump/restore 测试必须证明 Quick payload、活动消息路径和 Citation/NoteSource old/new snapshot 全等。

最低回归证据：现有 Chat schema/unit tests、真实 Quick SSE 事件捕获、PDF/Image Citation/Viewer 跳转、NoteSource 复制、Asset 删除后的 `sourceAvailable=false`、恢复前后 payload hash，以及“Quick 请求期间 Research 表/Event 数量不变”的集成断言。

## 13. Endpoint error 与幂等矩阵

| Endpoint | 主要前置错误 | 状态冲突 | 幂等结果 |
| --- | --- | --- | --- |
| create | `invalid_asset_scope`, `research_provider_not_configured`, `research_budget_limit` | concurrency policy conflict | 同 key 同 body 返回同 Run |
| list/read | `workspace_not_found`, `research_run_not_found` | none | GET 不写状态 |
| cancel | permission denied | terminal/already incompatible, stale version | 不重复 cancel Event |
| plan-decision | invalid plan/comment, permission denied | stale plan/run, wrong status, prior decision | 不重复 freeze/queue/Decision |
| conflict-decision | invalid option, permission denied | stale conflict/run, prior decision | 不重复 Decision/branch resume |
| retry | invalid step/attempt, permission denied, budget exhausted | non-failed/wrong attempt/stale run | 不重复 attempt/Event |
| artifact read/content | resource not found/unavailable | hash/provenance mismatch blocks content | GET 不写状态 |
| event stream | invalid/expired/ahead cursor | run/workspace mismatch before 200 | GET 不创建业务 Event |

## 14. Owner open decisions and approval record

以下问题必须显式选择；没有答案时对应合同保持 blocked，不能由实现者自行决定：

| ID | Owner decision | 影响 |
| --- | --- | --- |
| `API-O001` | 普通 member 是否可读同 Workspace 其他人的 Run/Event/user-visible Artifact | list/read/SSE 权限与隐私；联动 data permission 决策 |
| `API-O002` | 谁可裁决 conflict、手动 retry；owner 是否可代办；允许哪些 conflict action | decision/retry DTO、权限、状态机；联动 data Decision/retry 决策 |
| `API-O003` | 外部 provider 允许发送的数据、保留/训练/地域/DPA、approved deployment defaults | provider adapter 与安全门；联动 data provider 决策 |
| `API-O004` | 预算币种、默认/最大 calls/tokens/cost/time/parallel/attempt、top-up、planning 成本 | Budget DTO 与运行终态；联动 data budget/timeout 决策 |
| `API-O005` | Run/Event/Artifact/正文保留期、源 Asset 删除级联、hard delete 与审计 | deletion、restore、sourceAvailable；联动 data retention/delete 决策 |
| `API-O006` | Event 与 idempotency record 保留期、最大 replay、过期 cursor 策略 | SSE 重放与幂等保证；联动 data Event/idempotency retention |
| `API-O007` | Artifact user/internal 可见子集与脱敏 trace export 权限 | Artifact API；联动 data Artifact visibility |
| `API-O008` | Plan 最大修订次数、planning 预算与 comment 保留 | plan-decision 与 provider 使用；联动 data PlanRevision 决策 |
| `API-O009` | 每用户/Workspace 非终态 Run 并发上限 | create 429/409 语义；联动 data concurrency 决策 |
| `API-O010` | membership 移除或 creator 离开后，运行继续、取消、接管与可见性 | auth、lease、审计；联动 data membership lifecycle 决策 |

R000 approval record 至少需要：

1. 本文件获批 commit SHA 与内容 hash。
2. `API-O001-API-O010` 每项的 Owner 决定、日期与 reviewer，并显式关联 data draft decision ID；不能仅凭相同序号猜关联。
3. 对应字段/enum/API/SSE/tool schema 的批准或修改清单。
4. Quick Chat 不变 oracle、权限拒绝矩阵、幂等/重放、源删除和 provider policy 的测试映射。
5. 明确声明候选多模态 locator 标签没有被本文批准为新 schema。
6. 明确声明批准合同不等于批准实现；R000 关闭和稳定 Git recovery point 完成后先单独授权并通过 R100 exit gate，才可另行授权 R200/R300 slice。

R700 Evaluation persistence、创建方式、单 Run read 和跨 Run Dashboard list 不属于上述 `API-O001-API-O010`，
也不属于 R000 approval。它们必须等待独立 Evaluation 数据合同，不得因批准本文件而注册候选 Evaluation endpoint。
