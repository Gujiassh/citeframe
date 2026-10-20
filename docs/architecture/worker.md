# Worker 目录与离线评测边界

## 产品模块

`apps/worker/src/ai_pdf_worker/`：

| 路径 | 职责 |
|---|---|
| `main.py` / `metrics.py` | 进程启动、轮询/dispatcher 组合、停机与进程指标 |
| `ingestion/` | 九类摄取 adapter，以及 PDF/Image/HTML/Markdown/OCR 解析能力 |
| `research/runtime.py` | 生产 Research 运行时公共入口 |
| `research/processor.py` | 领取并处理单个 attempt，组合 service 与 dispatcher |
| `research/handlers.py` | 持久化 step kind 的 handler 和单 attempt 调度 |
| `research/agents.py` / `schemas.py` | 模型角色的输入、生成输出验证与 schema |
| `research/executor.py` / `engine.py` | 有界执行器公共入口与图执行实现；生产单 attempt dispatcher 不加载 engine/LangGraph |
| `research/tools.py` | Evidence 工具合同、作用域与结果校验 |
| `research/core.py` | 运行时协议、快照转换、lease heartbeat 与 UoW 基础能力 |
| `research/adapters/ledger.py` | 持久化账本端口适配 |
| `research/adapters/evidence.py` | 冻结 Evidence 检索/加载端口适配 |
| `research/adapters/generation.py` | 预留、调用、核算 provider 的适配器 |
| `research/persistence.py` | 中立 persistence commands 与 API 读/存储能力的组合根 |

`packages/backend-contracts/src/citeframe_contracts/validation.py` 拥有
`AgentResultValidationError`。它只保存验证失败的 node/rule/path/call/hash 元数据。
生产角色通过已有 `output_observer` 和 validator 注入点提供记录接口，默认业务错误码不变。
评测的原始输出捕获、secret scan、失败归因和文件写入留在评测包。

## 离线工具

`tools/evaluation` 是具有 pyproject、锁文件、wheel/sdist、console scripts 和独立测试的 Python 包。

- `cli/`：paired evaluation 与 prospective campaign 命令入口。
- `acceptance/`：Research 的 seed、scenarios、snapshot、verify 与 CLI。
- `runtime/fixtures.py`：冻结 Evidence 实验和执行快照。`FrozenEvidencePort.search` 按冻结资产与固定顺序选择证据，保留忽略 query 的实验语义。
- `runtime/quick.py`、`research.py`、`failures.py`：两种 case 执行与失败诊断绑定。
- `campaign/plan.py`、`rounds.py`、`runner.py`：冻结计划、单轮执行、campaign 调度。
- `campaign/storage.py`、`reporting.py`、`recovery.py`：持久化写入、指标汇总、恢复与完整性验证。
- `contracts.py`、`provider.py`、`policy.py`、`structured_output.py`、`scoring.py`、`diagnostics.py`、`integrity.py`：评测合同、provider 记录、策略、传输 schema、评分、诊断与散列证据。

## 依赖规则与范围

允许 `evaluation -> Worker/API/public contracts/persistence`。
禁止产品 Worker、API、共享合同及 persistence 包导入 `citeframe_evaluation`；lazy/dynamic import 同样受检查。
API 的产品 Evaluation API/数据库账本继续位于 API/共享 persistence，离线执行工具单独分发。

生产 API/Worker Docker target 不包含离线工具。Research 验收使用显式 `evaluation` target；
生产 Worker 命令仍是 `python -m ai_pdf_worker.main`。
