# R2-K A-DATA 决策提案独立 Critical 复审

日期：2026-09-01
基线：`5d9a87107d6a44bacfee23ce28570d03919b98c1`
审阅对象：[`r2k-adata-decision-proposal-2026-09-01.md`](r2k-adata-decision-proposal-2026-09-01.md)

## 最终结论

```text
Verdict: ACCEPT
Critical=0
High=0
Medium=0
Low=0
```

本结论表示待批准的 A-DATA 决策包已经把实现边界、数据合同、状态机、锁序、故障恢复、发布回滚和验收矩阵写到可实施且可审计的程度。它不表示所有者已经批准数据合同，也不授权修改 schema、ORM、production publication/save/retry/replay 路径。收到所有者含义明确的 `批准 A-DATA` 前，R2-K 仍处于停止实现状态，R2 仍必须保持 `coverage.r2Complete=false`。

## 复审范围

独立审阅对照了以下当前生产事实：

- `publish_final_report` 先写对象、再提交数据库终态，并只在即时 verification 可用时区分 committed/absent；
- `research_commit_outcome_unknown` 当前会落入通用失败归一化风险；
- generic expired-Attempt recovery 会回收所有过期 running Attempt；
- current Worker publication port 强制把结果解析为 Artifact UUID；
- 当前对象存储 adapter 使用无条件固定-key PUT/DELETE，不具备对象 generation fencing；
- Research 现有锁序、Artifact/Event 唯一约束、UoW commit owner 和 Worker dispatcher 结构。

最终提案已闭合以下关键合同：

1. durable intent 在任何对象上传前提交，并持久化有上限的完整 canonical report bytes；
2. 每次 ownership generation 使用独立对象键，迟到 PUT/DELETE 不能覆盖或删除 adopted generation；
3. `prepared`、`uploaded`、`committing`、`compensating` 的 claim 接管有明确原子转换；
4. `committing` 接管通过 intent 行锁等待旧 final transaction，再按锁后状态判断 committed 或重新 finalization；
5. nonterminal publication intent 使 generic Attempt reclaimer 让权，专用 reconciler 使用 DB-time generation/token fencing；
6. `absent` 与 Attempt/Step/Run disposition、既有 Event 在一个数据库事务中收敛；
7. 用户可见 Artifact/终态/Event exactly-once 与物理对象 generation-isolated/effectively-idempotent 的声明边界分开；
8. additive migration、旧 Worker 全量 drain、禁止混跑、forward-compatible code rollback 和受控 database downgrade 边界明确；
9. 自动化与真实 PostgreSQL 17.11 + MinIO 多进程矩阵覆盖 prepare/final commit unknown、claim expiry、旧 backend commit/rollback、迟到对象操作、补偿 kill points、取消、deadlock 和 secret scrub。

## Finding 关闭记录

首轮复审识别 `Critical=4 / High=5 / Medium=3 / Low=0`，主要涉及 durable payload 不完整、固定对象键不能 fence 在途操作、publication intent 与 generic Attempt reclaim 冲突、`absent` 非原子、commit oracle、锁序、唯一约束、混合版本上线、故障矩阵、portable ORM 类型、heartbeat 和内部 deferred 返回合同。

第二轮复审将剩余问题收敛为 `Critical=0 / High=1 / Medium=0 / Low=0`：claim 在 `uploaded` 或 `committing` 状态到期接管时，旧 current object marker 与新 generation 的关系未闭合。

第三轮确认以下修正后接受：

- `uploaded` 接管原子回退 `prepared`，使用新 generation/key 重新上传和核验；
- `committing` 接管先等待旧 final transaction 的 intent 行锁，锁后为 committed 时直接返回，仍为 committing 时才换代并回退 prepared；
- `compensating` 接管保持状态、清空 current object、继续清理整个 prefix；
- terminal 状态不再认领或递增 generation；
- 主动释放、退避、predicate recheck、锁序和真实故障矩阵同步闭合。

最终未发现未关闭 finding。独立审阅过程未修改、未提交、未推送仓库文件。
