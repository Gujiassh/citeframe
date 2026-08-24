# API / Worker Boundary Follow-up

状态：架构跟进记录，未修改生产代码。
审查日期：2026-08-18
审查分支：`work/docs-stale-honesty-20260817`
审查范围：`apps/api`、`apps/worker`、Python 镜像和部署编排。

> 2026-08-24 current-state override: A2a and R0 are independently accepted. R0 chain: start `7ee97471`, production `39766c37`, final ledger `6b8ab475`, review `9d4297f8` (`High=0`, `Medium=0`, `Low=0`). All R0 commits are local/not pushed; the branch has no upstream and no remote branch. R1 is the only next separately gated implementation slice; R2/W1 remain blocked. No admission or R1 implementation is authorized.

这份记录只处理两个问题：API/Worker 的实际代码边界，以及
`evidence.py` / `assets.py` 等中心文件的下一步拆分方向。它不是一次重写授权，
也不改变当前 API、数据库、Evidence locator 或保存语义。

## 1. Current Facts

### 1.1 系统形态（必须先说清楚）

当前是 **“部署分离、代码/事务共享的模块化系统”**，不是已经成立的独立服务边界：

- Compose/镜像上 API 与 Worker 是两个进程，但 Worker 构建与运行仍依赖 API 源码包。
- Repair worktree 中 SQLAlchemy mappings/唯一 metadata 由 neutral
  `citeframe_persistence` 定义，`ai_pdf_api.models` 保留 compatibility surface；
  Alembic execution/schema governance 仍属于 API。
- 初始审查事实是 Research Worker `_ApiPort` 创建 Session 并执行 write-path `commit` / `rollback` / `close`。Accepted A2a production 已把默认 DB-only Research composition 切到 neutral `ResearchUnitOfWork` / `ResearchRepository`；这仍不等于 API 进程独占事务。接受链的三笔本地提交尚未推送。
- Ingestion 路径由 API `process_ingestion_job` 编排并提交 job 状态，同时把同一
  SQLAlchemy `Session` 与 ORM `Asset` 传入 Worker adapter；模态解析与 ORM 写入仍
  混在同一会话里。
  证据：[`ingestion.py:141-224`](../../apps/api/src/ai_pdf_api/services/ingestion.py#L141)。

### 1.2 进程和部署边界

- Worker 在 Compose 中是独立进程和独立镜像 target，但 Worker 镜像在构建时复制
  `apps/api/pyproject.toml` 和 `apps/api/src`，运行时设置
  `PYTHONPATH=/app/apps/api/src:/app/apps/worker/src`。
  证据：[`Dockerfile.python:28-46`](../../infra/docker/Dockerfile.python#L28)。
- Worker 的 Python 项目把 `ai-pdf-api` 声明为 editable path 依赖
  `../api`，因此 API 包的版本和源码布局是 Worker 的构建前提，而不是独立发布的
  外部合同。
  证据：[`apps/worker/pyproject.toml:6-18`](../../apps/worker/pyproject.toml#L6)。
- Deploy Compose 为 API、Worker、migration 共享同一套数据库、对象存储和模型配置；
  Worker 只 `depends_on` migration/MinIO，不通过 API health 或内部 HTTP 端口建立任务
  调用链。任务主路径仍是 PostgreSQL 轮询和 `FOR UPDATE SKIP LOCKED`，不是 Redis。
  证据：[`compose.deploy.yml:128-144`](../../infra/docker/compose.deploy.yml#L128)。

### 1.3 Worker 对 API 内部模块的实际依赖

截至本次静态扫描，`apps/worker/src` 有 **28 个源模块、96 条导入语句**直接导入
`ai_pdf_api`，覆盖 `core`、`db`、`modalities`、`models`、`schemas` 和 `services`；
其中 12 个源模块还直接导入 SQLAlchemy。典型入口如下：

- Worker 主循环直接导入 API `settings`、`SessionLocal`、ingestion registry、job
  service 和 provider，并在启动时构造 `ResearchWorkProcessor`。
  证据：[`main.py:9-33`](../../apps/worker/src/ai_pdf_worker/main.py#L9)、
  [`main.py:246-263`](../../apps/worker/src/ai_pdf_worker/main.py#L246)。
- PDF/Image/Office/HTML/Audio/Video adapter 的方法参数是 API 的 `Session` 和
  `Asset`，并直接读写 API ORM 相关的 Representation、ContentUnit、Locator。
  证据：[`pdf_ingestion.py:7-24`](../../apps/worker/src/ai_pdf_worker/pdf_ingestion.py#L7)、
  [`image_ingestion.py:8-25`](../../apps/worker/src/ai_pdf_worker/image_ingestion.py#L8)、
  [`audio_ingestion.py:15-49`](../../apps/worker/src/ai_pdf_worker/audio_ingestion.py#L15)。

### 1.4 Research 端口：初始事实与 A2a repair current state

- Initial reviewed state defined `ResearchWorkerService`, `SessionFactory`, `_ApiPort`,
  and payload-only `SqlResearchLedgerAdapter`. Accepted A2a adds the installable neutral
  Research persistence boundary and default Worker UoW composition; remote delivery is pending.
- 初始快照由 `_ApiPort._db()` 管理 Session/commit。Accepted A2a production 的默认 DB-only Research 写路径改由 Worker-side neutral persistence service/UoW 管理 Session/commit；API 保留 HTTP/auth/Alembic/schema governance 与非 DB adapter composition。
- Research runtime 仍直接导入 API observability、provider、context policy、
  Agent I/O registry；Worker 启动时通过 `build_default_research_service()` lazy-load
  API `research_worker` 模块。lazy import 只改善测试隔离，不改变包耦合。
  证据：[`research_runtime_ports.py:17-33`](../../apps/worker/src/ai_pdf_worker/research_runtime_ports.py#L17)、
  [`research_runtime_processor.py:360-364`](../../apps/worker/src/ai_pdf_worker/research_runtime_processor.py#L360)。
- 文档若写“Worker 通过 service ports 更新 Research 账本、不拥有 ORM/migration”，
  只能描述 **migration/schema 定义归属**，不能否认 Worker 当前持有 Session 与
  commit；也不能外推到 ingestion/modality 路径。
  证据：[`research-workflow-runtime.md:22-32`](./research-workflow-runtime.md#L22)、
  [`database-design.md:383-392`](./database-design.md#L383)。

### 1.5 大文件现状（行数不得串套）

**生产中心文件（本轮不拆）：**

- `apps/api/src/ai_pdf_api/modalities/evidence.py` = **1587** 行：多模态 locator
  codec、公共校验、clone、序列化、检索 key 和 registry。
- `apps/api/src/ai_pdf_api/routers/assets.py` = **1526** 行：Asset 生命周期与多种
  viewer/media stream。

**超过 2000 行的测试/脚本（独立后续拆分切片；不是 evidence/assets）：**

- `apps/worker/tests/test_r803_campaign_v5.py` = **2461** 行。
- `apps/worker/scripts/v5b_document_restore_acceptance.py` = **2006** 行。

不要把 2461/2006 套到 `evidence.py`/`assets.py`，也不要把 1587/1526 套到上述
测试/脚本。本轮只记计划，不拆任何上述文件。

### 1.6 可度量 import 基线（进入 C 前必须归零或获批 allowlist）

当前 Worker 源码对 `ai_pdf_api` 的静态基线（不可改写为“已独立”）：

| 度量 | 当前值 | C 入口要求 |
| --- | ---: | --- |
| 直接导入 `ai_pdf_api` 的源模块数 | **28** | → **0**，或进入 owner 明确批准的最小 allowlist |
| `from`/`import ai_pdf_api` 语句数 | **96** | → **0**，或 allowlist 内可解释的残余 |
| 直接导入 `sqlalchemy` 的 Worker 源模块数 | **12** | → **0**（若仍走同库 Session），或 allowlist + 批准的 session 策略 |

扫描面至少覆盖：九类生产 adapter、Research runtime、composition root
（`main` / processor factory）。allowlist 必须逐条写清模块、原因、失效条件；
默认目标是归零。

## 2. Problem Statement

当前形态是“部署分离、代码共享、事务共享”：

1. Worker 不能独立升级 API 的模型、migration、provider 或 settings；API 内部重命名
   可能在 Worker 构建或运行时才暴露。
2. Initial snapshot 的 port、DTO 与 transitions 仍分散；repair 已建立可安装的
   DB-only neutral boundary，但 provider/retrieval/storage/observability composition 仍在
   app 层，且整个 repair 仍需新的 Critical re-audit。
3. Research 的 repair UoW 与 ingestion adapter 都让 Worker 触及 Session/事务生命周期；
   若把“schema owner”与“runtime commit process owner”混称，会掩盖真实故障面。
4. `evidence.py`（1587）与 `assets.py`（1526）以及超 2000 行的评测/恢复脚本会提高
   冲突与回归成本；拆分必须独立切片。

## 3. Non-goals（本轮 ADR 文档本身）

- 不在本次跟进中改 API payload、数据库 schema、Alembic、Asset generation、
  Evidence locator、Citation/NoteSource 或 Research save semantics。
- **本轮 ADR 文档工作不创建目标 packages（包括 `packages/backend-contracts`），不改
  production code，不创建新 Docker/build target。** 三个目标 distribution 的创建、
  分发与候选 build target 属于后续获批切片的计划项；这不是对目标 topology 的否定。
- 不把当前 PostgreSQL polling 直接替换为 Redis/Kafka；调度方案不是本记录的目标。
- 不把 Research 改成动态 DAG、通用 agent framework 或新的 checkpoint authority。
- 不要求一次性把 ingestion 全部改成 HTTP RPC。
- **本轮不拆分** `evidence.py` / `assets.py` / `test_r803_campaign_v5.py` /
  `v5b_document_restore_acceptance.py`。
- **Branch protection / GitHub 设置保持 unresolved**；本记录不调用仓库保护接口。
- `internal_preview` 的 same-DB adapter、Worker orchestration、R0 lock-normalization target 与 Worker-side UoW commit-process target 已获 owner conditional authorization；API-process HTTP/RPC 仍未授权。修订设计的独立 Critical 复审已接受 (`High=0`, `Medium=0`, `Low=0`)；A1 已于 2026-08-20 独立 ACCEPT；A1b/A2-foundation 已于 2026-08-21 独立 ACCEPT（follow-up Critical review：High=0、Medium=0、Low=0），A2a was independently accepted at local production `215cd52`, documentation `95981a4`, and review `eb97adf`; none is pushed; R0 已在本地 review `9d4297f8` 独立 ACCEPT；R1 是唯一下一门控切片，R2/W1 继续 blocked，admission 未授权；不授权 schema/API/save/replay/permission 变更。

## 4. Proposed Incremental Boundary

### 4.0 Owner 维度（A0 必须分开写清；不得混称）

| 维度 | 含义 | 当前事实 | 备注 |
| --- | --- | --- | --- |
| **Schema / migration owner** | 谁治理表结构与执行 Alembic | **API**；neutral `citeframe_persistence` 定义唯一 mappings/metadata | Schema governance 不等于 runtime commit |
| **Mutation logic owner** | 谁定义 Research/ingestion 业务写入函数与锁序 | Accepted A2a: DB-only Research transitions in `citeframe_research_persistence`; API compatibility/composition facades; ingestion remains API service-owned | Final Critical `ACCEPT` at `eb97adf` |
| **Session / commit process owner** | 哪个**进程**创建 Session 并执行 commit/rollback | Accepted A2a Research: Worker-side neutral UoW; Ingestion: shared Session boundary | Accepted locally; delivery push pending |

Transport 候选的 commit 含义不得混称：

- **Same-DB adapter 跑在 Worker 进程内**：即使 mutation logic 仍是 API service 函数，
  **runtime commit process owner 仍是 Worker**（Session 在 Worker 内打开/提交）。
  不能把它叫做“API-process commit”或笼统的 “API-owned transaction”。这是
  `internal_preview` 已获 owner 授权的目标。
- **Internal HTTP（或其他 RPC）由 API 进程执行写入**：此时 **runtime commit
  process owner 才是 API 进程**。该方向仍未授权。

### 4.1 目标依赖方向（A2a independently accepted locally；remote delivery pending）

Owner 已授权 `internal_preview` 使用 same-DB adapter 的目标方向：API 负责
HTTP/auth、Alembic 执行与 schema governance；Worker 负责 Research orchestration；
Worker-side UoW 是 Research job runtime commit-process owner。
`citeframe-backend-contracts` / `citeframe_contracts` 承载 DTO/Protocol；
`citeframe-backend-persistence` / `citeframe_persistence` 物理持有 Research 与 API
core/other 的全部 SQLAlchemy mappings 和唯一 Base/metadata；
`citeframe-research-persistence` / `citeframe_research_persistence` 只持有 Research
repositories/UoW/commands/locks，不复制 mappings 且不得 import `ai_pdf_api` 或
Storage/Provider/Retrieval/Observability/agent registry 实现。API 与 Worker 必须调用
同一 commands，禁止复制模型或 transition logic。当前 `ai_pdf_api.models` 是共享 ORM
import surface；迁移期间可 re-export 同一 classes。A1b/A2-foundation 迁移三套
pyproject/uv.lock path source 与 Docker 安装，Alembic 仍由 API 显式 import
`citeframe_persistence.models` 并加载唯一 metadata；这项 foundation 是 A2a 显式前置。

这是批准目标；A2a 已按该方向实现 DB-only boundary 并通过独立 Critical ACCEPT；三笔本地提交仍待远端交付。修订设计的独立 Critical 复审已接受 (`High=0`, `Medium=0`, `Low=0`)；A1 已于 2026-08-20 独立 ACCEPT；A1b/A2-foundation 已于 2026-08-21 独立 ACCEPT（follow-up Critical review：High=0、Medium=0、Low=0）；A2a was independently accepted at local production `215cd52`, documentation `95981a4`, and review `eb97adf`; none is pushed; R0 已在本地 review `9d4297f8` 独立 ACCEPT；R1 是唯一下一门控切片，R2/W1 继续 blocked，admission 未授权，且不授权 schema/API/save/replay/permission 变更。详细的 R1/R2/W1、锁/fencing、per-Run admission、
SSE 与语义 oracle 见
[`research-boundary-runtime-design.md`](../../specs/v5/post-v5-optimization/research-boundary-runtime-design.md)。

```text
Dependency direction (consumer -> dependency):

API adapters/commands ───────────────┐
Worker runtime/handlers ─────────────┼──> citeframe_research_persistence
                                     │        (Research behavior/UoW/locks)
                                     └──> citeframe_contracts (pure DTO/Protocol)

citeframe_research_persistence ──────┬──> citeframe_persistence
                                     └──> citeframe_contracts

API adapters/commands and Worker runtime/handlers may also import
citeframe_persistence only through the approved mapping/Session boundary.
```

推荐目标（**owner 已授权方向，但不是当前事实，也未开始生产实现**）：

- 跨边界只交换 contracts 中的 DTO/Protocol。
- 在 `internal_preview` 已授权的 same-DB transport 下，明确 **session/commit process owner**（见 §4.0）；
  不得把 same-DB-in-Worker 与 API-process HTTP 混写成同一种 “API-owned transaction”。
- Worker 负责解析、OCR、provider/tool execution 和 orchestration。
- 共享 `packages/shared-types` 当前是 TypeScript 包，不应直接承载 Python runtime DTO。

### 4.2 可执行迁移顺序

**A0：只冻结事实、DTO/Protocol 语义、已授权 owner + same-DB transport 目标（当前文档切片）**

1. 准确记录当前 repair-worktree 事实（并同步正式 SSoT，见 §7/§8）：API package
   拥有 HTTP/auth/Alembic/schema governance；neutral package 持有 DB-only Research
   transitions；Worker-side UoW 管理 Research Session/commit；ingestion 仍在共享
   Session/ORM 边界；系统是模块化双进程，不是独立服务边界。
2. 文档冻结 Research port payload / Protocol **字段语义**。
3. Owner 已授权的 A0 目标为：API 负责 HTTP/auth/Alembic/schema governance；Worker
   负责 Research orchestration；Worker-side UoW 负责 Research runtime commit；
   same-DB adapter 为 `internal_preview` transport；`citeframe_contracts` 纯 DTO/Protocol；
   `citeframe_persistence` 持有唯一 ORM/metadata/mappings；`citeframe_research_persistence`
   持有 Research repositories/UoW/commands/locks 且不得 import `ai_pdf_api`。
4. A0 **禁止**：改生产行为、创建 contracts package、创建候选 build target、移除
   API editable dependency、改 schema/Alembic/save。
5. **不得在 A0 声称事务 process owner 已改为 API；生产实现仅限于待独立复审确认的冻结边界，且尚未开始。**

**A1 -> A1b/A2-foundation -> A2a：唯一 staged package topology（A1/A1b/A2a 均已独立 ACCEPT）**

三包不是同一阶段创建。每个阶段只创建、版本化、声明、复制和 smoke 当前已存在的
package；禁止提前出现 behavior-free `citeframe-research-persistence` scaffold：

| Slice | Newly introduced package | API/Worker manifest + lock | Docker/PYTHONPATH/import smoke | Must not include |
| --- | --- | --- | --- | --- |
| A1 | `citeframe-backend-contracts` / `citeframe_contracts`，纯 DTO/Protocol；必要 legacy re-export | 只增加 contracts local path source | 只复制/暴露 contracts；smoke 只 import `citeframe_contracts` | persistence、research-persistence、ORM/Research behavior |
| A1b/A2-foundation | `citeframe-backend-persistence` / `citeframe_persistence`，唯一 Base/metadata + all ORM mappings | 在已有 contracts 上再增加 persistence | 在 A1 上再复制/暴露 persistence；smoke import contracts+persistence | research-persistence、Research behavior、R0/R1 |
| A2a | `citeframe-research-persistence` / `citeframe_research_persistence`，Research repositories/UoW/commands/locks | 在已有两包上再增加 research-persistence | 此时才达到三包 COPY/PYTHONPATH；smoke import all 3 并断言路径不在 `/app/apps/api` | 提前 scaffold、mapping relocation、R0/R1 |

A1 的 API/Worker export 只 omit `citeframe-backend-contracts`；legacy Worker 额外 omit
`ai-pdf-api`。A1b 在各自 A1 命令上仅追加 `--no-emit-package
citeframe-backend-persistence`。A2a 才追加 `--no-emit-package
citeframe-research-persistence`，形成 implementation-ready design 中的最终三包命令。
每阶段 `requirements.deploy.txt` 仍只包含 hash-pinned third-party；local packages
不走 pip、wheel 或 `--require-hashes`。每阶段 Docker 都先安装当前第三方 requirements，
再 source-copy 当前已有 packages 和 app source，设置当前阶段 `PYTHONPATH`，在最终
runtime filesystem、应用启动前执行当前阶段 smoke。精确命令、路径矩阵和 smoke 见
[`research-boundary-runtime-design.md` §3.1](../../specs/v5/post-v5-optimization/research-boundary-runtime-design.md)。

A2a 必须保持当前一次 `process_one` 可通过固定 LangGraph StateGraph 驱动多 Step
的 runtime 行为，只抽取 Research persistence behavior/ports；不得提前实施 R1
single-attempt dispatcher。A2a 通过后，R1 才移除 LangGraph 的 runtime step execution
职责并切换到 single-attempt dispatcher。现有 `ResearchStep.input_sha256` 含义保持不变；
canonical handler-input hash 若未来定义，必须单独走 A-DATA。

**R0：已独立 ACCEPT 的 Run-first 锁协议**

A2a 历史锁序混合/冲突。Accepted R0 production `39766c37` 已将所有多行 Research
mutation 统一为 Run-first，且只改锁获取顺序，不改保存、API、replay、permission
或 payload 语义。当前顺序为：

```text
ResearchRun -> ResearchStep -> ResearchStepAttempt -> provider/tool Call -> ResearchBudgetLedger
```

已知 Attempt/Call id 先无锁读取 parent ids 仅用于定位，不做决定；随后按
`Run -> Step -> Attempt -> Call -> Ledger` 加锁、refresh 并重验 chain/scope/status/
token/expiry，定位后任何变化都按重验失败处理。claim 从存在 queued work 的
candidate Run 开始，以 `FOR UPDATE SKIP LOCKED` 按每个 Run 最小 eligible Step 元组 `(queued_at, created_at, step_id)`+Run ID 稳定
排序，先锁 Run、复核 status/cap，再按现有 `queued_at`、`created_at`、再 Step ID 顺序锁该 Run
内 eligible Step 并创建 Attempt；不再
先锁 Step 再等待 Run。cancel 继续 Run-first，按稳定 Step ID 锁需要 mutate 的 Steps；
heartbeat/complete/reclaim/provider/tool/join/decision/publication 全部迁到同一顺序。
R0 禁止 deadlock retry 掩盖回归，必须用真实 PostgreSQL `pg_locks`/timeout 证明
claim-vs-cancel、claim-vs-complete、reclaim-vs-provider/tool、两个 claim/不同 Run。

cap-full 只在锁定 candidate Run 后复核；full 时 rollback 整个 claim transaction、
释放 Run lock、记录 local `excluded_run_ids` 并以新 transaction 继续，未锁 Step、无
Attempt/status/Event 变化；query prefilter 不是正确性依据。


**B：Ingestion object/hash/compensation + 单模态 pilot（pilot ≠ C 入口）**

1. 冻结并实现 generated object / upload / compensation 合同。
2. Adapter 产出纯 `IngestionResult` manifest；**先选一个**成熟模态（PDF 或 Image）
   做旧/新对照——这是 **pilot 出口**，证明合同与对照方法可行。
3. **B 的单模态 pilot 绝不能直接成为 C 的入口条件。** 其余生产启用模态仍须继续
   迁完或另开切片；C 另有独立前置门（§4.2 C）。
4. 保持 `Asset -> Representation -> ContentUnit -> Locator` 语义不变。

**C：独立 Worker（最后）。前置门 ≠ B pilot**

C 在 A0/A1 完成且 B 的合同方法已验证之后才评估，但 **进入 C 还必须同时满足**：

1. **Import 归零门（相对 §1.6 基线 28 / 96 / 12）**：九类生产启用 adapter、
   Research runtime、composition root 对 `ai_pdf_api` 的 runtime imports 已归零，
   **或**进入 owner 明确批准的最小 allowlist（逐条失效条件成文）。SQLAlchemy 直接
   导入同理。
2. **无 API source 环境**：候选 Worker 在不复制 `apps/api/src`、不声明
   `ai-pdf-api` editable path、`PYTHONPATH` 不含 API source 的环境下，
   **import / compile / start** 通过。
3. **Candidate build target/manifest 过渡（仅计划，本轮不创建 target）**：
   - 暂时保留 legacy Worker target/dependency（仍可复制 API source / editable path）；
   - **新增**候选 Worker build manifest/target：不复制 API source、不声明
     `ai-pdf-api`；
   - 候选完成 import/start/ingest/research/recovery/**version mismatch** smoke；
   - **通过后**才替换正式 target，并删除 legacy editable dependency / API source /
     API `PYTHONPATH`。
4. **禁止**“先删除旧依赖，再评估 transport”。也禁止“B 单模态通过 → 直接进 C”。

### 4.3 大文件拆分方向（独立后续切片；本轮不做）

#### 4.3.1 生产中心文件

- `evidence.py`（**1587**）：拆成 contracts/registry/per-modality/operations；先保留
  facade。
- `assets.py`（**1526**）：拆成 lifecycle/representations/router；URL/response 不变。

#### 4.3.2 超过 2000 行的测试/脚本（单独切片）

- `test_r803_campaign_v5.py`（**2461**）：按 campaign/helper/oracle 拆分，不改冻结
  artifact 语义。
- `v5b_document_restore_acceptance.py`（**2006**）：按 backup/restore/verify/CLI 拆分，
  不改恢复 oracle。

拆分门槛：职责单一；拆分前后相同 fixture/oracle/权限/错误码一致。

## 5. Dependency Direction And Ownership（摘要）

详见 §4.0。一句话：**repair worktree 中 API = HTTP/auth/Alembic/schema governance；
neutral package = DB-only Research transitions；Research runtime commit process =
Worker-side UoW；ingestion = 共享 Session/ORM。** A2a 已获独立 ACCEPT，三笔本地提交
仍待远端交付；API-process HTTP/RPC 仍未授权。

明确禁止：在 A0 把目标写成当前事实；用 B pilot 顶替 C 前置门；在 import 归零/候选
smoke 前删除 legacy 依赖；`contracts -> ORM/API settings`；把 same-DB-in-Worker
commit 混称为 API-process commit。

## 6. Migration Risks

1. **保存语义漂移**：manifest 映射变化可能改变 representation/locator/generation。
2. **Owner 维度混称**：把 schema owner、mutation logic owner、session/commit process
   owner 混成“API-owned transaction”，尤其是 same-DB-in-Worker 场景。
3. **B pilot 误当 C 入口**：单模态对照通过不等于九类 adapter / Research / composition
   root import 已归零。
4. **先删依赖后补 transport / 先删 legacy 后补候选 smoke**：顺序不可执行。
5. **对象存储补偿**与 **版本错配**、**Research 历史恢复**、**大文件拆分回归**。

## 7. Acceptance Checks

### A0（事实 + owner-authorized target + 三分 owner 记录；无 package、无生产改动、无新 build target）

Implementation-ready target details live in
[`specs/v5/post-v5-optimization/research-boundary-runtime-design.md`](../../specs/v5/post-v5-optimization/research-boundary-runtime-design.md).

- 本 ADR 与下列**正式 SSoT** 同步当前 repair-worktree 事实（schema governance vs
  neutral Research UoW commit vs shared ingestion session）；A1/A1b acceptance remains
  historical; A2a repair is independently accepted locally, with remote delivery pending:
  - [`docs/ssot/system-architecture.md`](../ssot/system-architecture.md)
  - [`docs/architecture/database-design.md`](./database-design.md)
  - [`specs/v5/multimodal-agent-product/v5b-detailed-spec.md`](../../specs/v5/multimodal-agent-product/v5b-detailed-spec.md)
- Research port payload / Protocol 语义成文；same-DB transport 与 session/commit process
  owner 已按 A0 目标记录，API-process HTTP/RPC 仍保持未授权。
- 行数事实正确：evidence=1587、assets=1526、r803 campaign test=2461、v5b restore
  script=2006。
- Historical A0 docs-only slice did not create packages or change production. A1/A1b
  later received independent `ACCEPT`; A2a repair is now implementer-complete, and the
  current next step is one immutable snapshot plus a new Critical re-audit.

### A1（2026-08-20 独立 ACCEPT；A1b/A2-foundation 与 A2a 均已通过独立复审）

- contracts 纯 DTO/Protocol、legacy identity-preserving re-export、API/Worker local
  path source、contracts-only export/Docker/CI smoke and focused tests are present.
- No schema/API/save/replay/permission/runtime behavior changed; A1 was independently
  accepted on 2026-08-20. A1b/A2-foundation was independently accepted on 2026-08-21 by the
  follow-up Critical review (`High=0`, `Medium=0`, `Low=0`). A2a and R0 are independently accepted locally. R1 is the only next separately gated implementation slice; R2/W1 remain blocked.

### B（pilot 出口，非 C 入口）

- object/hash/compensation 合同 + **一个** PDF/Image 旧新对照通过。
- 明确记录：其余模态与 import 归零仍未满足 C。

### C（独立镜像；独立前置门）

- 相对基线 **28 / 96 / 12**：九类 adapter + Research runtime + composition root 的
  `ai_pdf_api` runtime imports 归零或获批最小 allowlist。
- 无 API source 环境 import/compile/start 通过。
- 候选 build target/manifest smoke（import/start/ingest/research/recovery/version
  mismatch）通过后，**才**替换正式 target 并删除 legacy editable dependency。

### 大文件拆分（独立后续）

- 生产：evidence 1587 / assets 1526。
- 测试/脚本：r803 campaign 2461 / v5b restore 2006。各自独立切片与 oracle。

## 8. Recommended Next Slice

A0 目标方向已获 owner 授权，文档同步入口如下：

1. Preserve the accepted A2a chain and R0 chain `7ee97471 -> 39766c37 -> 6b8ab475 -> 9d4297f8`.
2. Push/integrate through the repository review flow and record remote SHAs; the branch currently has no upstream or remote counterpart.
3. R1 is the only next separately gated implementation slice. Keep R2/W1 behind their named gates and admission unauthorized; do not fold R1 into R0.
4. 大文件拆分、G/M/P、provider spend、M404 与 branch protection 保持后置 / unauthorized。

不要把 A2a、R1、B pilot、C 独立镜像、大文件拆分与 A0 文档冻结混成一个大 PR。

## 9. Evidence Snapshot

- `apps/worker/pyproject.toml:6-18`：editable API dependency。
- `infra/docker/Dockerfile.python:28-46`：Worker image copies API source / API
  `PYTHONPATH`。
- `apps/worker/src/ai_pdf_worker/research_persistence_service.py`：repair default
  composition over neutral Research UoW/repository/commands；independently accepted at `eb97adf`。
- `apps/api/src/ai_pdf_api/services/ingestion.py:141-224`：shared Session/ORM into
  Worker adapter。
- Line counts（本机 `wc -l`）：`evidence.py` 1587；`assets.py` 1526；
  `test_r803_campaign_v5.py` 2461；`v5b_document_restore_acceptance.py` 2006。
- Import 基线：modules **28**；`ai_pdf_api` import statements **96**；Worker
  `sqlalchemy` modules **12**。

本记录为审查结果，不包含生产代码修改、提交或推送。
