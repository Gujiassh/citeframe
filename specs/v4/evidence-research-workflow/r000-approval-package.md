# V4 R000 合同审批包

> 状态：**OPEN / UNAPPROVED**。
>
> 本文件把数据草案与 API/事件/工具草案的分散问题合并为 Owner 可审批的决策组。批准某项只批准所引用
> 合同语义，不授权 migration、ORM、API 路由、SSE、Worker、Web、provider 调用或外部网络访问。

## 1. 审批对象与边界

审批对象：

- [`data-state-contract-draft.md`](data-state-contract-draft.md)：字段、状态机、版本、账本、provenance、删除与恢复。
- [`api-event-tool-contract-draft.md`](api-event-tool-contract-draft.md)：公共 DTO/API、独立 Research SSE、Evidence-only tools、权限与错误。
- 本文件第 3 节 `AP001-AP012`：合并后的 Owner 决策及推荐默认。

不在本次审批范围：

- 任何实现、migration execution、部署或真实 provider credential/profile 启用。
- R700 Evaluation 数据合同、Dashboard API 或 Evaluation 路由。
- Markdown/HTML、DOCX/PPTX、Audio/Video 的新 locator、schema 或 adapter。
- Quick Chat、Citation、NoteSource、EvidenceLocator、Note 保存或现有 Asset 删除语义的改写。

正式 approval record 必须记录三份文件的同一 Git commit、SHA-256、Owner、日期、reviewer、例外项和明确授权范围。

## 2. 不可拆开的语义 Oracle

1. Create 和每次 plan revision 只冻结一个 append-only PlanRevision；批准时只精确复制当前 revision，创建唯一 immutable ExecutionSnapshot。
2. Quick Answer 保持默认且合同不变；Deep Research 显式 opt-in，不自动降级或升级，也不自动写 Note。
3. PostgreSQL Run/Step/Attempt/Event/Decision/Artifact/Claim/Evidence/Tool/Provider/Budget 账本是业务事实源；编排器 checkpoint 不是。
4. Agent 只可调用 `evidence.search/evidence.load`，并由 runtime 注入内部 `schemaVersion=1`；不得获得 ORM、MinIO、Shell、filesystem、任意网络或插件权限。
5. 每个最终事实 Claim 必须由 supported Evidence provenance 支撑；人工 Decision 不能把 unsupported Claim 改成 supported。
6. Research SSE 与 Chat SSE 分离，先持久化 Event 再推送，按 `(runId, seq)` at-least-once 重放。
7. R700 Evaluation 与候选新模态保持 deferred；R000 approval 不得让它们借壳进入 schema/API。

任一 Owner 例外如果破坏上述 Oracle，必须先修改两份草案并重新完成跨文档审查，不能只在 approval record 中覆盖。

## 3. Owner 决策组

所有状态当前均为 `OPEN`。`推荐默认`是待批准方案，不是已生效事实。

### AP001 状态机与双快照边界

- **推荐默认**：批准草案中的 Run/Step/Attempt/Decision closed enums 与迁移表。approval 前 question、scope、server-resolved config/version/budget 变化在同一 Run 创建新 PlanRevision；approval 只验证并精确复制该 revision，之后任何输入变化必须新 Run。
- **禁止**：原地修改 revision、批准时吸收 latest Asset/config、终态回退、未批准直接 fan-out。
- **映射**：data `O001/O002/O021`；API plan create/decision DTO。
- **状态**：OPEN。

### AP002 Workspace 读取与操作者权限

- **推荐默认**：当前有效 Workspace member 可读取同 Workspace 的 Run、Event 和 `user` Artifact；`internal` Artifact、Prompt 和 provider 审计不开放给普通 member。
- **推荐默认**：只有 creator 可 approve/revise plan、裁决 conflict、人工 retry 和普通取消；Workspace owner 只能因 `cost/security` 终止任意 Run，不能冒充 creator 作语义裁决。
- **推荐默认**：creator membership 被移除时，非终态 Run进入 `cancel_requested`，不自动转交 owner；已有 SSE 立即断开。
- **映射**：data `O003/O005/O015`；API `API-O001/API-O002/API-O010`。
- **状态**：OPEN。

### AP003 Plan 修订与 HITL

- **推荐默认**：每个 Run 最多 5 个 PlanRevision；每次 revision 保存 comment 和新的 planning snapshot。触发 revision 的旧 Decision 以 `submitted/action=request_revision` 保留，旧 Plan Artifact 可被新版本 supersede，但二者都不删除。
- **推荐默认**：plan/conflict Decision 不自动过期；人工等待不计 active run/provider timeout，但仍受 Workspace 归档/终止策略约束。
- **推荐默认**：conflict 只允许 `exclude_conflicted_claims / keep_as_unresolved / cancel_run`；不允许人工接受 unsupported Claim 为事实。
- **推荐默认**：普通 cancel 和人工 retry 只接受 closed reason/error 与版本字段，不接受自由 comment；人工 retry 使用 append-only RetryRequest 审计 actor、Attempt 和时间。
- **映射**：data `O004/O005`；API `API-O002/API-O008`。
- **状态**：OPEN。

### AP004 Provider 与数据边界

- **推荐默认**：客户端只提交 question 与 Asset scope；server 从唯一 approved deployment profile 解析 provider/model/config/pricing/data-boundary policy。v1 每 Run 只用一组 generation provider/model。
- **推荐默认**：外部 provider 仅接收当前节点最小必要 question、Prompt 和 bounded text excerpt；Image crop/bytes、整个 Workspace、对象键、认证信息和任意 URL 均不发送。
- **推荐默认**：approved profile 必须满足 no-training、传输/静态加密、明确地域/DPA 和可审计 retention；条件不完整时 fail closed。v1 不开放 Agent 任意网络。
- **映射**：data `O010/O011`；API `API-O003`。
- **状态**：OPEN。

### AP005 预算、并发、timeout 与 retry

- **推荐默认**：Create 冻结 Run 级单一 USD currency，全部 PlanRevision 与 Execution ledger 必须保持该币种，不做运行时汇率换算；非 USD provider 必须新建 Run 并使用对应同币种 profile。planning 每 revision 上限为 2 provider calls、32k input tokens、8k output tokens、USD 0.50；approved execution 上限为 32 provider calls、64 ToolCall attempts、250k input、64k output、USD 5.00。
- **推荐默认**：最多 3 个并行 Researcher；active run 30 分钟、step 5 分钟、provider call 120 秒；每 Step 最多 3 个 Attempt。HITL 等待不计 active run timeout。
- **推荐默认**：每用户最多 2 个、每 Workspace 最多 10 个非终态 Run；超限返回 429。预算不允许原 Run top-up，retry 消耗同一 frozen budget，预算耗尽必须新 Run。
- **推荐默认**：ProviderCall + ToolCall + BudgetLedger 是 reserve/reconcile/outcome-unknown 的权威事实源；StepAttempt usage 只做派生聚合。
- **映射**：data `O003/O004/O012/O013`；API `API-O004/API-O008/API-O009`。
- **状态**：OPEN。

### AP006 Evidence、Claim 与 Tool provenance

- **推荐默认**：批准 normalized Claim/Evidence/ArtifactClaim；Research Evidence 只克隆当前 registry 已支持的 typed locator/detail/regions，不保存 locator JSON 或候选模态字符串。
- **推荐默认**：Evidence handle 是持久化 opaque ID，只能由同一 Run、ExecutionSnapshot、逻辑 Researcher Step/branch 使用；sibling branch 与后继 Agent 不共享 handle。
- **推荐默认**：ToolCall、input handle join、result handle 与 BudgetLedger 在内部原子事务提交，不产生核心 SSE Event；Claim/Evidence/Artifact publish 在 Step 业务边界与对应 Event 原子提交。retry 不能替换已成功结果闭集。
- **映射**：data `O006/O007`；API Evidence-only Tool Registry。
- **状态**：OPEN。

### AP007 Artifact 可见性与 trace

- **推荐默认**：`research_plan/evidence_bundle/conflict_report/final_report` 可标为 `user`；`verification_result/execution_checkpoint` 固定 `internal`。`trace_export` 只允许 owner 显式请求脱敏版本，不暴露 Prompt、思维链、raw provider/tool payload 或内部对象键。
- **推荐默认**：Deep final report 是独立 ResearchArtifact，不伪装为 ChatMessage；origin thread 可空且只作导航。
- **映射**：data `O015/O016/O020`；API `API-O007`。
- **状态**：OPEN。

### AP008 保留、源删除与 hard delete

- **推荐默认**：v1 只支持 Run archive，不提供单 Run hard delete。Run、Plan、Decision、Event、user Artifact、Claim/Evidence provenance 随 Workspace 生命周期保留；internal diagnostics 最长 30 天，但不得早于可恢复 Run 到期。
- **推荐默认**：源 Asset 删除后保留与 Citation/NoteSource 同级的最小 excerpt、typed locator 和 sourceVersions 快照；`sourceAvailable=false`，Viewer/load fail closed，不绑定新 generation 或同名 Asset。
- **推荐默认**：Workspace hard delete 才执行显式两阶段 DB/MinIO 清理与 tombstone 审计；任何对象失败都可重试，不使用无边界 cascade。
- **映射**：data `O008/O009/O017`；API `API-O005`。
- **状态**：OPEN。

### AP009 Event replay 与 mutation 幂等

- **推荐默认**：ResearchEvent 与 Run 同寿命，每 Run 最多 10,000 个持久化业务 Event；SSE 只发送草案 allowlist，客户端按 `(runId, seq)` 去重。不可用历史 cursor 返回 410，不伪造无缺口历史。
- **推荐默认**：`research_idempotency_records` 覆盖所有公开 mutation，TTL 24 小时且不得短于最大客户端 retry window；同 key/同 body 返回冻结结果，同 key/不同 body 返回 409。
- **推荐默认**：GET/read/SSE 不创建业务 Event；核心 Research SSE 不发送 token delta、正文、Prompt、comment 或 provider/tool raw data。
- **映射**：data `O014`；API `API-O006`。
- **状态**：OPEN。

### AP010 Workflow/Prompt 治理

- **推荐默认**：v1 只允许受控 deployment release 发布/retire WorkflowVersion 与 PromptVersion，不提供 Workspace UI/API；普通 member 和 Workspace owner 都不能读取 Prompt 正文或发布全局版本。
- **推荐默认**：版本被运行引用后内容不可变；retire 只阻止新 revision 引用，不改变历史 replay。
- **映射**：data `O015`；API provider/config snapshot。
- **状态**：OPEN。

### AP011 Migration、备份与恢复

- **推荐默认**：R200 migration 只能 additive，不给 Quick/Asset/Citation/Note 表增加必填字段。空 Research 表可 downgrade；存在业务数据后禁止破坏性 downgrade，使用 backup/restore。
- **推荐默认**：恢复到空 PostgreSQL/MinIO/Redis；新 Worker 不复用旧 lease token，等待 frozen lease expiry 后把旧 Attempt 标为 abandoned，再按原 retry policy 恢复。
- **推荐默认**：restore oracle 比较全部 Research 行、Event seq、Artifact bytes/hash、typed locator、planning/execution snapshot 和 Quick Answer old/new payload。
- **映射**：data `O018/O019`；API restore/error semantics。
- **状态**：OPEN。

### AP012 安全、Evaluation/新模态延后与实施授权

- **推荐默认**：error/comment/Artifact/trace 不进入普通日志或 metric；日志只保留扁平 ID/status/reason/duration；敏感 DB/MinIO 内容使用现有静态加密和访问审计边界。
- **推荐默认**：R700 Evaluation persistence/API 另建合同；候选 `audio_range/video_range/heading/anchor/workbook/sheet/cell/range` 不进入 R000 schema。
- **推荐默认**：批准 `AP001-AP012` 仍只关闭 R000 合同设计；之后先单独授权并通过 R100 exit gate，才可另行授权 R200 账本、R300 执行器；任何真实 provider 启用也必须单独批准。
- **映射**：data `O020`；API deferred R700；requirements D001-D007。
- **状态**：OPEN。

## 4. Owner 回复格式

可以一次回复：

```text
批准 AP001-AP012 推荐默认；例外：无。
```

或仅列例外：

```text
批准除 AP005/AP008 外的推荐默认。
AP005：<修改>
AP008：<修改>
```

收到明确回复后，下一步只能是把决定回写为带 commit/hash 的 R000 approval record，完成反向审查和合同测试映射。
在 Owner 另行授权实现前，不创建 migration、表、endpoint、SSE、Worker DAG 或 Web UI。

## 5. 未来独立 Approval Record 字段

Owner 明确决定后另建 immutable approval record，并在其中记录本文件 hash；不得在本文件内回填自身 hash，
避免自引用导致 hash 永远变化。

| 字段 | 值 |
| --- | --- |
| Owner | OPEN |
| Decision date | OPEN |
| Approved AP IDs | OPEN |
| Exceptions | OPEN |
| Data draft SHA-256 | OPEN |
| API/event/tool draft SHA-256 | OPEN |
| Approval package SHA-256 | OPEN |
| Git commit | OPEN |
| Independent reviewers | OPEN |
| Implementation authorized | **NO** |
