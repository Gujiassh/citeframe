# R100 Evaluation-first 基线

## 状态

- 阶段：R100 exit gate passed
- 日期：2026-07-27
- 范围：Research fixture、claim/evidence 标签、失败 taxonomy、scorer 和可重放 Quick baseline
- 不代表：Deep Research 模型质量、多 Agent 增益、M404 用户价值或生产发布通过

## 输入

| 输入 | 作用 |
| --- | --- |
| [`r100-research-cases-v1.json`](r100-research-cases-v1.json) | 6 个比较、综合、冲突、Evidence gap 和拒答案例；冻结 Asset scope、Claim 与 Evidence labels |
| [`r100-quick-baseline-v1.json`](r100-quick-baseline-v1.json) | 同一 PDF/Image fixture 和 `openai/gpt-5.5` 捕获条件下的 Quick reference |
| [`multimodal-golden-v1.json`](multimodal-golden-v1.json) | 21-case PDF/Image/mixed 工程集和 3 个 fixture |
| [`retrieval-v1.jsonl`](retrieval-v1.jsonl) | 40-case 真实 PDF retrieval reference |
| [`multimodal-failures-v1.json`](multimodal-failures-v1.json) | 10 类失败 taxonomy 和既有 regression nodes |

R100 不直接复制 40-case retrieval 问题作为 Agent 质量结论。Research cases 只复用已冻结 fixture、真实模型捕获和
Evidence locator；后续 Deep 运行必须使用同一 scope/provider/model 与 scorer 才能做成对比较。

## 执行

```bash
uv run --project apps/api pytest apps/api/tests/test_r100_research_eval.py
uv run --project apps/api python apps/api/scripts/evaluate_r100.py \
  --output docs/evals/artifacts/r100-v1/report.json
```

核心实现位于 `ai_pdf_api.services.r100_evaluation`。CLI 只负责输入参数和写出报告，测试直接调用 service，避免
脚本目录成为隐式运行时模块。

## 结果

| 门禁 | 结果 |
| --- | ---: |
| Research cases | 6 |
| Claim support replay | 1.0 |
| Evidence recall replay | 1.0 |
| Locator accuracy replay | 1.0 |
| Conflict decision replay | 1.0 |
| Refusal replay | 1.0 |
| Engineering gate | passed |
| Model quality evaluated | false |
| User value validated | false |

Canonical report 和闭集 hash 位于 [`artifacts/r100-v1/`](artifacts/r100-v1/)。`captured_reference_only` 指这些指标
证明标签、scorer 和 Quick capture 可以确定性重放；不能把 1.0 解释成尚未执行的 Deep Research 质量。

## 下一门禁

R100 已允许进入 R200/R300。实现必须保持 R000 的不变量：Quick 合同不变、Research 账本独立、Evidence-only
tools、Verifier fail-closed、Research SSE 与 Chat SSE 分离。Deep Research 实际执行完成后，才在 R800/R700
使用本 R100 fixture 生成 Quick/Research 成对质量、延迟、成本和恢复报告。
