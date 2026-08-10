# V5 详细规格索引

## 文档状态

当前状态：V5-B Markdown-only `document` v1 已批准并完成 isolated/canonical implementation；live migration、scoped PostgreSQL/MinIO restore、standalone browser 和 B008 formal isolated deployment gate 已通过。B008 单一 artifact 已记录 built API/Worker/Web image、双 Document asset PostgreSQL/MinIO restore oracle、API/DOM replay 和 zero-residue；当前仅待最终独立 Critical review 后完成 release closure。V5-C 仍为 `draft-for-approval`，等待 OD-C1/C2/C3/C4/C5/C8。

V5-A 已在 `80d73e3` 完成并推送。V5-B Markdown v1 的 OD-B1/B2/B3/B4 已批准，OD-B5 明确拒绝 HTML，OD-B6/B7 仍阻塞 Audio/Video；本目录中的 V5-B 字段合同和验收记录描述已实现切片。V5-C 文档仍是 owner decision 前的规格，未批准的 C 侧数据库、API 或产品决策不得由实现 worker 自行决定。

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
3. V5-B/V5-C 详细规格：
   - `open-decisions.md`
   - `v5b-detailed-spec.md`
   - `v5c-detailed-spec.md`
   - `implementation-lanes-v5bc.md`
   - `verification-matrix-v5bc.md`
   - `save-contract-checklist.md`
4. `spec.md`、`plan.md`、`tasks.md`：路线索引和状态汇总，不替代上述字段级冻结包。

## 实现顺序

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
  -> V5-D integration
```

V5-B 与 V5-C 可以并行写 spec；生产实现只有在各自 contract gate 通过后才允许并行，而且 lane ownership 必须不重叠。

## 硬规则

- 新模态必须是 `registry + catalog + adapter + typed locator + API DTO + renderer + fixture + recovery tests` 的完整版本切片。
- 不允许用任意 JSON 代替 locator 真相，不允许按 MIME、字段存在性或“第一个可用字段”猜模态。
- 不新增 provider/profile selector，不自动 fallback，不自动 reindex，不在 ASR 未配置时假实现 Audio。
- 不改变 Citation、NoteSource、Quick Chat、Research ledger 或历史保存语义；如确实需要改变，立即停工并走 `save-contract-checklist.md`。
- 所有实现 worker 使用 `grok-4.5`；reviewer 独立执行，可使用更强模型。
- 不把 R803/M404 当作 V5-B/V5-C 的工程完成 gate。
- Audio/Video 不因 tasks checkbox 自动启用：Audio 受 OD-B6 ASR capability contract 阻塞，Video 受 OD-B7 transcript/temporal contract 阻塞。
