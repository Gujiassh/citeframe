# Post-V5 Optimization

Date: 2026-08-19

Status: **Design re-audit ACCEPT (High=0, Medium=0, Low=0); A1 independently accepted on 2026-08-20; A1b/A2-foundation independently accepted on 2026-08-21 (follow-up Critical review ACCEPT; High=0, Medium=0, Low=0); A2a is implementer-complete; independent Critical review is pending; R0/R1/R2/W1 and downstream remain blocked**

Product stage: `internal_preview`

Owner has authorized the A0/R/W architecture direction (same-DB adapter, Worker
orchestration, one-claimed-attempt runtime, and independent Research SSE work). Package
staging is strictly A1 contracts -> A1b/A2-foundation persistence -> A2a Research
persistence; no later-stage package scaffold is allowed early. The design re-audit is
accepted with `High=0`, `Medium=0`, `Low=0`. A1 was independently accepted on `2026-08-20`. A1b/A2-foundation was independently
accepted on `2026-08-21` by the follow-up Critical review (`High=0`, `Medium=0`, `Low=0`).
Implementation evidence is recorded in `reviews/a1b-persistence-implementation-2026-08-20.md`;
the reviewer-owned result is `reviews/a1b-persistence-critical-audit-2026-08-20.md`.
A2a is implementer-complete; independent Critical review is pending. R0, R1, R2, W1, and downstream slices remain
conditionally authorized, unstarted, and blocked. No schema/API/save/replay/permission changes are authorized.
G/M/P and GitHub repository settings remain unauthorized.

This package turns the 2026-08 architecture review into four bounded follow-up
lanes. A1 was independently accepted on `2026-08-20`; its evidence is recorded in
`reviews/a1-contracts-implementation-2026-08-20.md`. A1b/A2-foundation was independently
accepted on `2026-08-21` by the follow-up Critical review (`High=0`, `Medium=0`, `Low=0`).
Implementation evidence is recorded in `reviews/a1b-persistence-implementation-2026-08-20.md`;
the reviewer-owned result is `reviews/a1b-persistence-critical-audit-2026-08-20.md`.
A2a is implementer-complete; independent Critical review is pending. R0, R1, R2, W1, and downstream slices remain
conditionally authorized, unstarted, and blocked. No schema/API/save/replay/permission changes are
authorized, and G/M/P, GitHub settings, paid evaluation, and user study remain outside
this status.

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
| [`tasks.md`](tasks.md) | Slice state; authorization and implementation status are kept separate |
| [`research-boundary-runtime-design.md`](research-boundary-runtime-design.md) | Implementation-ready Research boundary, dispatcher, locking, admission, SSE, and oracle design |
| [`reviews/`](reviews/) | Independent plan/re-audit evidence |
| [`reviews/a2a-persistence-implementation-2026-08-21.md`](reviews/a2a-persistence-implementation-2026-08-21.md) | A2a implementer evidence; independent Critical review pending |

## Recommended Order

1. Record the owner-authorized A0/R/W direction and the accepted design re-audit (`High=0`, `Medium=0`, `Low=0`).
2. Preserve the final independent A1b follow-up Critical review ACCEPT (`High=0`, `Medium=0`, `Low=0`) and its clean-image evidence in the linked artifacts.
3. A2a Research persistence extraction is implementer-complete; finish its independent Critical review before implementing R0 lock normalization, then keep R1 one-claimed-attempt dispatch in a separate PR.
4. Prove R1/R2 with real PostgreSQL and two or more Workers after R0; implement W1 as an independent SSE slice.
5. Migrate all nine ingestion modalities in A3/A4 before claiming an API-source-free Worker candidate in A5.
6. Keep G/M/P and GitHub settings behind their own authorization gates.

Related current facts:

- [`docs/architecture/api-worker-boundary-follow-up-2026-08-18.md`](../../../docs/architecture/api-worker-boundary-follow-up-2026-08-18.md)
- [`specs/v5/architecture-hardening/`](../architecture-hardening/)
- [`specs/v5/multimodal-agent-product/current-execution-plan.md`](../multimodal-agent-product/current-execution-plan.md)
