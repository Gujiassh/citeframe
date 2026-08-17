# Architecture Hardening (post V5-F)

Date: 2026-08-15  
Status: **implemented Phase 1+2** (branch work/arch-hardening-full-20260815)  
Product stage: `internal_preview`  
Base: `main` after PR #13 (`3c1c517`)

## Why this package exists

V5-F closed the multimodal + fixed-DAG engineering surface. A deep review then scored four areas as the highest structural/product debt:

| Area | Review score | Problem in one line |
| --- | --- | --- |
| Service boundaries | 6.5/10 | Worker/API share ORM; Chat leaks PDF crop |
| Modality extensibility | 8.5/10 | Protocol strong; shared-layer special cases growing |
| Research architecture | 7/10 | Correct fixed DAG, ~12k lines cognitive load |
| Product narrative vs implementation | 6/10 | SSoT/README lag; depth ladder unclear |

This package is **optimization and debt control**, not new modalities and not R803/M404.

## Documents

| File | Role |
| --- | --- |
| [`decision-2026-08-15-architecture-hardening.md`](decision-2026-08-15-architecture-hardening.md) | Approved-scope decision; **implemented** Phase 1+2 on main (PR #14/#15) |
| [`spec.md`](spec.md) | Requirements, non-goals, acceptance |
| [`plan.md`](plan.md) | Lanes, ownership, sequence, risks |
| [`verification-matrix.md`](verification-matrix.md) | Gates and evidence |
| [`tasks.md`](tasks.md) | Checkbox work breakdown |
| [`reviews/2026-08-15-plan-audit.md`](reviews/2026-08-15-plan-audit.md) | Independent plan audit |

## Relation to other specs

- Does **not** reopen V5-E (R803/M404) unless owner authorizes.
- Does **not** change Asset/Evidence locator meanings or save semantics.
- Reuses contracts in `docs/architecture/modality-extension-contract.md` and `docs/architecture/research-workflow-runtime.md`.
- Lane N narrative updates landed with the package; residual non-goals remain in `tasks.md` (R803/M404, rename, dynamic DAG, etc.).

## Default recommendation

Implement in order **N → B → M → R** (narrative first is cheap and reduces wrong decisions; then boundaries; modality registry purity; Research freeze/docs last if no code change needed).
