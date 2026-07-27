# V4 R000 合同审批记录

> 合同决策状态：**APPROVED**。
>
> 记录持久化状态：**DURABLE / COMMIT A REFERENCED**。
>
> 实现授权：**NO**。

## 1. Owner 决定

| 字段 | 值 |
| --- | --- |
| Owner | Citeframe repository Owner（主会话直接决定；本地 transcript 不含独立账号标识） |
| Decision timestamp | 2026-07-27, Asia/Shanghai（本地 transcript 未暴露客户端消息的精确时分秒） |
| Requested decision | `批准 AP001-AP012 推荐默认；例外：无。` |
| Owner response | `批准` |
| Approved AP IDs | `AP001-AP012` |
| Decision meaning | 全部采用 [r000-approval-package.md](r000-approval-package.md) 中对应的推荐默认 |
| Exceptions | 无 |
| Implementation authorized | **NO** |

Owner 的回复发生在上述明确请求之后，因此只关闭 `AP001-AP012` 的合同语义，不扩大为实现、部署或真实
provider 启用授权。任何未来例外或合同语义修改都必须产生新的审批输入、hash、独立审查和审批记录，不能
改写本次决定。

## 2. 获批输入

以下 SHA-256 是 Owner 决定时看到并批准的精确内容。三个输入文件保持原样；其中的 `OPEN / UNAPPROVED`
文字记录的是审批前输入状态，不覆盖本记录中的批准事实。

| 输入 | SHA-256 |
| --- | --- |
| [data-state-contract-draft.md](data-state-contract-draft.md) | `a55b815a55e819820c60a6fe030b8b0fabb01a2a0cd1231e214d82293b51d72e` |
| [api-event-tool-contract-draft.md](api-event-tool-contract-draft.md) | `cf445bb46d99cef4f62c88e87cb5d0362ef32d871cba2495f90d973bd8c5fcd7` |
| [r000-approval-package.md](r000-approval-package.md) | `158ea0e6cab1a3db6a35b61bb78bcf440eac0ded2640603ac7060507967558d0` |

| Git 字段 | 值 |
| --- | --- |
| Contract snapshot commit A | `466e5a3` |
| Approval record commit B | `THIS RECORD'S CONTAINING COMMIT; SHA INTENTIONALLY OMITTED` |
| Decision-time HEAD | `9aa3bf27ec97a9c0da14cf9e57db38ca0e5a5c3c` |
| HEAD qualification | 该 HEAD 不包含工作树中的获批输入，不能充当 approval commit |

Git commit 不能在自身内容中记录自己的 SHA，因此恢复点采用两阶段模型：

1. commit A 固化三份获批输入及其所依赖的经审计当前基线，但不包含对 commit A SHA 的自引用；
2. 取得 commit A SHA 后，把 `Contract snapshot commit A` 的 pending 值替换为该 SHA，同时将本记录状态改为
   `DURABLE / COMMIT A REFERENCED`，把 `Approval record commit B` 改为不含 SHA 的
   `THIS RECORD'S CONTAINING COMMIT; SHA INTENTIONALLY OMITTED`，再以 commit B 固化本审批记录和同步后的
   `spec.md`、`plan.md`、`tasks.md`、`requirements-discovery.md`；
3. 本记录不记录 commit B 自身 SHA；commit B 可从 Git 历史定位，避免不可解的自引用。

commit A/B 都需要 Owner 单独授权。第 2 步的状态、哨兵和 A SHA 回填是唯一允许的审批记录闭环更新，不能改变
获批语义。授权 push 仍是另一个外部动作。

## 3. 获批合同范围

| ID | 获批主题 | 结果 |
| --- | --- | --- |
| AP001 | 状态机与 PlanRevision/ExecutionSnapshot 双快照边界 | approved as recommended |
| AP002 | Workspace 读取、creator 决策与 owner 成本/安全终止权限 | approved as recommended |
| AP003 | 最多 5 次 PlanRevision、HITL、冲突动作、取消与人工 retry | approved as recommended |
| AP004 | server-resolved provider profile、最小外发数据与 fail-closed 数据边界 | approved as recommended |
| AP005 | USD 预算、并发、timeout、attempt、配额与 reserve/reconcile 账本 | approved as recommended |
| AP006 | normalized Claim/Evidence provenance 与 branch-scoped Evidence-only tools | approved as recommended |
| AP007 | Artifact 可见性、独立 final report 与脱敏 trace export | approved as recommended |
| AP008 | Run 保留、源删除后最小快照与 Workspace 两阶段 hard delete | approved as recommended |
| AP009 | 10,000 Event 上限、Research SSE replay 与 mutation 幂等 | approved as recommended |
| AP010 | deployment-controlled Workflow/Prompt 发布、retire 与不可变历史 | approved as recommended |
| AP011 | additive migration、restore-first downgrade 边界与恢复 oracle | approved as recommended |
| AP012 | 敏感数据、安全日志、R700/新模态延后与分阶段实现授权 | approved as recommended |

不可拆开的语义 Oracle 继续以审批包第 2 节为准：Quick Answer 合同不变；Deep Research 显式 opt-in；
PostgreSQL 账本是业务事实源；Agent 只使用 `evidence.search/evidence.load`；unsupported Claim 不发布；
Research SSE 与 Chat SSE 分离；R700 和候选新模态保持 deferred。

## 4. API Owner 决策与 data 映射

下表逐项关闭 API 草案的 `API-O001-API-O010`。全部决定日期均为 2026-07-27，Owner 均采用审批包中的
推荐默认，reviewer 均为 `m403_review`；data 关联显式列出，不能按编号猜测。

| API ID | Owner 决定 | Data decision 映射 | AP |
| --- | --- | --- | --- |
| API-O001 | 当前有效 member 可读同 Workspace Run/Event/user Artifact；internal/Prompt/provider audit 不开放 | `O015/O020` + data 12.1 | AP002 |
| API-O002 | creator 裁决 conflict、人工 retry 和普通取消；owner 仅以 `cost/security` 终止；conflict action 保持 closed set | `O003/O004/O005` | AP002/AP003 |
| API-O003 | server 解析唯一 approved profile；只外发最小 question/Prompt/text excerpt；policy 不完整 fail closed | `O010/O011/O020` | AP004 |
| API-O004 | 单一 USD ledger；批准 planning/execution 上限、3 researcher、timeout/attempt；不 top-up | `O003/O004/O012/O013` | AP005 |
| API-O005 | v1 仅 Run archive；源删除保留最小 typed snapshot；Workspace hard delete 两阶段清理 | `O007/O008/O009/O017/O020` | AP008 |
| API-O006 | Event 与 Run 同寿命、每 Run 10,000；idempotency TTL 24h；无效历史 cursor 返回 410 | `O009/O014` + data 11.2 | AP009 |
| API-O007 | 四类 user Artifact、两类 internal Artifact；owner 只可显式请求脱敏 trace export | `O009/O015/O016/O020` | AP007 |
| API-O008 | 每 Run 最多 5 个 PlanRevision；保留 comment 与旧 Artifact/Decision；planning 使用冻结上限 | `O002/O004/O012/O021` | AP003/AP005 |
| API-O009 | 每用户最多 2 个、每 Workspace 最多 10 个非终态 Run；超限 429 | `O012/O013` + data 5.1 | AP005 |
| API-O010 | creator membership 移除时取消非终态 Run、断开 SSE、不转交 owner | `O005/O009/O015/O020` + data 12.1 | AP002 |

## 5. 获批合同清单

以下内容按第 2 节 hash 对应的原文获批，未作修改：

| 合同面 | 获批范围 |
| --- | --- |
| Fields and relations | data contract 第 2-9 节的字段、必填/可空、唯一键、外键、关系、敏感字段与 retention class |
| Enums and transitions | data contract 第 3、10 节的 closed enums、Run/Step/Attempt/HumanDecision 合法迁移和终态 |
| Snapshot/replay/idempotency | data contract 第 11 节的 PlanRevision/ExecutionSnapshot、历史 replay、原子边界和公开 mutation 幂等 |
| Public DTO/API | API contract 第 1-5、13 节的 envelope、DTO、create/list/read/cancel/decision/retry/artifact endpoint 与错误矩阵 |
| Research SSE | API contract 第 8 节的独立 endpoint、持久化顺序、exact 15-event allowlist、`Last-Event-ID` 和 410 语义 |
| Evidence tools | API contract 第 9 节的 `evidence.search/evidence.load` schema v1、opaque handle、tool error 与 prompt-injection boundary |
| Provider/budget/retry | API contract 第 10 节及 AP004/AP005 的 approved profile、最小数据、预算、timeout 与 retry policy |
| Retention/deletion | data contract 第 12 节、API contract 第 11 节及 AP008/AP011 的删除、备份、恢复和 downgrade 边界 |
| Quick invariants | data contract 第 13 节与 API contract 第 12 节的 Quick Chat/Citation/NoteSource/Viewer/save 不变 oracle |

R700 Evaluation persistence/API 明确不在此清单。`audio_range`、`video_range`、`heading`、`anchor`、
`workbook`、`sheet`、`cell`、`range` 只是需求发现中的候选产品定位标签，**没有**被批准为 locator kind、字段、
enum、API DTO、tool schema、database schema 或 registry entry。

## 6. 合同测试映射

以下是后续被授权实现时必须先写成可执行 oracle 的映射，不代表本轮已实现或已运行这些测试：

| Oracle | 必需测试证据 |
| --- | --- |
| Quick Chat 不变 | 现有 Chat schema/unit 全量回归；真实 Quick SSE 保持 `meta -> delta* -> citations -> done/error`；PDF/Image Citation/Viewer、NoteSource、save payload old/new 等值；Quick 请求期间 Research 表/Event 增量为 0 |
| 权限拒绝矩阵 | creator/member/owner/non-member 的 list/read/SSE/decision/retry/cancel/artifact 矩阵；跨 Workspace ID 返回安全错误；membership 移除后 SSE 断开且运行按合同取消，不发生 owner 接管 |
| 幂等与 replay | 每个 mutation 同 key/同 body 返回冻结结果、同 key/不同 body 409；Event 先持久化后推送；重复交付去重、合法 cursor 续播、gap 停止应用、过期/不可用 cursor 410、10,000 上限 |
| 源 Asset 删除 | PDF/Image fixture 删除后保留 excerpt、typed locator、regions、sourceVersions 与 Artifact hash；`sourceAvailable=false`；Viewer/load fail closed；不绑定新 generation/同名 Asset |
| Provider policy | approved profile 缺失、歧义、policy 不完整均在调用前 fail closed；payload capture 只含最小 question/Prompt/bounded text excerpt，不含 image bytes/crop、Workspace dump、object key、credential、URL；不发生任意网络/tool 调用 |
| Migration/restore | additive schema 不给 Quick/Asset/Citation/Note 增加必填字段；空表 downgrade；有数据时拒绝破坏性 downgrade；空 PostgreSQL/MinIO/Redis 恢复后核对全部行、seq、snapshot 与 Artifact bytes/hash |

R100 只实现 Research fixture、scorer 和可重放 Quick baseline；R200/R300 获得单独授权后才可把上述 schema、
API、SSE、tool 和恢复映射实现为合同/集成测试。

## 7. 评审与验证证据

| 证据 | 结果 |
| --- | --- |
| RD003 current-state review | `m403b_deploy_config` 于 2026-07-25 完成 code-backed independent re-review，PASS |
| R000 cross-contract review | `m403_review` 对 data/state 与 API/event/tool 合同完成独立复审，最终 `PASS` |
| Input hash verification | 三个 SHA-256 与审批前冻结值逐字一致 |
| Relative Markdown links | passed |
| Markdown fence balance | passed |
| Research Event allowlist | exact 15-event closed set |
| Canonical enum membership | passed |
| Decision coverage | data `O001-O021` 与 API `API-O001-API-O010` 共 31 项全部映射到 `AP001-AP012` |
| Approval writeback check | `git diff --check`、相对 links、Markdown fences、15-event allowlist、12 AP rows 和未来阶段未误勾均 passed |

R001-R006 的合同产物由获批输入关闭：固定 DAG/tool schema；实体、状态与关系；版本和 replay；权限、删除、
取消、恢复和成本；Quick Answer 不变 oracle；字段、幂等、事件与错误矩阵。迁移影响以 data contract 第 12 节
和 AP011 为准，Quick regression oracle 以 data contract 第 13 节和 API contract 第 12 节为准。

## 8. 未授权范围与下一门禁

本次批准不授权以下任何工作：

- migration、表、ORM、schema、API route、Research SSE、Worker DAG 或 Web UI 实现；
- provider credential/profile 启用、真实 provider 调用或外部网络访问；
- Quick Chat、Citation、NoteSource、EvidenceLocator、Note 保存或现有 Asset 删除语义修改；
- R700 Evaluation persistence/API；
- Markdown/HTML、DOCX/PPTX、Audio/Video 或其他新模态的 locator、schema、adapter 或入口。

门禁顺序固定为：

1. Owner 授权 contract snapshot commit A，固化三份获批输入及其经审计当前基线；
2. 在本记录回填 commit A SHA，并以 approval record commit B 固化批准事实和状态同步；
3. 单独推进并通过 R100 fixture、scorer 和可重放 Quick baseline exit gate；
4. 另行取得 R200/R300 实现授权；
5. R700 Evaluation 和每种新模态继续使用各自独立合同与进入门。

第 1-2 步已完成，R007 关闭；下一门禁是 R100 Evaluation-first，R100-R800 的实现任务仍按各自门禁推进。
