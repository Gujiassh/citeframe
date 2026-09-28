# Issue45 settlement — 独立 Critical 审查准备

日期：2026-09-29（Asia/Shanghai）

## 0. 状态与授权边界

**状态：BASELINE / ORACLE PREPARATION COMPLETE；候选实现待冻结，未审、未验收。** 本文固定旧 public 语义、锁与 rollback 边界，以及后续真实 PostgreSQL 反向 oracle。本轮没有读取施工中的 `tools.py`、新测试或开发 evidence，没有对施工候选作 PASS、APPROVE 或缺陷裁决。

- 固定旧源码：`e7b3e86ae4de70764c4d17bcbe272686c1c8063a`。PR51/45a0 的交付身份按 controller 提供记录；本轮没有查询远端 PR 或推断其 merge 状态。
- 开发 lane：`D:/Code/citeframe-lanes/issue45-research`，`work/issue45-research-memory`；原开发 `agt_d03b4a29` 唯一产品作者，原独审 `agt_26025b40` 保持独立审查。controller 负责 relay、候选冻结、复制本文和 Git/PR/CI/integration。
- 授权文档：该 lane 的 `specs/v5/memory-management/lanes/issue45-settlement-ownership.md`，本轮读到 SHA-256 `B9FB26CD86419AC515931223CB7E899FB5CFA2D576077AFF6E20D39E42E4FF96`。
- governing contract：canonical `lanes/issue45-research.md`，SHA-256 `249C97FD1705AFCA6481566FD49F1511A6D0E2F82E2C5933BEAD80212FBB89F4`，§8.3；仅本次 grant 的事务内 settlement 提取。Hegel 已确认 #40 不占此 package tools/tests，按 controller 授权记录；不自行扩大文件所有权。
- 产品 grant 仅 `packages/research-persistence/src/citeframe_research_persistence/tools.py` 与新 `packages/research-persistence/tests/test_memory_tool_settlement.py`，及开发自有 evidence。固定旧树中此 package 尚无 tests 目录；若实际使用不同测试目录，须先由 controller 澄清 grant。
- 本审查仅新建 canonical `specs/v5/memory-management/reviews/issue45-settlement.md`。没有产品、CI、旧 review、共享 spec/workbench 或 Git 状态写入。

完整目标仍为所有主 dispatch/recovery 前同 live Attempt 自动压缩、两次 crossing 无新增用户消息，保持冻结证据、phase-root 预算、cancel/unknown/publication，以及 A1 choice2 全部私有数据排除。本次提取只准备单事务调用能力，不实现该完整目标，不扩大 schema、reclaim、planner sidecar、#43 ABI、tool names 或任何 runtime 激活权限。模型与 UI46 访问均不在本轮范围。

## 1. 固定旧源码与证据身份

以下均以 canonical 仓库对象库的 `git --no-optional-locks show <完整固定 SHA>:<path>` 读取，未 checkout、未导出覆盖工作树。SHA-256 使用 `subprocess.check_output` 所得原始 blob bytes 计算，避免 PowerShell 换行转换。路径前缀：

- `N/` = `packages/research-persistence/src/citeframe_research_persistence/`
- `P/` = `packages/backend-persistence/src/citeframe_persistence/models/`
- `A/` = `apps/api/src/ai_pdf_api/services/research/`

| 固定基线文件 | SHA-256 |
|---|---|
| `N/tools.py` | `4150B842B6FEC30057E9B0A7E332AD1C45E9A165652B29AEB5021E83E525BA02` |
| `N/locks.py` | `2489458D22B6557024002100E7EE03594DC81C3290883F0B1459B827B84F171B` |
| `N/lease.py` | `C500FA36F6A65A7CADEFD588ADEF7D2ED7BFB20D445AEBF97BA64C4DC7B1E44A` |
| `P/research_execution.py` | `45476FD49ADDB13867AD98CA960437A1A24FDD57856BC89EF5BAD7F65F7340EC` |
| `A/research_worker_tools.py` | `4FD79E2358043140A246E9A0B03843B9C4A61877A75E0AE2638B0DCAE31754E3` |
| `apps/api/tests/test_research_worker_budget_recovery.py` | `AAF68419E6660D0E3911F6D45C0F56A2F4BE1F0C480360C1B30AF03DDADF9BCA` |
| `apps/api/tests/research_worker_test_support.py` | `BDBC5FFA9D2C764F5A320C9F673921C42C935CB4606329F67C77BEB6A55E8B03` |
| `apps/worker/tests/test_r2_postgres_budget_contract.py` | `76789CDAA32A45CF0D20C3E7D5F20A6DC6394F2BA3111BF88F2E57B12724AE45` |

补充只读核对：固定旧 `A/research_worker_evidence.py` 的原生 callback，以及 `infra/scripts/r2_scenario_l_budget.py` 的 PG proof 结构。本轮未执行这些脚本。

### 两层 public 必须区分

1. **本次 grant 的 neutral public**：`N/tools.py::complete_tool_call`。无 commit；只有自己的 settlement try 内 `Exception` 才显式 rollback。
2. **未授权修改的 API compatibility facade**：`A/research_worker_tools.py::_commit_command` / `complete_tool_call`。调用 neutral 命令，成功后 commit；对命令或 commit 的 `Exception` 调用 rollback。因此 facade 的 precondition 失败也会 rollback，callback 失败可能经过 neutral 与 facade 两层 rollback。

后续 public parity 必须直接测 neutral public，再单独保留 facade regression。仅从 facade 观察不到 neutral precondition 是否被错误纳入 rollback 范围。

## 2. neutral public 的精确旧语义

固定 `N/tools.py:140–171`：签名为 `complete_tool_call(db, *, tool_call_id, status, complete=None, error_code=None, error_message=None, now=None) -> None`；callback 类型 `Callable[[Session, ResearchToolCall], int]`。

### 2.1 调用顺序、异常优先级及事务边界

| 顺序 / 位置 | 旧行为 | neutral public 显式 rollback |
|---|---|---|
| 1 / 151–152 | status 必须为 succeeded / failed / cancelled / abandoned；否则 `ValueError("invalid tool terminal status")`。先于 call ID 查询，即使 call 不存在或已 terminal 也先报此错。 | **无**；未进入 try，也不调用 callback |
| 2 / 153 | `_tool_call_chain` locate、锁定刷新、校验完整链。缺失/错链通常为 `ResearchError("research_state_conflict", "Research tool call chain is invalid.", 409)`；该过程自己的 SQL/ORM 异常也在 public try 外。 | **无** |
| 3 / 154–155 | 刷新后的 call.status 必须为 requested 或 running；否则 `ResearchError("research_state_conflict", "Research tool call cannot be completed.", 409)`。链校验优先于 already-terminal。 | **无**；callback 不执行 |
| 4 / 156–168 | callback → 设置 terminal payload → 一次计账 → 最后 `db.flush()`。 | 成功无 rollback、无 commit |
| 5 / 169–171 | 上述 try 中的 `Exception` 调用 `db.rollback()` 后原异常继续抛出。包括 callback、字段/算术及最终 flush 的错误。 | **有**，整个 Session 当前事务；没有局部 savepoint 隔离 |

`except Exception` 没有捕获所有 `BaseException`。不要通过 broad try 或另一个 wrapper 静默改变异常类别与 rollback 时机。需要区分“函数没有显式调用 rollback”与“SQL 错误后事务仍可用”：链查询失败可能已经使 PostgreSQL 事务进入失败状态，仍由 caller 清理。

precondition 也可能已获取锁；其失败不会由 neutral public 自动释放。定位/父链的 no_autoflush 只覆盖明确的代码段，call/ledger 查询不在那些代码段内。在 Session autoflush=True 时，不能把“precondition 在 try 外”写成“该阶段绝无 flush/SQL/副作用”。后续对照应记录旧/新相同 Session 配置和实际 SQL 顺序。

### 2.2 terminal payload 与一次算术

callback 存在且 truthy 时，在 call 仍为原 requested/running、原计数尚未由 settlement 更新时调用 `complete(db, call)`，使用相同 Session/已刷新 native call。没有 callback 时 result_count=0；有 callback 时原样使用返回值，没有新增类型转换、截断、负数检查或按 terminal status 强制清零。

| 对象 | 旧 public 直接修改的字段 |
|---|---|
| ResearchToolCall | status=传入值；result_count=callback 返回或0；error_code/error_message=原参数（含 None）；finished_at=`now or datetime.now(UTC)`，求值在 callback 后 |
| ResearchBudgetLedger | reserved_tool_calls −1；actual_tool_calls +1；state_version +1；updated_at=call.finished_at |
| ResearchStepAttempt | tool_call_count +1 |

四个 terminal status 都消耗已接纳的一次 slot，cancelled/abandoned 也不退款。requested 与 running 都可完成。最后一次显式 flush 位于所有上述更新之后，随后返回 None。callback 自己可以先 flush 原生结果，仍留在同一事务。

本函数没有直接改 run/step status、lease、provider/token/money 计数、请求哈希/工具身份/started_at、publication 或事件；callback 产生的业务写入须单独观察。对无 now 情形只固定调用时序/时间关系，不要求两次真实执行的墙钟相同。

重复完成同一 terminal call 会在 try 前报 already-terminal，不是幂等成功，也不得二次 callback/计费。当前 public 不新增 active lease、membership、当前 Attempt number 或 run status 校验；它依赖链完整性与 call 状态。把 `_active_attempt_chain` / `_locked_attempt` 替换进来会引入新准入语义，超出本次保真提取。

## 3. 固定锁链及权限上限

`N/tools.py::_tool_call_chain`（74–137）和 `N/locks.py::lock_attempt_chain`：

1. no_autoflush 下无锁读取 ToolCall 的 run/step/attempt/execution_snapshot ID，仅作 locator。
2. `locate_attempt` 无锁读父 ID；随后 **Run → Step → Attempt**，均 `FOR UPDATE` + `populate_existing=True`，按真实父链约束 ID/workspace。
3. **ToolCall** `FOR UPDATE` + populate_existing：同时匹配最初 locator 的 call/run/step/attempt/snapshot。
4. **BudgetLedger** `FOR UPDATE` + populate_existing：由刷新 call.execution_snapshot_id 选择。
5. `db.get(ResearchExecutionSnapshot, ...)` 读取 snapshot；该 helper 没有显式对 snapshot 加 FOR UPDATE。
6. 检查 call/ledger/attempt/step/run/snapshot 存在；locator 与锁定对象一致；Attempt→Step、Call→Attempt/Step/Run、Step→Run/Snapshot、Snapshot→Run；call/step/attempt/snapshot/ledger workspace 与 run 一致，ledger.run_id 与 run 一致。

有锁实体顺序为 **Run → Step → Attempt → ToolCall → BudgetLedger**。这些链锁默认不 skip_locked；父锁先于子锁，locator 不产生可复用 authority。完整 helper 没有给调用者 source/body/read 权限，也没有调用 membership 验证。快照普通读、可触发的 implicit FK locks 与 callback SQL 必须在 PG trace 中如实记录，不能宣称这里只读/锁五张表。

### 未来 private inner 的审查条件（未冻结具体签名）

- 内部函数自身及其调用路径不 commit、rollback、关闭/替换 Session，不开独立事务来隐藏 caller 的失败；使用 caller 同一个数据库事务。flush 可以存在，public 的既有 flush 位置与次数语义须保留。
- 相关 terminal、chain 与 single-settlement 不变量仍成立，public precondition 的异常和 rollback 分界仍与第2节一致。若拆分导致 precondition 从 try 外移到 catch 内，属于必须修复的 public parity 回归。
- 接收 ID 时应走真实 native 查找/锁定校验；若接收预锁定对象，须有代码内可审计的受控获取路径及一致性验证。`Session` 归属、ORM persistent 标志、相同 UUID 或 caller 自称 locked 都不足以证明已按 native 顺序获取锁。foreign/detached/stale/fabricated row 不能充当 authority。
- 不能为了复用 arithmetic 而凭空引入 planner execution row、第二 ledger、返还 slot、source issuer 或新 replay 命令。§8.3 后续 planner/reclaim 内容不因这次函数提取获得实施授权。
- 可信 callback 自身也须遵守外层事务契约。该函数提取无法原子回滚任意网络、对象存储或 callback 自行 commit 的外部效果；本次 PG oracle 只证明同 Session 的原生数据库写入。

## 4. 现有测试能支持的范围

- 固定 `apps/api/tests/test_research_worker_budget_recovery.py:298–367` 覆盖 begin + succeeded(result_count=3) + failed(default0) 的预算/Attempt 计数。这些调用来自 API facade。
- 同文件 `:700–762` 记录 ORM statement 的锁顺序与 populate_existing。
- fixture `research_worker_test_support.py:94–105` 使用 **SQLite 文件、autoflush=False**。上述测试不能证明 PG 实际行锁、等待者、事务可见性或 private caller rollback。
- `apps/worker/tests/test_r2_postgres_budget_contract.py` 是 source/adversarial pure-oracle 测试，读取 `infra/scripts/r2_scenario_l_budget.py`；文件名含 PostgreSQL 不能替代真实数据库运行记录。

上述测试本轮均未运行。后续需要扩展独立 package tests，直接导入 neutral 函数，保持 API facade 原行为不变；不更改现有测试、fixture、CI 或服务 runner 来迁就候选。

## 5. 后续真实 PostgreSQL 反向 oracle（全部待执行）

### 5.1 统一装置与观测要求

在 controller 批准的隔离测试数据库中，用固定 native schema/迁移和有效 native fixtures。记录服务器版本、隔离级别、schema/migration identity、旧/新精确源码 SHA、实际 import 路径及命令。不得使用 SQLite fallback、修改 CHECK/FK/trigger、新增产品 schema 或把一切包在同一外层测试连接的自动回滚内冒充真实可见性。

提交 fixture 基线后再开始待测事务。预先创建合法 run/snapshot/step/attempt/ledger 和 requested/running call，并使 reserved_tool_calls 与真实预留一致。冻结 now、error payload，计数可先非零以捕获错误“归零”实现。callback 写入现有 native 结果表：例如有效 evidence handle 对应的 ResearchToolCallInputHandle，或合法 evidence snapshot/handle；不引入 fake sidecar/schema。输入数据保持公共合成内容，不读取私有业务数据。

至少两个独立物理连接/Session：S1 执行，S2 观察，必要时 S3 竞争。观察事务使用新快照/READ COMMITTED，禁止以 stale identity map 判断数据库结果。对 call、ledger、attempt、callback result 行进行完整 before/inside/after 投影，比较所有修改字段以及不应变化的其他字段；hash 仅索引原始记录。事务事件与 SQL trace 辅助证明 COMMIT/ROLLBACK、锁语句、flush 边界和 callback 次数；不把 spy 计数当唯一 PG 证据。

### 5.2 矩阵与反例判据

| ID | 必须执行的对照 / 反向情景 | 判据与所捕获回归 |
|---|---|---|
| S45-P01 public payload parity | 旧/新 neutral public，requested/running × 四 terminal statuses × 无 callback/返回0/返回非零；固定 now、None/非空 errors。 | callback 参数/调用次数、完整 native 字段、一次算术、flush 后状态、返回 None 一致。失败类 status 不应擅自强制 result_count=0 或退款。success 在 S1 可见但 S2 仍见基线，证明 neutral 无 commit；caller commit 后 S2 才见全部结果。 |
| S45-P02 precondition precedence | invalid status + missing ID；valid status + missing/wrong chain；terminal + wrong chain；valid chain + already-terminal。S1 先写入并 flush 一个独立合法 sentinel。 | invalid status 优先且不查链；chain 优先于 already-terminal；callback均0。neutral public不显式 rollback，普通业务校验失败后 caller 可继续 commit sentinel；相关 native settlement 不发生。不要经 facade 测这一判据。 |
| S45-P03 callback failure | callback 写合法结果并 flush 后抛自定义 Exception；另一次在写入前抛错。S1 提前 flush sentinel。 | 旧/新 public 都 rollback 整个事务，原异常继续抛出；fresh S2 见 call/ledger/attempt/result/sentinel 全为基线，Session 经 rollback 可复用。防止只撤销结果或把 public 改成不 rollback。 |
| S45-P04 actual PG flush failure | 用现有约束制造最终 flush 的真实 IntegrityError，例如 callback 加两个同 tool_call/input_order、不同合法 handle 的输入行（冲突 `uq_research_tool_input_handles_order`），callback本身不flush。 | 进入 settlement 后真实数据库拒绝最终 flush；public显式rollback。四类写入及提前 sentinel 全撤销，保留原异常类型/SQLSTATE，后续新事务可用。spy 人工抛异常可补时序测试，不能替代此 PG 失败。 |
| S45-P05 private success + outer rollback | 冻结后真实 private inner 使用受控锁链，callback 写合法结果并 flush；inner成功，S1随后主动rollback。 | inner返回时 S1能看到 call/ledger/attempt/result 全部变化，S2未见；caller rollback 后 fresh S2四类写入全恢复，提前 sentinel 也撤销。任一持久残留抓出隐藏commit或独立Session。 |
| S45-P06 private callback error owned by caller | callback写合法结果并flush，再抛普通应用 Exception。 | inner不调用rollback/commit；尚未发生数据库错误时 S1当前事务仍可用，能观察先前sentinel/结果写入。caller负责rollback后S2全回基线。防止 private 偷用 public rollback。不要把 PG constraint error 后的 failed transaction 当作“inner 已 rollback”。 |
| S45-P07 private actual flush error | 重用 P04真实约束错误，改调private。 | 错误继续抛出；没有inner显式rollback/commit。SQLAlchemy/PG失败状态如实记录，caller rollback 后四类写入与sentinel恢复。禁止吞错、自动commit或把failed Session继续当健康事务。 |
| S45-P08 caller subsequent failure | inner成功并flush后，外层再写同事务的合法记录，再注入普通异常；另一次外层触发现有约束错误。 | 外层统一rollback撤销inner与后续写入。另设无错误的outer commit正例证明所有写入一次持久化。成功private调用不是事务完成边界。 |
| S45-P09 no double settlement | 同事务重复；以及S1/S2争同一call，S1先成功commit；再做S1先rollback的对照。 | terminal重复报既有冲突且callback0/无第二计数。竞争commit赢家只有一套结果与一次算术；失败等待者刷新后见terminal。若S1rollback，S2可按基线完成一次。两条不同call共享ledger也不得lost update。 |
| S45-P10 actual lock order / stale rows | SQL trace加独立连接持有Run/Step/Attempt/Call/Ledger中指定锁，设置有界lock_timeout与明确barrier；预加载旧call后让另一事务完成，再调用。 | 实际有锁SELECT依Run→Step→Attempt→Call→Ledger；等待可由pg_blocking_pids/锁等待或明确timeout佐证，不能只sleep推定。populate_existing刷新阻止旧running对象二次完成；第一父锁阻塞前不得先写call/ledger或调用callback。记录隐式锁，不扩大锁范围。 |
| S45-P11 foreign/unlocked authority | 依最终private签名，传错误call ID、合法但跨run/workspace的关联、旧Session/detached/伪造对象或未受控预锁上下文；构造必须符合现有数据库约束，不关约束。 | 不可借supplied ledger/attempt对象完成另一条call；callback/计账不执行。直接接收ID时须重新锁定/校验；内部预锁对象路径须证明受控构造与全部关联，不靠命名宣称安全。无法创建的DB非法形状作为结构单测补充，明确与PG情景分开。 |
| S45-P12 facade unchanged | 固定API facade + 新neutral，success / precondition / callback / commit error。 | facade继续success后commit，任何Exception时rollback；neutral自己的分界仍由直接测试证明。callback时双层rollback的既有可能性不能被误报为本次提取新增行为。 |

普通校验异常（P02）与真实数据库错误（P04/P07）必须分开观测。对SQLAlchemy flush失败，驱动/Session内部可能已对底层事务执行rollback；private“无rollback”要求是**不自行调用/接管事务控制**，不否认数据库错误处理。报告应区分函数显式调用、Session状态和服务器事务状态。

### 5.3 public 锁与错误边界的额外辨别

- 在 chain 阶段注入/复现SQL异常时，旧/新 neutral 都不得因提取而新增自己的 rollback；caller仍必须清理失败Session。
- 对普通 precondition 的锁保持，可由S2有界竞争验证：neutral失败后S1未结束事务时锁仍存在；caller结束事务后才释放。不要把这种锁保持误判为函数泄漏后自行“修复”。
- 四个terminal必须覆盖已有requested/running输入；不发明 outcome_unknown native status，保持当前CHECK和§8.2分别记录native/sidecar的设计边界。
- 不凭callback返回数模拟真实结果落库：P05–P08至少有一项真正native result表写入与四类状态全量核对。
- 本轮未决定private具体函数签名、锁上下文DTO或新增export；候选冻结后检查实际实现是否满足以上条件，不借oracle扩大grant。

## 6. 候选冻结后的原独审入口

controller 提交：完整固定候选SHA或明确的文件hash集合、相对 `e7b3e86` 的授权diff、完整新测试/evidence、真实PG命令与环境身份（无secret）、旧/新原始投影与事务记录、失败/skip信息、仍开放的限制。候选在审查期间发生变化时重新pin，不能用早期绿灯覆盖新bytes。

随后本原独审才读取candidate并独立复验；优先P02/P03/P05/P06/P09/P10，核对是否出现broad try、public内部复用API facade、inner接管Session或可信锁对象伪造。developer self-report、source hashes、SQLite/pure pass 均为辅助证据。PG不可用时报告确切命令/错误和未完成oracle，不降级为fake Session通过，不启动被拒服务/UI46、不绕权限，也不修改CI。

| 本轮事项 | 状态 |
|---|---|
| 授权边界、旧public payload / lock / rollback范围 | 已完成固定源码静态核对 |
| 真实PG反向oracle | 已准备；全部未执行 |
| 施工candidate、private实现及其测试 | 未读取、未审查，等待冻结 |
| 新实现Critical验收 | 待冻结及独立PG证据；无PASS/APPROVE |
| schema/reclaim/#43ABI/完整Research运行/模型/UI | 不在本次grant；原有mandatory gates保持 |

## 7. 执行与保全记录

已读取适用全局/workspace指令、MEMORY-POLICY、SOUL/IDENTITY；固定树仅web存在额外AGENTS，与本包无关。只读运行 `python -B D:/Code/dev-workbench/scripts/prepare_session.py --repo-path D:/Code/citeframe` 并读取其project/state/task引用；未写workbench，未读取全局私有MEMORY或daily memory。

源码读取使用canonical对象库的固定SHA `git show/grep/ls-tree`。首次从lane执行`git show`被Git dubious ownership拒绝；随后从已有可读canonical对象库读取同一固定提交，未设置safe.directory、未提权或修改Git配置。没有读取lane施工产品、运行候选测试、PG、服务、browser、model或网络。未checkout、commit、push、改index/branch、启动CI或修改产品/旧review。

写回检查：仅本新review保存已核验基线、边界和待执行oracle；controller可复制至lane并接续冻结后独审。本文件不构成开发候选验收，也不改变已有249C设计及45a0审查结论。
---

## 8. 冻结候选实际 Critical 独审 — 2026-09-29

### 8.1 最新判定

**BOUNDED APPROVE — 本次 transaction-neutral settlement 提取可在 controller grant 内接受。未发现该冻结候选范围内的阻断缺陷。** 此节更新上文“候选未审”的准备状态；上文固定旧语义与oracle保留为历史及审查依据。

已实际读取冻结产品/测试/evidence，独立运行真实 PostgreSQL 与旧回归，并补充开发套件之外的并发/外层事务反向探针。该结论限于 native execution ToolCall 的本次提取，未授权 private raw-row arithmetic helper 成为新的调用ABI，未激活 memory callbacks、planner、reclaim 或完整 Research runtime。

没有本次需要返工的实缺。CI尚未收集新package测试是明确交付缺口，由后续专用workflow grant处理；本结论不声称CI/PR/release完成。

### 8.2 冻结对象、授权与原始差异

lane：`D:/Code/citeframe-lanes/issue45-research`。读取`.git`指向及ref文件确认HEAD仍为 `e7b3e86ae4de70764c4d17bcbe272686c1c8063a`；以下为其工作树冻结候选，不把未提交文件归入该commit。授权文档仍为第0节所列原grant。

| 已审文件（lane-relative） | SHA-256，读取前及所有执行后均一致 |
|---|---|
| `packages/research-persistence/src/citeframe_research_persistence/tools.py` | `F8E02EB6C9F93DED10BF59C9B136168130591FC49B4DED0041E6115530230A51` |
| `packages/research-persistence/tests/test_memory_tool_settlement.py` | `787ED87A226F26D928C2F7505A444235F4EB658E9C252719956FFAB5F9DC27E8` |
| `specs/v5/memory-management/evidence/issue45-settlement.md` | `F3021C394463BB9FCC0F8255F37EADA1EEFBF899C135EE633ED92561F939E1B6` |

独立将固定Git blob与候选做内存diff/AST对照：原有函数仅`complete_tool_call`重组；`begin_tool_call`、`_tool_call_chain`、`restore_evidence_handles`的AST不变。另逐行核对lane `locks.py`、`lease.py`、ORM `research_execution.py` 和API `research_worker_tools.py`与固定旧对象一致。没有通过旧函数共享一个已改锁helper来制造旧/新parity。

测试内`OLD_SOURCE`已与独立读取的固定Git对象`complete_tool_call`完整源段核对一致，旧文件SHA仍为 `4150B842B6FEC30057E9B0A7E332AD1C45E9A165652B29AEB5021E83E525BA02`。额外探针直接编译该固定对象中的旧函数作为public oracle，而非仅信任开发测试内的digest常量。

### 8.3 实现判断与证据范围

| 核查项 | 判定与直接依据 |
|---|---|
| Public signature / precondition precedence | **Pass。** public先调用`_tool_call_for_settlement`，再进入try。status→完整锁链→requested/running检查的顺序与旧public相同；失效status、missing/foreign chain、already-terminal及chain SQL/autoflush异常没有被新catch包住。真实PG旧/新对照与额外owner-commit probe支持此结论。 |
| Public callback/settlement rollback | **Pass。** try仅包`_settle_tool_call`；callback、callback flush和最终flush错误仍显式rollback后抛出。真实PG CHECK失败检验事务状态和所有已写入数据；未以fake Session替代。 |
| Exact fields / clock / arithmetic | **Pass。** arithmetic helper的语句与旧try body AST一致；requested/running × 4 terminal × absent/0/3 callback的全字段PG投影一致。时间用不同seed/settlement值，保留callback后求值，error None和默认clock分支另测。slot消费、ledger version和Attempt累计计数无重置/退款。 |
| Private independent entry | **Pass。** `_complete_tool_call_in_transaction`按ID调用同一preparation，不接收caller supplied call/ledger/Attempt；同Session直接执行settlement，无commit/rollback/Session替换。callback也须遵守外层事务规则；本函数不控制任意callback的外部副作用。 |
| Lock / refresh / chain authority | **Pass，本次既有native范围。** ID重新定位、Run→Step→Attempt→Call→Ledger FOR UPDATE/populate_existing保持。独立连接NOWAIT与Run lock timeout证明实际锁保持；额外真实blocking关系与stale cached running行验证刷新。foreign workspace链被拒绝。无新lease/member/source权限声明。 |
| Raw-row helper使用边界 | **Pass，局部实现。** `_settle_tool_call`仅由两个已先执行`_tool_call_for_settlement`的入口调用，未export。它自身是无guard的内部算术块；未来集成应调用`_complete_tool_call_in_transaction`，不能将该raw-row helper当作已批准的外部“预锁ABI”。本次无必要新增capability/DTO/schema。 |
| Caller atomic undo / once only | **Pass。** inner成功后caller rollback恢复call、ledger、Attempt、真实ResearchArtifact结果行；额外outer应用/约束错误也恢复全部写入。真实竞争的commit-first、rollback-first及不同call共享ledger均得到正确计数与callback次数。 |
| API facade | **Pass，保留既有层级。** facade源代码未改；28项旧budget/recovery/boundary回归通过。直接neutral事务测试与facade区分。没有新宣称对facade所有commit-error分支做了单独PG专项覆盖。 |
| Schema / native authorization / full runtime | **不在本次验收。** 使用原生ORM创建表；不等于Alembic迁移/触发器或policy/source授权证明。未改reclaim、schema、#43ABI、Worker dispatch；没有同Attempt两次压缩、真实模型或UI结果。 |

冻结工具源码约为小型单模块提取，职责仍是native tool persistence，未扩散到shared层。对未来单事务owner的方向正确：可复用独立ID入口；旧调用者继续使用public原事务语义。

### 8.4 独立真实PG环境与完整套件执行

本 reviewer 新建自己的disposable cluster，未复用开发者结果或开发者数据目录：

- PostgreSQL **17.11**，`READ COMMITTED`，loopback `127.0.0.1:56546`。
- 数据库`citeframe_issue45_settlement_test`，合成测试role `issue45_review`，仅本次临时cluster使用trust本地测试配置；无凭据读取/存储。
- cluster目录 `$env:TEMP/citeframe45-independent-settlement-20260929/data`；仅作为允许的测试运行临时状态，非产品文件。
- 工具 `D:/Code/citeframe/.local-runtime/postgresql/pgsql/bin/{initdb,postgres,createdb,psql,pg_ctl}.exe` 只读使用。
- 每个PG fixture独立schema，真实ORM依赖表与FK/CHECK启用。没有Alembic upgrade、产品schema改动或mock数据库。fixture中通用snapshot字段是合成数据，此处不验证native approval graph，也未将这些fixture提升为授权证据。

初始化/启动按以下形式执行，全部同一非提权sandbox身份：

```powershell
$base=Join-Path $env:TEMP 'citeframe45-independent-settlement-20260929'
# 初次执行已先检查目录不存在
& D:/Code/citeframe/.local-runtime/postgresql/pgsql/bin/initdb.exe `
  -D (Join-Path $base 'data') -U issue45_review --auth=trust --encoding=UTF8 --locale=C
Start-Process -FilePath D:/Code/citeframe/.local-runtime/postgresql/pgsql/bin/postgres.exe `
  -ArgumentList @('-D',(Join-Path $base 'data'),'-h','127.0.0.1','-p','56546') `
  -WindowStyle Hidden -RedirectStandardOutput (Join-Path $base 'stdout.log') `
  -RedirectStandardError (Join-Path $base 'stderr.log')
& D:/Code/citeframe/.local-runtime/postgresql/pgsql/bin/createdb.exe `
  -h 127.0.0.1 -p 56546 -U issue45_review citeframe_issue45_settlement_test
```

初始化打印Windows restricted-token诊断87/3，同时实际初始化完整成功、exit0；随后普通postgres进程在同身份成功监听，并由真实SQL查询确认版本。无提权、权限变更或sandbox-policy绕过。初次`pg_isready`未指定user产生一条默认role不存在日志；后续连接全部明确`issue45_review`，DB创建及测试成功。该ready诊断不计作数据库测试通过。

完整套件从lane根执行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTHONPATH=((@(
  'apps/worker/src','apps/api/src','apps/api/tests',
  'packages/backend-contracts/src','packages/backend-persistence/src',
  'packages/research-persistence/src','packages/memory-service/src',
  'packages/prompt-contracts/src'
) | ForEach-Object { Join-Path $PWD $_ }) -join ';')
$env:CITEFRAME_ISSUE45_POSTGRES_URL='postgresql+psycopg://issue45_review@127.0.0.1:56546/citeframe_issue45_settlement_test'
$base=Join-Path $env:TEMP 'citeframe45-independent-settlement-20260929/pytest'
# 已先检查本次basetemp不存在
& D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -B -m pytest `
  -p no:cacheprovider --basetemp "$base" `
  packages/research-persistence/tests/test_memory_tool_settlement.py `
  apps/api/tests/test_research_worker_budget_recovery.py `
  apps/api/tests/test_research_persistence_boundary.py `
  apps/worker/tests/test_research_memory_context.py -q --tb=short
```

**本 reviewer 实际结果：120 passed, 1 warning in 25.47s，exit0，无skip。** 其中56专项=55真实PG参数化case+1固定源码/签名/AST case；其余28旧回归、36projection。warning是既有Starlette/httpx TestClient deprecation。该结果独立于开发者24.30s记录，不把SQLite旧回归计入PG数。

真实importpath在独立probe中用`Path(module.__file__).resolve().is_relative_to(lane_root)`断言并打印：

```text
citeframe_contracts
  D:\Code\citeframe-lanes\issue45-research\packages\backend-contracts\src\citeframe_contracts\__init__.py
citeframe_persistence.models
  D:\Code\citeframe-lanes\issue45-research\packages\backend-persistence\src\citeframe_persistence\models\__init__.py
citeframe_research_persistence.tools
  D:\Code\citeframe-lanes\issue45-research\packages\research-persistence\src\citeframe_research_persistence\tools.py
```

canonical API venv仅作为Python/pytest/psycopg工具来源。未写bytecode或pytest cache，没有从canonical旧tools获得候选测试绿灯。

### 8.5 额外 reviewer 反向探针：11个真实PG情景

通过`python.exe -B -`执行独立stdin程序；未写入产品或新测试文件。复用已审fixture仅用于真实PG建表、合成native seed及全表投影，断言/并发控制由 reviewer另写。没有monkeypatch native锁/settlement行为，也没有伪造native状态机含义。

程序从固定Git对象编译旧public；直接使用冻结候选inner/public。每个情景独立schema和物理连接，最终清理。执行清单：

| 额外情景 | 实际结果与反向判据 |
|---|---|
| 6：old/new × invalid status / missing chain / already terminal | S1先真实写Workspace description sentinel；函数报错后未rollback/commit，Session仍active，caller明确commit。fresh S2看到sentinel持久化，call/ledger/Attempt/result仍与baseline完全相同。补足原套件只验证“仍在当前事务可见随后rollback”的证据范围。 |
| 2：inner成功后outer应用异常 / real NOT NULL异常 | inner写ResearchArtifact并更新call/ledger/Attempt后，outer再写Workspace。应用异常时S1仍看到结果；实际NOT NULL错误时Session inactive；两者inner均未接管事务。caller统一rollback后fresh connection完整投影等于基线，结果/outer写入均消失。 |
| 1：same call，S1 commit-first | S2独立Session先缓存旧running行再开始inner，实际阻塞于S1；`pg_blocking_pids(S2_pid)`包含S1 backend。S1commit后S2刷新并报already-terminal，第二callback为0。最终reserved=0、actual=5、version=8、Attempt tools=5，结果只有一份。 |
| 1：same call，S1 rollback-first | 同样实际blocked；S1rollback撤销其结果与结算，S2随后成功一次、callback1次并由S2commit。最终同一套一次结算计数、结果一份。 |
| 1：two calls共享ledger | 基线两个不同native call、reserved=2，S1/S2真实锁竞争；S1commit后S2完成另一个call并commit。最终reserved=0、actual=6、version=9、Attempt tools=6，无lost update，无第二ledger。 |

并发使用thread barrier/queue给出backend PID，3秒有界轮询`pg_blocking_pids`，不以sleep时长推定有锁；线程有界join与finally rollback。投影核对完整native rows，计数初始非零（actual=4、version=7、Attempt tools=4）。stale cached row场景同时证明实际数据库刷新阻止重复结算。

实际stdout：

```text
BASELINE exact old function and unchanged existing helpers independently verified
PASS 6 old/new precondition errors preserve caller commit of prior sentinel
PASS 2 later caller failures undo all native settlement/result/outer writes
PASS actual concurrent commit blocker observed; exact counters and callback outcome
PASS actual concurrent rollback blocker observed; exact counters and callback outcome
PASS actual concurrent two_calls blocker observed; exact counters and callback outcome
SUPPLEMENTAL RESULT 11 PG scenarios passed; 6 precondition + 2 outer failure + 3 concurrency
```

成功probe exit0，用时5.69s。11个是额外执行情景，未伪称新增11个已提交pytest case；55+11为此次真实PG专项及额外情景数量，120套件总数另计。

第一次stdin probe从lane cwd调用canonical Git读取旧对象，因Git dubious ownership退出128；当时尚未进入任何额外PG情景。改从canonical cwd执行相同检查、PYTHONPATH仍明确lane后成功。没有修改safe.directory或全局Git配置；这次失败不掩盖、不计作通过。

### 8.6 反向审查、限制与后续owner

- 若public broad try误含precondition，六个caller-commit sentinel情景会丢失先前写入；已独立通过。
- 若inner隐藏commit/rollback，outer-later-failure、callback-failure状态及独立连接完整投影会揭示部分持久化/提前撤销；已通过。
- 若省略锁刷新，真实等待者携带cached running状态会重复callback/结算；commit-first probe已拒绝第二执行。
- 若错误使用第二Session/第二ledger，rollback与共享ledger两call的最终实际计数会不符；当前实现和执行均无此行为。
- `_settle_tool_call`内部接受raw rows不代表外部授权；未来集成必须守住带ID/锁链的entry边界。Python私有命名不构成安全sandbox；本审查判断当前可达调用图及grant，不承诺对任意应用代码滥用内部函数防护。
- 本轮实际约束错误涵盖native非负reserved CHECK、native tool-name CHECK、NOT NULL及chain autoflush。未执行Alembic升级、迁移回退、未来memory/source triggers或全部API facade commit-error矩阵；无相关扩大结论。
- CI当前不自动收集新package文件。controller需在后续授权workflow中提供真实PG URL、显式选中测试、失败不skip，保留本次本地证据范围。review批准不替代该交付gate。
- schema、planner-sidecar、state/reclaim/membership、#43 ABI/原有未闭合项、源权限与A1私有排除、完整同live-Attempt两次自动压缩、真实语义/UI均继续由原owner在各自grant中实现/审查。本轮不触达UI46或调用模型。

### 8.7 清理、保全与write-back

所有执行后查询：`remaining_review_schemas = 0`；以精确本次data路径执行`pg_ctl -D ... -m fast -w stop`返回server stopped。后台启动命令随后正常结束，测试/并发线程均已结束。没有停止其他PostgreSQL实例，也未删除共享目录。

候选三文件hash执行后仍与8.2一致。只向本canonical原review追加本节；未改旧review文字、lane产品/测试/evidence、CI、schemas/models、共享spec/workbench、Git/index/branch或全局私有memory。此前同session只读bootstrap和固定baseline准备继续适用。临时PG data/log/pytest fixture状态仅在本次自有TEMP目录；没有产品runtime或网络provider执行。

controller可将本review复制到lane，按本次冻结hash作bounded integration/后续CI授权；若代码或测试变化，须重新pin并交回本原独审。有实缺时仍由原开发 `agt_d03b4a29` 返工，本轮没有更换开发或另起产品owner。