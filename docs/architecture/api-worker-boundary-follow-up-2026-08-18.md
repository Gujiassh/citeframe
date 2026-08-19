# API / Worker Boundary Follow-up

状态：架构跟进记录，未修改生产代码。
审查日期：2026-08-18
审查分支：`work/docs-stale-honesty-20260817`
审查范围：`apps/api`、`apps/worker`、Python 镜像和部署编排。

这份记录只处理两个问题：API/Worker 的实际代码边界，以及
`evidence.py` / `assets.py` 等中心文件的下一步拆分方向。它不是一次重写授权，
也不改变当前 API、数据库、Evidence locator 或保存语义。

## 1. Current Facts

### 1.1 系统形态（必须先说清楚）

当前是 **“部署分离、代码/事务共享的模块化系统”**，不是已经成立的独立服务边界：

- Compose/镜像上 API 与 Worker 是两个进程，但 Worker 构建与运行仍依赖 API 源码包。
- SQL model、service 实现、Alembic migration 的**定义**在 API package
  （`ai_pdf_api`）中。
- Research Worker 的 `_ApiPort` **当前会创建 Session，并在 write 路径上
  `commit` / `rollback` / `close`**；因此运行时事务生命周期并不等于“已由 API
  进程独占”。把“事务 owner = API”写成当前事实是错误的。
  证据：[`research_runtime_core.py:192-217`](../../apps/worker/src/ai_pdf_worker/research_runtime_core.py#L192)。
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

### 1.4 Research 端口是“部分收口”，不是独立包边界

- Research runtime 已定义 `ResearchWorkerService`、`SessionFactory` 和 `_ApiPort`；
  `SqlResearchLedgerAdapter` 只接受 service 返回的 payload，不接受 ORM 对象。这是
  当前最清晰的 **payload 边界**，但 **不是** 已完成的事务/transport 边界。
  证据：[`research_runtime_core.py:172-217`](../../apps/worker/src/ai_pdf_worker/research_runtime_core.py#L172)。
- `_ApiPort._db()` 用 Worker 持有的 `SessionFactory` 开会话；`write=True` 时由
  Worker 侧 port 提交或回滚。API package 拥有 SQL/service/migration **定义**，但
  Research 写路径的 **运行时 commit owner 当前是 Worker `_ApiPort`**。
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
2. Research 已有 port/adapter 意识，但 port 定义、DTO、provider policy 和 API
   service 实现仍分散在两个 app；边界是约定，不是可安装/可检查的包合同。
3. Research `_ApiPort` 与 ingestion adapter 都让 Worker 触及 Session/事务生命周期；
   若把“schema owner”与“runtime commit process owner”混称，会掩盖真实故障面。
4. `evidence.py`（1587）与 `assets.py`（1526）以及超 2000 行的评测/恢复脚本会提高
   冲突与回归成本；拆分必须独立切片。

## 3. Non-goals（本轮 ADR 文档本身）

- 不在本次跟进中改 API payload、数据库 schema、Alembic、Asset generation、
  Evidence locator、Citation/NoteSource 或 Research save semantics。
- **本轮 ADR 文档工作不创建 `packages/backend-contracts`，不改 production code，
  不创建新 Docker/build target。** 创建/分发 contracts 与候选 build target 属于
  后续获批切片的计划项。
- 不把当前 PostgreSQL polling 直接替换为 Redis/Kafka；调度方案不是本记录的目标。
- 不把 Research 改成动态 DAG、通用 agent framework 或新的 checkpoint authority。
- 不要求一次性把 ingestion 全部改成 HTTP RPC。
- **本轮不拆分** `evidence.py` / `assets.py` / `test_r803_campaign_v5.py` /
  `v5b_document_restore_acceptance.py`。
- **Branch protection / GitHub 设置保持 unresolved**；本记录不调用仓库保护接口。
- **不替用户批准**任何 transport/事务方案；推荐项仅供决策。

## 4. Proposed Incremental Boundary

### 4.0 Owner 维度（A0 必须分开写清；不得混称）

| 维度 | 含义 | 当前事实 | 备注 |
| --- | --- | --- | --- |
| **Schema / migration owner** | 谁定义表结构、Alembic、ORM model | **API package**（`apps/api`） | 定义归属，不等于运行时 commit |
| **Mutation logic owner** | 谁定义 Research/ingestion 业务写入函数与锁序 | **API package service 实现** | Worker 调用这些函数，不另起一套 ledger 语义 |
| **Session / commit process owner** | 哪个**进程**创建 Session 并执行 commit/rollback | Research：**Worker `_ApiPort`**；Ingestion：共享 Session 边界（API orchestrator + Worker adapter 同会话） | 这是运行时事实 |

Transport 候选的 commit 含义不得混称：

- **Same-DB adapter 跑在 Worker 进程内**：即使 mutation logic 仍是 API service 函数，
  **runtime commit process owner 仍是 Worker**（Session 在 Worker 内打开/提交）。
  不能把它叫做“API-process commit”或笼统的 “API-owned transaction”。
- **Internal HTTP（或其他 RPC）由 API 进程执行写入**：此时 **runtime commit process
  owner 才是 API 进程**。这才是“API-process commit”。
- 文档里的推荐方案 **“API-owned internal service transport”** 必须在 A0 决策门里
  显式选择上述哪一种；**需 owner approval，本 ADR 不替用户批准。**

### 4.1 目标依赖方向（推荐目标，需 owner approval 后才实现）

```text
packages/backend-contracts (纯 DTO / Protocol / 版本化 JSON；无 ORM/settings/provider client)
        ^                         ^
        |                         |
API adapters + ORM/migrations   Worker runtime + modality parsers
        ^                         ^
        |                         |
routers / API service         composition root / transport adapter
```

推荐目标（**不是当前事实，且未获本文件批准**）：

- 跨边界只交换 contracts 中的 DTO/Protocol。
- 在 owner 批准的 transport 下，明确 **session/commit process owner**（见 §4.0）；
  不得把 same-DB-in-Worker 与 API-process HTTP 混写成同一种 “API-owned transaction”。
- Worker 负责解析、OCR、provider/tool execution 和 orchestration。
- 共享 `packages/shared-types` 当前是 TypeScript 包，不应直接承载 Python runtime DTO。

### 4.2 可执行迁移顺序

**A0：只冻结事实、DTO/Protocol 语义、三分 owner + transport 决策门（推荐下一切片）**

1. 准确记录当前事实（并同步正式 SSoT，见 §7/§8）：API package 拥有
   **schema/migration** 与 **mutation logic** 定义；Research Worker `_ApiPort`
   **当前**创建 Session 并 `commit`/`rollback`；ingestion 在共享 Session/ORM 边界；
   系统是模块化双进程，不是独立服务边界。
2. 文档冻结 Research port payload / Protocol **字段语义**。
3. 设立 **决策门（需 owner approval）**，分开批准：
   - schema/migration owner（通常保持 API）；
   - mutation logic owner（通常保持 API service）；
   - session/commit process owner + transport（same-DB-in-Worker vs API-process HTTP 等）。
4. A0 **禁止**：改生产行为、创建 contracts package、创建候选 build target、移除
   API editable dependency、改 schema/Alembic/save。
5. **不得在 A0 声称事务 process owner 已改为 API。**

**A1：获批后创建/版本化/分发 Python backend contracts，再实现批准的 transport（需 owner approval）**

1. 创建 Python-only `packages/backend-contracts`（纯 DTO/Protocol；无 ORM/settings/
   provider client）。
2. API mapper + Worker 只依赖 contracts 类型。
3. 按批准方案实现 transport adapter；在**旧依赖仍存在**时完成行为 oracle。
4. 旧 editable path / 镜像 API source / `PYTHONPATH` **此时仍保留**。

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

详见 §4.0。一句话：**API package = schema/migration + mutation logic 定义；Research
runtime commit process 当前 = Worker `_ApiPort`；ingestion = 共享 Session/ORM。**
推荐 transport 需 owner approval，不在本文件批准。

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

### A0（事实 + 语义 + 三分 owner 决策门；无 package、无生产改动、无新 build target）

- 本 ADR 与下列**正式 SSoT** 同步当前事实（定义归属 vs `_ApiPort` commit vs 共享
  ingestion session），且**不声称 A1 已完成**：
  - [`docs/ssot/system-architecture.md`](../ssot/system-architecture.md)
  - [`docs/architecture/database-design.md`](./database-design.md)
  - [`specs/v5/multimodal-agent-product/v5b-detailed-spec.md`](../../specs/v5/multimodal-agent-product/v5b-detailed-spec.md)
- Research port payload / Protocol 语义成文；transport 与 session/commit process
  owner 仅作为 **需批准** 的决策门。
- 行数事实正确：evidence=1587、assets=1526、r803 campaign test=2461、v5b restore
  script=2006。
- 不创建 contracts package / 候选 build target；不改 production。

### A1（获批后；旧依赖仍在）

- contracts 纯 DTO/Protocol；行为 oracle 通过；legacy API path 仍保留。

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

建议先做 **A0**，并点名同步正式文档：

1. 保持本 ADR 对 `_ApiPort` commit、共享 ingestion session、模块化而非独立服务的准确表述。
2. 同步更新：
   - `docs/ssot/system-architecture.md`
   - `docs/architecture/database-design.md`
   - `specs/v5/multimodal-agent-product/v5b-detailed-spec.md`
3. 请 owner **分别**批准/否决：schema/migration owner、mutation logic owner、
   session/commit process owner + transport（same-DB-in-Worker vs API-process HTTP）。
   推荐方案保持未批准状态。
4. 大文件拆分与 branch protection 保持后置 / unresolved。

A0 获批后再进入 A1。不要把 B pilot、C 独立镜像、大文件拆分与 A0 混成一个大 PR。

## 9. Evidence Snapshot

- `apps/worker/pyproject.toml:6-18`：editable API dependency。
- `infra/docker/Dockerfile.python:28-46`：Worker image copies API source / API
  `PYTHONPATH`。
- `apps/worker/src/ai_pdf_worker/research_runtime_core.py:192-217`：`_ApiPort` creates
  Session and commits/rollbacks on write。
- `apps/api/src/ai_pdf_api/services/ingestion.py:141-224`：shared Session/ORM into
  Worker adapter。
- Line counts（本机 `wc -l`）：`evidence.py` 1587；`assets.py` 1526；
  `test_r803_campaign_v5.py` 2461；`v5b_document_restore_acceptance.py` 2006。
- Import 基线：modules **28**；`ai_pdf_api` import statements **96**；Worker
  `sqlalchemy` modules **12**。

本记录为审查结果，不包含生产代码修改、提交或推送。
