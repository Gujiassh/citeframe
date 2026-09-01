# R2-K 持久化补偿责任 A-DATA 决策提案

日期：2026-09-01
基线：`5d9a87107d6a44bacfee23ce28570d03919b98c1`
状态：**待所有者明确批准；本文不构成实现授权**

## 1. 决策目的

R2 已通过 A-J 与 L 的真实 PostgreSQL 多进程验收，但 K 场景仍未闭合。最终研究报告发布当前按以下顺序执行：

1. 生成报告字节、`artifact_id`、内容哈希和对象键；
2. 把对象写入 MinIO；
3. 在一个数据库事务中写入 `ResearchArtifact`、Claim 映射、Step/Attempt/Run 终态和三个终态事件；
4. 数据库 `commit` 抛出异常时，立即新建会话检查提交结果；
5. 检查结果为 `committed` 时返回成功，为 `absent` 时删除对象；检查本身不可用时返回 `research_commit_outcome_unknown`。

该链路能处理“提交响应丢失但数据库可立即核验”和“提交明确未发生”两类情况，不能处理“对象已写入、提交结果未知、数据库核验也暂时不可用”的情况。此时数据库中没有独立于原 Worker 进程的发布意图，也没有后续 Worker 可以认领的补偿责任。原进程退出后，对象可能成为孤儿；同时通用失败路径会把未知结果归一为非重试的 `research_execution_failed`，存在把已经提交成功的发布误判为失败的风险。

关闭 R2-K 至少需要一条先于对象写入持久化的内部发布意图，以及由后续 Worker 独立认领、核验、完成或补偿该意图的状态机。这会新增数据库表、Alembic 迁移和 ORM 映射，并改变最终报告发布的内部保存、重试和崩溃恢复语义，因此必须通过 `A-DATA` 决策门。

## 2. 请求批准的范围

建议批准以下内部变更：

- 新增 `research_publication_intents` 表及对应 Alembic migration、ORM 映射和 Research persistence commands；
- 最终报告在对象上传前先提交 durable intent，并在 intent 中保存可由任意后续 Worker 原样上传的 canonical report bytes；
- Worker 使用数据库时间租约认领未完成 intent，并在原发布进程退出后继续核验和补偿；
- 对象写入使用 reconcile generation 隔离的 key；PostgreSQL fencing 不再被错误地当成可以取消已经发出的 MinIO PUT/DELETE；
- 数据库终态、`ResearchArtifact`、Claim 映射、现有三个终态 Event 与 intent 的 `committed` 状态仍在同一个事务中原子提交；
- 未知 prepare/final commit 结果通过内部 `reconcile_pending` 结果进入 intent reconciler，不再进入通用 `fail_research_step`；
- `artifact_publisher` Attempt 存在非终态 intent 时，由 publication-specific recovery 接管，generic expired-Attempt reclaimer 不得把它按普通 Attempt abandon/requeue；
- 只有 cancellation、永久 scope/integrity 冲突或明确终止策略才进入补偿；数据库明确未提交但 payload/object 仍有效时，优先重试 finalization；
- 对象已确认不存在或已安全删除后，intent `absent` 与 Attempt/Step/Run disposition、既有失败/排队/取消 Event 必须在同一数据库事务中提交；
- 同一 Run 的 `final-report` 继续最多存在一个已提交 `ResearchArtifact`；重复执行、重复 reconcile 和迟到 Worker 不得产生第二个终态 Artifact 或重复 Event。

本提案不请求批准以下变化：

- 不改变公开 HTTP 路由、请求体、响应体、状态码和权限规则；
- 不增加新的用户可见 Research Run/Step/Attempt/Event 枚举值；
- 不改变最终报告内容、Claim 选择、对象键既有 `research/{workspace}/{run}/{artifact}` 前缀、内容类型和内容哈希含义；完整对象键会增加内部 publication generation 段；
- 不改变现有 Workspace、Asset、Citation、Note、Chat 或 SSE 对外合同；
- 允许既有 `step_failed` Event 的开放字符串字段 `reasonCode` 在确认补偿为 absent 后使用新的安全码 `research_publication_compensated`；Event 类型、schema 和顺序合同不变；
- 允许超过 16 MiB 的 canonical final report 在任何 intent/object 写入前使用新的非重试安全码 `research_publication_payload_too_large` 进入既有失败路径；该上限是本次批准的一部分；
- 不授权 W1、A3-A6、M、P、G 或 GitHub repository settings 工作；
- 不授权 provider 付费评测或用户研究。

## 3. 建议的数据合同

### 3.1 `research_publication_intents`

建议由一个内部表承载一次最终报告发布尝试的持久化责任。字段名称可以在实现审查中做不改变语义的机械调整，但以下信息和约束不可缺失。

| 字段 | 类型与空值 | 含义 |
| --- | --- | --- |
| `id` | `varchar(36)`，主键 | intent 稳定标识 |
| `workspace_id` | `varchar(36)`，非空，外键 | Workspace 边界 |
| `run_id` | `varchar(36)`，非空，外键 | Research Run |
| `step_id` | `varchar(36)`，非空，外键 | `artifact_publisher` Step |
| `attempt_id` | `varchar(36)`，非空，外键，唯一 | 创建本次 intent 的 Attempt；一个 Attempt 只能创建一个 intent |
| `execution_snapshot_id` | `varchar(36)`，非空，外键 | 固定工作流、模型和 Prompt provenance |
| `logical_key` | `varchar(160)`，非空 | 固定为 `final-report` |
| `artifact_id` | `varchar(36)`，非空，唯一 | 预分配的最终 Artifact 标识，重放时保持不变 |
| `committed_artifact_id` | `varchar(36)`，可空，唯一外键 | 仅 `committed` 时指向与 `artifact_id` 相同的 `ResearchArtifact` |
| `object_prefix` | `varchar(1024)`，非空，唯一 | 稳定且由 intent 独占的对象前缀；完整 key 按 generation 生成 |
| `current_object_generation` | `bigint`，可空 | 当前合法 claim 使用的对象 generation |
| `current_object_key` | `varchar(1024)`，可空，唯一 | 当前合法 generation 的对象键 |
| `adopted_object_generation` | `bigint`，可空 | 最终 Artifact 已采用的 generation，仅 `committed` 时非空 |
| `adopted_object_key` | `varchar(1024)`，可空，唯一 | 最终 Artifact 实际引用的对象键，仅 `committed` 时非空 |
| `content_type` | `varchar(255)`，非空 | 固定为 `text/markdown` |
| `render_schema_version` | `varchar(32)`，非空 | 固定 canonical renderer 合同版本，初始为 `final-report-v1` |
| `payload_bytes` | portable binary，非空 | 完整 canonical report bytes；ORM 使用 `LargeBinary`，PostgreSQL 为 `bytea`、SQLite 为 `blob` |
| `byte_size` | `bigint`，非空 | `payload_bytes` 字节长度；本方案批准 16 MiB 内部硬上限 |
| `content_sha256` | `varchar(64)`，非空 | canonical report SHA-256 |
| `selection_json` | portable JSON，非空 | 有序 `factClaimIds` 与 `unresolvedClaimIds`；ORM 使用既有 `JSON_DOCUMENT`，PostgreSQL 为 `jsonb` |
| `selection_sha256` | `varchar(64)`，非空 | canonical `selection_json` SHA-256，防止恢复时选择集合或顺序漂移 |
| `status` | `varchar(24)`，非空 | `prepared`、`uploaded`、`committing`、`committed`、`compensating`、`absent` |
| `state_version` | `bigint`，非空 | intent 乐观版本，初始为 1 |
| `claim_generation` | `bigint`，非空 | 每次 reconcile 认领递增的 fencing generation |
| `claim_owner` | `varchar(128)`，可空 | 当前 Worker instance；与 token/expiry 成组出现 |
| `claim_token_hash` | `varchar(64)`，可空 | reconcile token 的 SHA-256；不持久化明文 token |
| `claim_expires_at` | `timestamptz`，可空 | 使用数据库时间计算的认领到期时间 |
| `claim_heartbeat_at` | `timestamptz`，可空 | 当前 claim 最近一次 DB-time heartbeat；与其他 claim 字段成组出现 |
| `next_reconcile_at` | `timestamptz`，非空 | 使用数据库时间控制的下一次尝试时间 |
| `reconcile_attempt_count` | `integer`，非空 | reconcile 次数，只用于调度与可观测性 |
| `last_error_code` | `varchar(128)`，可空 | 安全归一化错误码，不保存原始异常或凭据 |
| `created_at` | `timestamptz`，非空 | intent 创建时间 |
| `updated_at` | `timestamptz`，非空 | 最近状态变化时间 |
| `resolved_at` | `timestamptz`，可空 | `committed` 或 `absent` 的收敛时间 |
| `orphan_sweep_after` | `timestamptz`，可空 | terminal intent 下一次 generation-prefix 清理时间；不改变 terminal 状态 |

必要数据库约束：

- `status` 只能取上述六个值；
- `0 <= byte_size <= 16777216`，并使用 PostgreSQL/SQLite 均支持的 `byte_size = length(payload_bytes)` check；`state_version >= 1`、`claim_generation >= 0`、`reconcile_attempt_count >= 0`；
- `claim_owner`、`claim_token_hash`、`claim_expires_at`、`claim_heartbeat_at` 必须同时为空或同时非空；
- `committed`、`absent` 必须具有 `resolved_at`，非终态不得具有 `resolved_at`；
- 终态 intent 不得保留任何 claim 字段；
- `content_sha256` 与 `selection_sha256` 必须是 64 字符小写十六进制字符串；
- `(run_id, logical_key)` 建立 `WHERE status <> 'absent'` 的 partial unique index；只有历史 `absent` 可以与下一次 Attempt 共存，`committed` 永久阻止新 intent；
- `committed` 必须具有 `committed_artifact_id`、`adopted_object_generation` 和 `adopted_object_key`，并满足 `committed_artifact_id = artifact_id`；其他状态三者必须为空；
- `current_object_generation`、`current_object_key` 必须同时为空或同时非空，并且 generation 为正数；
- `uploaded`、`committing` 必须同时具有有效 claim 和 current object，且 `current_object_generation = claim_generation`；`prepared` 有 claim 时 current object 必须属于该 claim generation，无 claim 时 current object 必须为空；`compensating`、terminal 状态的 current object 必须为空；
- 完整对象键固定为 `{object_prefix}/publication/{claim_generation}/final.md`；旧 generation 对象只通过 prefix sweep 发现，不得继续占用 current 字段；
- `ResearchArtifact` 现有 `(run_id, logical_key)` 唯一约束继续作为最终用户可见发布的最后防线；
- 建立 `(status, next_reconcile_at, claim_expires_at, id)` 调度索引，以及 `run_id`、`step_id` 查询索引；`committed_artifact_id` 的循环外键使用明确命名的 deferred/use-alter migration 约束。

`payload_bytes` 和 `selection_json` 是内部恢复快照，不是新的公开 payload。prepare 时先由当前 renderer 生成一次完整字节并冻结；后续 Worker 只能上传 `payload_bytes`，不能依赖当前 renderer、原 Worker 内存或可被异常修改的 Claim 行重新渲染。写入前必须验证 Claim ID 唯一、两组互斥、顺序稳定，并验证 selection/payload 哈希、字节长度、renderer 版本；finalize 时还要与既有 synthesis checkpoint 和 Claim provenance 交叉核验，但该交叉核验不得改变已经冻结的字节。

超过 16 MiB 时不得截断、压缩后冒充原报告或只存 hash；prepare 在写入 intent 和对象前以 `research_publication_payload_too_large` 失败。该码为非重试 failure，沿用既有 `step_failed`/`run_failed` 结构。Terminal intent 与冻结 payload 的保留期跟随 Research Run/Workspace；nonterminal payload 不得被 TTL 清理。Workspace 的既有硬删除/备份/恢复范围必须包含新表，不能留下脱离 Run 的报告副本。

## 4. 目标状态机

```text
prepared
  | 当前 claim generation 的对象写入并按 key/size/hash 核验
  v
uploaded
  | 独立短事务提交 committing marker
  v
committing ------------------------------+
  | 终态事务明确提交                     | commit 响应/核验未知
  v                                      |
committed <-------------------------------+-- 后续 Worker reconcile

prepared/uploaded/committing
  | cancellation/永久 scope 或 integrity 冲突/明确终止策略
  v
compensating
  | generation-prefix 安全清理完成
  v
absent + Attempt/Step/Run/Event disposition（同一 DB 事务）
```

### 4.1 `prepared`

发布命令必须先在持有 Run、Step、Attempt 锁并验证 lease/fencing 的事务中生成稳定 `artifact_id`、`object_prefix`、完整 `payload_bytes`、报告哈希和 selection 快照，然后提交 intent。prepare 事务可把原发布 Worker 直接登记为第一代 intent claimant；完整对象键由该 claim generation 派生。只有 durable intent 可由独立会话读回后，才允许上传对象。

准备事务的提交响应如果丢失，必须使用同一 `attempt_id` 查询或幂等重放，不能生成第二个 intent；在准备结果仍无法核验时不得上传对象，也不得进入通用失败路径。若准备事务实际上已提交，后续 reconciler 负责继续；若实际未提交，对象尚未写入，原 Attempt 可在 lease 到期后按既有恢复流程处理。所有非终态 intent 都保留完整 payload，因此 Worker/renderer 版本切换不影响字节重放。

### 4.2 `uploaded`

对象上传使用 intent 中冻结的 payload 和当前 claim generation 专属 key，例如：

```text
research/{workspace_id}/{run_id}/{artifact_id}/publication/{claim_generation}/final.md
```

每次 claim 接管都递增 generation，并只允许新 owner 上传、读取或删除自己的 generation key。PostgreSQL token/generation 不能取消事务外已经发出的对象请求；generation-scoped key 保证迟到 PUT/DELETE 只能影响旧 generation，不能覆盖或删除新 owner 的对象。

由于最终报告限定为 16 MiB，上传确认后必须重新下载对象字节并验证长度和 SHA-256；不能把 multipart ETag 当成内容 SHA-256。验证通过后再把 intent 推进为 `uploaded`。若 `uploaded` 状态写入失败，intent 可以停留在 `prepared`；reconciler 仍会以自己的新 generation 上传同一冻结 payload，不依赖旧中间标记或旧对象继续。所有存储调用必须使用硬超时，并由 DB-time heartbeat 保证 intent claim 覆盖该操作；超时不会授权复用同一完整 key，而是等待本代 claim 结束或由下一代使用新 key 接管。

### 4.3 `committing` 与 `committed`

`uploaded -> committing` 由一个独立短事务先行提交；它在验证 current generation 对象后写 marker 并释放锁。随后 final transaction 按现有 `Run -> Step -> Attempt -> intent` 锁顺序取得业务链。原发布进程必须同时验证 Attempt lease 和 intent claim；独立 reconciler 不得伪造或复用旧 Attempt lease，而是验证 intent 的 `claim_generation + claim_token_hash + DB-time expiry`，再确认该 intent 仍是该 Step 的唯一非 absent 发布责任。该事务必须再次验证 Workspace/Run/Step/Attempt/snapshot/Claim/Prompt/current object metadata 和冻结 payload。

若 final commit 响应丢失，不得另写失败状态。数据库恢复后，reconciler 先从 Run 开始取得业务锁，再 `SELECT ... FOR UPDATE` 锁 intent；该锁会等待仍在运行的旧 final transaction 结束。看到 `committed` 表示旧事务成功；取得锁后仍看到 `committing` 才能证明旧事务没有提交。数据库不可用、锁等待仍未决或结果不完整时继续保持 nonterminal，绝不删除对象或失败 Run。看到 `committing` 且 Run/payload/current generation 对象仍有效时，重新执行同一个 finalization，不能仅因旧事务 absent 就进入补偿。

即使原 Attempt lease 已过期，也只能由持有有效 intent fencing 的专用 reconcile command 完成或补偿，普通 Step complete/fail command 仍不得绕过 Attempt lease。final transaction 原子完成：

- 写入既有 `ResearchArtifact`、Prompt 版本映射和 Claim 映射；
- 把 Attempt 与 Step 标记为 `succeeded`，把 Run 标记为 `completed`；
- 继续使用现有 dedupe key 写入一次 `step_succeeded`、`artifact_published`、`run_completed`；
- 把 `current_object_generation/key` 冻结为 `adopted_object_generation/key`，让 `ResearchArtifact.object_key` 只引用 adopted key；
- 把 intent 标记为 `committed`、设置 `committed_artifact_id` 并清空 reconcile claim。

因此，数据库中不应出现“最终 Artifact 和终态 Event 已提交，但 intent 仍是非终态”的正常状态。即使客户端未收到 commit 响应，后续查询也能由 `artifact_id`、Run/Step/Attempt 终态、三个 dedupe Event 和 intent `committed` 共同确认成功。

### 4.4 `compensating` 与 `absent`

“旧 final transaction 未提交”只授权使用冻结 payload 和合法 current generation 重试 finalization，不构成补偿理由。只有以下情况才能从 nonterminal 进入 `compensating`：Run cancellation 已先取得锁并提交、永久 scope/provenance/integrity 冲突使发布永远不可完成，或以后另经批准的明确终止策略。`unknown`、暂时数据库错误、暂时对象存储错误和旧 transaction rollback 都不是删除或失败理由。

补偿以 intent 独占 prefix 为边界，删除所有已知 generation 对象，并在最后一次可能的旧存储请求硬超时与 claim expiry 之后执行至少两次有间隔的 prefix sweep。对象键、预分配 artifact id、Workspace 和 Run 必须都匹配 intent，任何删除/列举错误都保持 `compensating` 并退避。只有重新列举确认 prefix 为空后，才允许数据库收敛为 `absent`。

对象安全清理完成后，**一个数据库事务**必须按 `Run -> Step -> Attempt -> intent` 锁序完成以下全部动作：再次确认不存在 final Artifact 和三个终态 Event；把 intent 标记为 `absent`、设置 `resolved_at`、清空 claim；以安全 reason code `research_publication_compensated` 终结原 Attempt；若 Attempt 次数未耗尽，则原子把 Step 重新排队并写入既有 `step_failed`、`step_queued` Event；若次数耗尽，则按既有 retryable disposition 把 Run 置为 `awaiting_retry` 并只写既有 `step_failed` Event；若 cancellation 获胜，则不写补偿失败/排队 Event，而在同一锁序中进入既有取消收敛。`research_publication_compensated` 被明确加入 internal transient failure policy；prepare/final outcome unknown 本身永远不使用该码。

不得先提交 `absent` 再单独处理 Attempt/Step/Run；否则 terminal intent 会失去后续 durable owner。补偿事务在任何 kill point rollback 后都仍保持 `compensating`，可被新 Worker 接管。

若当前 generation 对象内容哈希不匹配，reconciler 不得把它当作成功发布。先用新的 claim generation 从冻结 payload 写入一个新 key 并重试；只有重复不匹配被证明为永久 storage-integrity 冲突时才进入 `compensating`。任何删除失败都保持非终态并退避，不能假报 `absent`。

取消竞态沿用现有 Run 锁决定顺序：若 final transaction 先取得 Run 锁并完成提交，Run 的 `completed` 终态获胜，迟到取消不得回退；若 `cancel_requested` 先提交，reconciler 不得再发布 final Artifact，而应在确认数据库没有发布后补偿对象并让既有取消流程收敛。任何分支都不得同时产生 `run_completed` 与 `run_cancelled`。

### 4.5 terminal orphan sweep

物理对象写无法跨 PostgreSQL 与 MinIO 达到 exactly-once，本方案只承诺用户可见 Artifact、Run/Step/Attempt 终态和 Event exactly-once。terminal intent 仍保留周期性 orphan-sweep 责任：

- `committed` intent 每次 sweep 先重新读取终态与 adopted key，只保留 adopted key，删除同 prefix 下其他 generation；
- `absent` intent 每次 sweep 先重新读取终态，再删除整个 prefix；
- sweep 在覆盖最大存储请求超时的观察窗口内重复，防止旧 generation 的在途 PUT 在早期 sweep 后迟到落盘；
- sweep 只处理 intent 独占 prefix，不改变 terminal 数据库状态；错误只延后 `orphan_sweep_after`；
- 最终验收必须在观察窗口后证明无已确认孤儿对象，不能把一次 list/delete 成功当成永久证明。

## 5. 多进程认领与 fencing

Worker 每个 dispatcher loop 在普通 Step claim 前，先尝试处理至多一个到期 publication intent。认领使用 PostgreSQL `FOR UPDATE SKIP LOCKED`，排序固定为 `next_reconcile_at, id`，避免多 Worker 阻塞同一行。

所有租约判断使用数据库时间，不接受调用者传入的本机时间：

- 认领时在同一数据库事务中取得 DB timestamp；
- 仅认领非终态、`next_reconcile_at <= db_now`，且未认领或 claim 已到期的 intent；
- 设置 `claim_owner`、随机 token 的 SHA-256、`claim_expires_at`、`claim_heartbeat_at`，并递增 `claim_generation`；
- 每个 claim/heartbeat/finalize/compensate command 在事务内只读取一次 DB timestamp，并用同一个值完成到期比较、heartbeat、expiry 和 `next_reconcile_at` 计算；不接受本机时间替代；
- 长对象 PUT/GET/LIST/DELETE 在硬超时内执行，Worker 在操作期间用 intent token/generation 做 DB-time heartbeat；heartbeat 失败后不得继续采用该对象或回写状态；
- 存储访问在短事务外执行；回写前重新锁行并同时校验 `id + claim_generation + claim_token_hash + claim_expires_at > db_now`；
- 迟到 Worker 的 generation/token 不匹配时只能放弃，不得删除对象、写 Artifact、改变 Step/Run 或推进 intent；
- claim 事务只锁 intent、写入租约后立即提交，不在持有 intent 行锁时反向获取 Run/Step/Attempt；
- 状态更新、终态提交和补偿均沿用 `Run -> Step -> Attempt -> intent` 的锁顺序，不能反向获取造成死锁。

Reconcile 的暂时性数据库或对象存储错误只更新安全错误码、递增计数并设置有上限的退避时间。它不得消耗新的模型调用、工具调用或预算，也不得创建新的用户可见 Event。

### 5.1 claim 接管状态转换

Claim 事务在 intent 行锁内按锁后实际状态执行以下原子转换，不能只递增 generation 而保留旧状态标记：

| 锁后状态 | 接管事务必须执行 | 接管后的下一步 |
| --- | --- | --- |
| `prepared` | `claim_generation += 1`，写入新 claim/heartbeat/expiry；把 `current_object_generation/key` 设置为新 generation/key；状态保持 `prepared` | 只从 frozen `payload_bytes` 上传新 generation，下载核验后才进入 `uploaded` |
| `uploaded` | `claim_generation += 1`，写入新 claim；**原子回退为 `prepared`**，用新 generation/key 替换 current 字段 | 不继承旧 generation 的 verified marker；重新 upload、download/hash verify、`uploaded -> committing` |
| `committing` | `SELECT ... FOR UPDATE` 必须先等待旧 final transaction 结束；锁后若为 `committed`，不递增、不改写，直接返回原 Artifact；锁后仍为 `committing` 才证明旧 final transaction 未提交，此时递增 generation、写新 claim、**原子回退为 `prepared`**并替换 current 字段 | 以新 generation 重做 upload/verify/marker/finalize；旧 generation 交给 terminal sweep |
| `compensating` | `claim_generation += 1`，写入新 claim，状态保持 `compensating`，清空 `current_object_generation/key` | 按整个 intent 独占 prefix 继续 list/delete/观察窗口/sweep，不创建或采用新的 report object |
| `committed` / `absent` | 不得认领或递增 generation；若等待行锁期间变成 terminal，claim query 必须重新检查 predicate 并返回未认领 | 仅由 terminal orphan sweeper 按终态规则清理 |

旧 claim 主动释放或暂时错误退避时，`prepared` 必须在同一事务中清空 claim 与 current 字段；`uploaded`、`committing` 不能在没有 claim 的情况下继续存在，而应由当前 owner 在合法 fencing 下回退为 `prepared` 后释放。接管后的新 generation 从不采用旧 generation 的对象，即使旧对象字节正确；这样可以避免旧 owner 的在途 DELETE 破坏新 owner 的 finalization。

`committing` 接管的等待只持有 intent locator/行锁，不预先持有 Run/Step/Attempt；旧 final transaction 使用 `Run -> Step -> Attempt -> intent`，因此新 claim 不会形成 intent→Run 的反向锁。接管短事务提交后，新的业务 finalization 再从 Run 开始取得完整锁链。

### 5.2 publication Attempt 与 generic reclaim

现有 generic `reclaim_expired_research_steps` 必须增加一条窄范围 invariant：当 `artifact_publisher` Attempt 存在 `status <> 'absent'` 的 publication intent 时，generic reclaimer 不得把该 Attempt 标记为 `abandoned`、不得重排 Step，也不得改变 Run。检查必须遵守 `Run -> Step -> Attempt -> intent` 锁序；intent 是 nonterminal 或 committed 时，该 Attempt 交由 publication reconciler。

Publication reconciler 可以在普通 Attempt lease 已过期后终结原 Attempt，但仅限专用 command，并且必须同时证明：

- Step 仍是同一 `artifact_publisher`，`current_attempt_number` 仍对应 intent 的 Attempt；
- 没有 replacement Attempt，Run 未处于冲突 terminal 状态；
- intent 仍是 `(run_id, final-report)` 唯一非 absent 责任；
- intent generation、token、DB-time expiry 有效；
- final payload/current object 或 compensation precondition 全部通过。

这是对“过期 Attempt 不得完成”的现有规则唯一获批例外。普通 completion/failure/reclaim 仍只认 Attempt lease；迟到原 Worker 必须同时被旧 Attempt lease 和 intent generation 拒绝。

### 5.3 公平性与锁证明

Dispatcher 对 publication intent 使用有界配额：每个循环每轮最多处理一个 intent，随后至少执行一次普通 Step 扫描；不得因持续 reconcile backlog 永久饿死 ingestion 或其他 Research Step。真实 PostgreSQL 验收必须并发运行 claim、finalize、generic reclaim、cancel、compensate 和 orphan sweep，记录 `pg_locks`，并证明没有 `40P01` deadlock 或未解释的 `55P03` lock failure。

## 6. 幂等与重放语义

- 原发布进程、同一 Attempt 重试和独立 reconciler 都通过 `attempt_id` 找到同一 intent，不重新生成 Artifact ID、对象前缀或 payload；每次 ownership generation 只生成自己的完整对象键；
- 多个失败 Attempt 可以留下 `absent` 历史 intent，但 partial unique index 保证同一 Run 只能有一个 `status <> 'absent'` intent；
- `ResearchArtifact(run_id, logical_key)` 唯一约束和 Research Event `(run_id, dedupe_key)` 唯一约束继续阻止重复用户可见结果；
- 已是 `committed` 的 intent 重放直接返回原 `artifact_id`；
- 已明确 `absent` 的旧 intent 不得复活，新的 Step Attempt 创建新 intent；
- prepare 或 final commit 结果为 unknown 时，调用链返回内部 `PublicationResult.reconcile_pending(intent_id)`，不调用通用 `fail_research_step`；原 Attempt 保持由 intent 负责，直到 reconcile 把它原子推进到 succeeded 或在明确 absent 后原子执行 disposition；
- Run 已完成时，任何迟到 Attempt、重放或 reconcile 都只能核验同一个 final Artifact，不能回退 Run 或补发 Event。

`PublicationResult` 是 Worker 内部 port 合同，不进入 HTTP/OpenAPI/SSE：

```text
PublicationResult
  committed(artifact_id)
  reconcile_pending(intent_id)
```

`SqlResearchLedgerAdapter.publish_final` 不再无条件把结果解析为 Artifact UUID；publisher handler 必须在通用异常捕获和 `_persist_step_failure` 之前单独处理 `reconcile_pending`，把本次 `process_one` 视为已处理但发布仍 pending，不产生用户 Event。也可以使用语义等价的专用 `ResearchPublicationDeferred(intent_id)` 控制信号，但不得让它落入通用异常归一化路径。

## 7. Worker 责任边界

API 继续拥有 Alembic/schema governance 和公开 HTTP/auth；`citeframe_persistence` 继续拥有唯一 ORM/Base；`citeframe_research_persistence` 负责 intent commands、状态机、锁和 fencing；Worker composition root 注入 Session 与带硬超时的对象存储 put/get/list/delete adapter，并运行 reconcile 与 terminal orphan-sweep 调度。

Publication saga 是多事务 orchestration，必须显式拥有 prepare、`committing` marker、finalize/compensate 各次 commit 及其 unknown 处理。不能把它包在一个在函数返回后才自动 commit 的普通 `ResearchUnitOfWork` 中，否则真正的 commit 异常会绕过 `PublicationResult`。实现可以新增 saga-specific session orchestration，或让每个 publication command 各自使用独立 UoW；无论哪种方式，调用层都必须接收到实际 commit owner 产生的 `committed/reconcile_pending` 结果，外层不得再执行含未提交写入的隐式第二次 commit。

建议把 publication reconcile 作为现有 Worker 的内部工作种类，不新增独立服务。每个长驻 dispatcher loop 以有界配额执行 intent claim，使崩溃后的 intent 能被任意 Worker 接管，同时保留普通 Step/ingestion 进度。对象 adapter 必须能按 intent prefix 枚举 generation key；当前 `upload_bytes`/`delete_object_if_exists` 的无条件固定-key 接口不足以证明对象侧 fencing，不能原样冒充新合同已经成立。

## 8. 发布与回滚影响

### 8.1 上线顺序

1. 先执行 additive migration，新增表、约束和索引；现有已完成 Run 无需回填；
2. graceful drain 并停止全部旧 Worker，而不是依赖当前不存在的 publisher-only 开关；API 可继续提供不触发新 Worker execution 的读服务；
3. 确认没有旧版正在运行的 publisher Attempt；若存在，先让它在旧路径明确完成，或停止在尚未 upload 的安全点并记录恢复状态；
4. 部署所有强制 intent-first、理解 `PublicationResult`、generic-reclaim 例外和 generation object key 的 API/Worker 版本；
5. 核对 Worker instance/version 清单，证明没有旧 Worker 后才启动新 Worker；整个切换窗口禁止旧/新 Worker 混跑；
6. 新代码只为新的 final publication 创建 intent；部署前已经完成的 Run 不变；
7. 上线后监控非终态 intent 数、最老 pending 时长、claim heartbeat/fencing、reconcile 成功/退避/补偿计数、generation 对象数和 orphan sweep；
8. 真实 PostgreSQL + MinIO 故障矩阵通过后，才允许把 R2 artifact 的 `coverage.r2Complete` 设为 `true`。

### 8.2 回滚边界

回滚时继续运行新 Worker，直到所有 intent 都为 terminal、所有 `committed` 只剩 adopted key、所有 `absent` prefix 为空，并在最大存储请求观察窗口后复查；然后 graceful stop 全部新 Worker，确认没有运行中的 publisher/reconciler，再部署旧 Worker，禁止新旧混跑。代码回滚可以保留只含 terminal 历史的 additive 表；数据库 downgrade 不是常规回滚步骤，只有 intent 行已按明确数据保留流程清空且没有对应 generation 对象时才允许执行。

这不是需要双写旧/新业务 payload 的兼容迁移；公开 API 和最终 Artifact 表保持原合同。风险集中在内部发布过程跨两个数据库事务和一个对象存储操作的恢复责任。

## 9. 批准后必须通过的验收

### 9.1 自动化与合同测试

- migration upgrade/downgrade、metadata parity、约束与索引测试；
- `LargeBinary -> bytea/blob`、`JSON_DOCUMENT -> jsonb/json` parity、16 MiB payload 边界和 `length(payload_bytes)` 一致性；超限必须在零 intent/零 object 下使用非重试安全码失败；
- prepare 必须先于 upload；prepare 后、upload 前崩溃，以及 prepare commit 响应丢失时幂等找到同一 intent/payload；
- 同一 Attempt 重入、多个 Worker 同时 claim、DB-time heartbeat、claim 到期后接管、迟到 generation fencing；
- claim 分别在 `prepared`、`uploaded`、`committing`、`compensating` 到期时接管；逐项断言原子状态回退、current key/generation 和 terminal predicate recheck；
- generation-scoped object present/absent/hash mismatch、put/get/list/delete 暂时失败与响应丢失；
- `uploaded -> committing` marker 成功/响应丢失，以及 final commit success/response lost/verification unavailable/later restored；
- unknown outcome 不调用通用失败路径，不提前删除对象，不重复模型或工具调用；
- nonterminal publication Attempt 到期时 generic reclaimer 让权，replacement Attempt 不得出现；
- committed/absent 两种收敛路径；absent、Attempt/Step/Run disposition 和 Event 在单事务内经全部 kill point 重启仍原子；
- `research_publication_compensated` 在次数有余额时自动 requeue、次数耗尽时 `awaiting_retry`、cancellation 时走既有取消路径；
- Artifact、Claim/Prompt 映射、Step/Attempt/Run 终态与三个 Event exactly once；
- 物理对象只宣称 generation-isolated/effectively idempotent；terminal sweep 保留 adopted key、清理旧 generation 和迟到 PUT；
- cancellation 与 pending publication、Worker shutdown、lease expiry、重复 reconcile 的竞态；
- API schema、Web contract、Research view/SSE replay 与现有 deterministic browser flow 不变。

### 9.2 真实 PostgreSQL 17.11 多进程场景 K

场景必须使用至少两个独立 OS Worker 进程和独立 PostgreSQL backend，并对 MinIO 与数据库连接分别注入可控故障：

1. intent prepare 已提交、任何对象上传尚未开始时杀死原 Worker；新 Worker 必须只使用 frozen `payload_bytes` 上传相同 SHA-256；
2. prepare commit 响应丢失且即时 verification 不可用；恢复/重放不得产生第二个 intent、Artifact ID 或 object prefix；
3. 对象 PUT 响应丢失、对象实际 present/absent 两个分支，以及 `uploaded` marker 响应丢失；
4. `committing` marker 提交响应丢失；恢复后必须由行锁 oracle 判断 marker 状态，不能误删或误失败；
5. 原 PostgreSQL final transaction/backend 尚未结束时启动新 reconciler；新进程必须从 Run 开始取锁并等待 intent 行锁，不能把未决事务当 absent；
6. final commit 实际成功但响应丢失、即时 verification 不可用；恢复后确认 intent、同一 Artifact、映射、终态和三个 Event 各一次；
7. final commit 实际未发生且 verification 暂不可用；恢复后优先用同一 frozen payload 和新 generation 重试 finalization，不因 rollback/unknown 直接补偿；
8. generic Attempt lease 到期、generic reclaimer、intent reconciler 三方竞态；不得 abandon/requeue publication Attempt 或创建 replacement Attempt；
9. Worker A 已开始 generation 1 PUT 后 claim 到期，Worker B 用 generation 2 完成；A 迟到 PUT 只能生成旧 key，不能覆盖 adopted key，terminal sweep 最终删除旧 key；
10. 旧 generation DELETE 迟到时不能删除新 generation/adopted key；真实 MinIO hash mismatch、PUT/DELETE response lost 均必须收敛；
11. renderer/Worker 版本切换后，新进程不重新 render，直接从 durable payload 上传 byte-identical 报告；
12. cancellation 或永久 integrity 冲突进入 `compensating` 后，在每次 list/delete、prefix-empty 确认和数据库收敛事务前后杀死 Worker；重启后不得先有 `absent` 再遗留 running Attempt；
13. `absent` disposition 覆盖 Attempt 次数有余额、次数耗尽和 Run cancel 三种分支；数据库行与既有 Event 必须同事务一致；
14. 两个 Worker 同时 reconcile 同一 intent、DB-time heartbeat、claim expiry 接管和 stale token/generation；只有合法 generation 能回写，stdout/argv/artifact 不得出现 token；
15. claim、finalize、generic reclaim、cancel、compensate、orphan sweep 并发运行；记录 `pg_locks`，证明 `40P01=0`、未解释 `55P03=0`；
16. committed terminal sweep 保留 adopted key 并删除其他 generation；absent terminal sweep 删除整个 prefix；覆盖最大存储请求观察窗口后再次确认无迟到孤儿；
17. 重复 reconcile、重复 commit 响应丢失和重复进程重启，最终仍只有一个 final Artifact、一组终态 Event，所有 intent 均为 `committed` 或 `absent`；
18. 强制清理临时数据库成功，artifact 不含数据库密码、lease token、对象存储凭据或未脱敏连接信息。
19. 分别在 `prepared`、`uploaded`、`committing`、`compensating` 令 claim 到期并接管；`uploaded`/`committing` 必须原子回退 `prepared` 且换成新 current generation，`compensating` 必须保留状态并清空 current 字段；
20. `committing` 接管覆盖旧 final backend 仍运行后 commit、仍运行后 rollback、接管等待期间已变 `committed` 三个分支；验证 predicate recheck、对象哈希、Artifact/Event exactly-once 与旧 generation terminal sweep。

R2-K 通过后必须重新运行 canonical R2 A-L；只有全部场景通过、独立 Critical 审计为 `ACCEPT` 且四级 finding 均为零，才能生成最终 artifact、设置 `coverage.r2Complete=true` 并解除 W1 的 R2 前置阻塞。测试 stub 和 deterministic provider 仍只作为工程证据，不能宣称模型质量或用户价值。

## 10. 所有者需要确认的决定

建议批准的决定为：

> **批准 A-DATA：允许 Citeframe 为 R2-K 新增内部 `research_publication_intents`、16 MiB 上限的 frozen canonical report bytes、generation-scoped 对象键、Alembic migration、ORM/commands、Worker reconcile/orphan sweep；允许 publication Attempt 在存在 nonterminal intent 时由专用 DB-time fencing recovery 接管而不进入 generic reclaim；允许确认补偿为 absent 后使用新的 retryable 安全码 `research_publication_compensated`，并按本文约束原子更新 Attempt/Step/Run/Event；允许超出 16 MiB 的报告在写 intent/object 前使用非重试码 `research_publication_payload_too_large` 失败。公开 HTTP/OpenAPI、权限、报告内容、Research 状态/Event 类型及 schema 保持不变。**

在收到含义等价的明确批准前，生产 schema、ORM、publication/save/retry/replay 路径不得修改，R2 继续保持 `coverage.r2Complete=false`。
