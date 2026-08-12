# V5-D Implementation Lanes

## 1. 使用方式

本文件把 [`v5d-detailed-spec.md`](v5d-detailed-spec.md) 拆成可并行但不重叠的
agent lane。实现 worker 使用已批准的 `grok-4.5` 配置；独立 reviewer 不承担
实现。main controller 负责基线、合同裁决、集成、验收和最终交付。

当前 Citeframe canonical worktree 含有未提交的 V5-C 实现。任何 lane 开始前
必须由 main controller 记录源 SHA、`git status --short`、已有修改归属和 lane
允许修改的文件集合。agent 不得覆盖或清理不属于自己的 dirty changes。

## 2. Gate 0：串行前置门

状态：`required-before-D-implementation`

由 main controller 完成，不作为并行 writer lane：

1. 固定 V5-C accepted baseline，并决定 dirty worktree 的保留/提交边界。
2. 关闭或明确记录 F1 executable registry mapping oracle。
3. 生成 F5 pre-V5-C historical-row artifact，或记录明确的非阻塞延期理由。
4. 确认 D 仍不引入新 registry version、schema、API、save/replay 变化。
5. 创建 D artifact 根目录，例如 `docs/evals/artifacts/v5d-20260811-01/`。
6. 将本文件的 lane ownership 复制到 workbench checkpoint。

## 3. Lane ownership

| Lane | 责任 | 允许修改 | 不得修改 | 依赖 |
|---|---|---|---|---|
| D-API-WORKER | D001 mixed scope/retrieval/recovery contract regression；不新增合同 | `apps/api/src/**`、`apps/api/tests/**`、`apps/worker/src/**`、`apps/worker/tests/**` 中与混合 scope、recovery、delete/retry 直接相关文件；对应测试/fixture | `apps/web/**`、基础 schema/migration、无批准的 provider/locator/save path | Gate 0；可与 D-WEB 并行但不得共改同一文件 |
| D-WEB | D002 desktop/mobile asset/Chat/Research/Viewer primary paths | `apps/web/src/**`、`apps/web/e2e/**`、Web fixtures/test helpers | API/Worker/infra；不得在 shell 中实现 modality business logic | Gate 0；依赖既有 API DTO |
| D-OPS | D003 deployment/restart/backup/restore evidence harness | `infra/**`、部署 profile、acceptance scripts、artifact schema、必要的 isolated test fixture | 业务 API/Worker/Web contract；不得放宽 health/restore 判定 | Gate 0；可与 D-API-WORKER/D-WEB 并行 |
| D-DOCS | D004 runbook、diagnostic map、SSoT/spec writeback | `docs/ssot/**`、`docs/architecture/**`、V5-D spec/acceptance records、runbook | 生产代码、迁移、既有 V5-B/C 历史 artifact | Gate 0；实现结果到齐后收口 |
| D-ACCEPT | D005 full regression、review、rework routing、release verdict | 只读审计；可新增 acceptance report/artifact；修复必须回原 owner lane | 不直接替代 owner lane 修改生产代码；不自行改变 scope/contract | 所有 lanes 完成 |

同一文件只能有一个 writer。发现跨 lane 需要改同一文件时，暂停并由 main
controller 串行分配，不通过兼容分支或临时双写解决。

## 4. 依赖顺序

```text
Gate 0
  -> D-API-WORKER ─┐
  -> D-WEB         ├-> D-OPS integration evidence
  -> D-DOCS draft  ┘
  -> D-DOCS final -> D-ACCEPT -> independent Critical review -> internal-preview verdict
```

D-OPS 可提前做静态脚本和 fixture 检查，但 live deployment 必须使用已集成的
canonical code。D-DOCS 可以先写 runbook skeleton，最终命令和 artifact 必须
在 D-ACCEPT 前按真实执行结果更新。

## 5. 每个 lane 的交付格式

agent 回报必须包含：

- lane 名、owner、源 SHA、worktree 路径和 dirty-change disposition；
- goal alignment、changed files、未改变的合同；
- 实现摘要和明确未做事项；
- 单元/集成/静态/运行证据：命令、exit code、数量、日志/DOM/artifact 路径；
- reviewer findings、已修复项和仍存在的 residual risk；
- 是否需要触发 `save-contract-checklist.md`；
- 未经用户明确要求，不 commit、不 push。

## 6. Lane-specific acceptance

### D-API-WORKER

- 混合 PDF/Image/Document scope 与 retrieval 不跨 Workspace、不跨 generation、不跨无效 index。
- Citation/NoteSource、delete/retry/no-resurrection、Research restart/lease/recovery 语义保持不变。
- provider/model/limits/retrievalTopK 只读取 frozen execution snapshot。
- API/Worker focused tests、compileall 和 diff check 通过。

### D-WEB

- `1440x1000` 和 `390x844` production-start Playwright 覆盖混合资产、Quick Chat、Citation/NoteSource、Research 控制和 Viewer。
- 所有 enabled locator 使用精确 renderer；unknown/unavailable 不 fallback。
- Web unit、lint、tsc、build 和截图/DOM/state evidence 通过。

### D-OPS

- restart/reclaim/delete/retry/backup/restore 脚本具备明确 preflight、失败码、cleanup 和 zero-residue。
- live PostgreSQL/MinIO 证据包含 image/version、Alembic head、row/object checksums、API/DOM replay 和 teardown。
- 不把 SQLite 或 scripted provider 伪装成 live/model evidence。

### D-DOCS

- README、plan、tasks、progress、runbook、D matrix、acceptance record 互相链接且状态一致。
- 每个命令可在当前 repo 运行或注明阻塞原因；不保留过期端口、脚本和 artifact 名称。

### D-ACCEPT

- 按 [`verification-matrix-v5d.md`](verification-matrix-v5d.md) 逐项标记状态。
- Critical review 发现问题时，回派原 lane；替换 worker 需要记录原因。
- 只在所有 required gates 为 `pass`/`not applicable` 且没有未解释 blocker 时出具 `ACCEPT`。

## 7. 停工条件

以下情况必须立即回报 main controller，不得自行猜测：

- 需要改数据库/API/save/replay/permission/cost/locator 合同；
- 发现 V5-C dirty change 与目标文件重叠且无法证明归属；
- 需要 provider selector、fallback、compatibility layer 或新的 registry version；
- live PostgreSQL/MinIO、认证状态、真实 fixture 或生产启动环境不可用；
- 测试失败可能是既有基线回归，尚未完成 old/new 对比；
- 发现 spec 与当前代码不一致且无法由既有合同裁决。
