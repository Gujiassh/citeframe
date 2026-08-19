<!-- status note: V5-F package added 2026-08-13; see decision-2026-08-13-v5f-scope.md -->
# V5 详细规格索引

## 文档状态

当前状态（2026-08-18）：V5-B/C/D/F、V5-A、architecture-hardening 与 PPTX layout/embed preview 的工程实现和验收已关闭；产品阶段为 `internal_preview`。R803 真实模型质量与 M404 用户价值仍为 `not_evaluable`。当前唯一执行入口是 [`current-execution-plan.md`](current-execution-plan.md)，只维护 ops 真复配和 V5-E 后置证据；旧 V5-D/W1 “进行中”描述均为历史记录。

V5-A 已在 `80d73e3` 完成并推送。V5-B 当时的 Markdown-only 决策、OD-B5 拒绝和 OD-B6/B7 阻塞只描述原始 V5-B 切片；这些模态后来经 V5-F 独立批准、实现并关闭。既有字段合同和验收记录继续有效；任何新的数据库/API/save/recovery 影响仍需 main controller 串行审核。

## 权威顺序

1. 现有运行时合同：
   - `docs/architecture/modality-extension-contract.md`
   - `docs/architecture/api-contracts.md`
   - `docs/architecture/evidence-migration-impact.md`
   - `docs/architecture/research-workflow-runtime.md`
   - `specs/v4/evidence-research-workflow/`
2. V5-A 已冻结合同：
   - `decision-2026-08-04-provider-capability-contract.md`
   - 已推送的 V5-A production code 和 regression tests
3. V5-B/V5-C/V5-D 详细规格：
   - `open-decisions.md`
   - `v5b-detailed-spec.md`
   - `v5c-detailed-spec.md`
   - `decision-2026-08-11-v5d-scope.md`
   - `v5d-detailed-spec.md`
   - `implementation-lanes-v5bc.md`
   - `implementation-lanes-v5d.md`
   - `verification-matrix-v5bc.md`
   - `verification-matrix-v5d.md`
   - `grok-handoff-v5d.md`
   - `save-contract-checklist.md`
4. **当前执行 SSOT**（2026-08-18，唯一当前入口）：
   - `current-execution-plan.md`
   - `collaboration-mode-lane-pairs.md` 与 `pdf-in-page-visual-v1.md` 是已关闭执行方式/合同记录，不是并列当前入口
5. V5-F 模态补全 + Agent 协作完善：
   - `decision-2026-08-13-v5f-scope.md`
   - `parallel-execution-plan-v5f.md`
   - `pdf-in-page-visual-v1.md`
   - `v5f-detailed-spec.md`
   - `implementation-lanes-v5f.md`
   - `verification-matrix-v5f.md`
   - `plan-audit-v5f.md`
   - `grok-handoff-v5f.md`
6. `spec.md`、`plan.md`、`tasks.md`：路线索引和状态汇总，不替代上述字段级冻结包。

## 历史实现顺序（已关闭）

```text
Process Gate 0
  -> B-G1 modality brief / C-G1 V4 delta approval
  -> B-G2 shared-entry audit
  -> B-G3 first modality contract approval
  -> B-G4 first modality implementation
  -> B-G5 mixed-workspace lifecycle/recovery
  -> B-G6 independent Critical review and registry enablement
  -> B-G7 ASR/temporal prerequisites for Audio/Video
  -> C-G2/C-G3 Research productization contract
  -> C-G4/C-G5 Web control/timeline productization
  -> C-G6 boundary audit
  -> C-G7 full regression
  -> D-G0 baseline/contract gate
  -> D-G1 mixed scope/retrieval
  -> D-G2 desktop/mobile primary paths
  -> D-G3 restart/delete/restore/deployment
  -> D-G4 runbook/diagnostics
  -> D-G5 full regression and Critical review
  -> V5-D internal-preview engineering gate
```

V5-B 与 V5-C 可以并行写 spec；V5-D/F 的并行执行也已完成。当前不再开启 W1/W2/W3；剩余执行仅按 [`current-execution-plan.md`](current-execution-plan.md) 的 OPS/V5-E residual board 进行。

## 硬规则

- 新模态必须是 `registry + catalog + adapter + typed locator + API DTO + renderer + fixture + recovery tests` 的完整版本切片。
- 不允许用任意 JSON 代替 locator 真相，不允许按 MIME、字段存在性或“第一个可用字段”猜模态。
- 不新增 provider/profile selector，不自动 fallback，不自动 reindex，不在 ASR 未配置时假实现 Audio。
- 不改变 Citation、NoteSource、Quick Chat、Research ledger 或历史保存语义；如确实需要改变，立即停工并走 `save-contract-checklist.md`。
- 历史 V5-F 执行约束（已结束）：当时实现 worker 使用 `grok-4.5`，reviewer 独立执行；这不是当前 residual execution 的模型要求。
- 不把 R803/M404 当作 V5-B/V5-C/V5-D 的工程完成 gate。
- 历史 V5-D 执行约束（已结束）：当时 agent 必须先读 V5-D decision/spec/lanes/matrix/handoff；这些文件现在只作冻结合同和验收追溯。
- Audio/Video 当前状态：OD-B6/B7 已在 V5-F 获批，ASR/temporal 合同、生产注册和验收均已关闭；未来扩展仍须独立 decision/gate，不能只改 tasks checkbox。
