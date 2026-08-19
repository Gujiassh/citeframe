# Post-V5 Optimization

Date: 2026-08-19

Status: **planned / implementation not authorized**

Product stage: `internal_preview`

This package turns the 2026-08 architecture review into four bounded follow-up
lanes. It is a planning artifact only. No production code, persistence contract,
GitHub repository setting, paid evaluation, or user study is authorized by this
package.

| Area | Baseline score | Primary fact |
| --- | ---: | --- |
| Architecture boundary | 6.0/10 | Worker imports API internals and shares ORM/session boundaries |
| Maintainability | 6.5/10 | Several production, evaluation, and acceptance files have mixed responsibilities |
| Product completeness | 7.0/10 | Nine modalities are vertically connected, but depth and quality evidence are uneven |
| Delivery governance | 5.5/10 | `main` has no branch protection or repository ruleset |

## Documents

| File | Purpose |
| --- | --- |
| [`spec.md`](spec.md) | Goals, constraints, facts, and owner decision gates |
| [`plan.md`](plan.md) | Sequenced lanes, dependencies, estimates, and acceptance oracles |
| [`tasks.md`](tasks.md) | Unstarted work breakdown; checkboxes are not implementation authorization |
| [`reviews/`](reviews/) | Independent plan review evidence |

## Recommended Order

1. Authorize delivery governance and freeze the API/Worker A0 ownership decision.
2. Establish baselines and guards before moving code.
3. Introduce contracts and perform one non-semantic file split at a time.
4. Build the modality capability/quality matrix and run authorized R803/M404 evidence work.
5. Select one product-depth investment from evidence; do not deepen every modality in parallel.
6. Attempt an API-source-free Worker build only after all runtime imports and behavior oracles pass.

Related current facts:

- [`docs/architecture/api-worker-boundary-follow-up-2026-08-18.md`](../../../docs/architecture/api-worker-boundary-follow-up-2026-08-18.md)
- [`specs/v5/architecture-hardening/`](../architecture-hardening/)
- [`specs/v5/multimodal-agent-product/current-execution-plan.md`](../multimodal-agent-product/current-execution-plan.md)
