# Post-V5 Optimization

Date: 2026-08-19

Status: **Design re-audit and A1/A1b are accepted; PR #20 is merged at `origin/main@9f40241`; PR #21 head `1d81470` is merged at `origin/main@8674d4dc407048471f7b14b23b821e72529487bf` with `6/6` CI, delivering A2a/R0. R1 was independently `ACCEPTED` on 2026-08-25 (`High=0`, `Medium=0`, `Low=0`) across start `8674d4dc407048471f7b14b23b821e72529487bf`, historical initial candidate `f4a1d1d7451d707d90948612791d1bb2aac410f3` (`REWORK`), runtime rework `473213d79154f3fbcf6044e1c4e62ed65038e1c1`, ledger `652cfd47f8bc462038e1bd623afc2b33a4ce511a`, canonical docs `559997d073cc2d26fb346c30e2ab9f20550b673f`, delivery truth `80d395d4fd19c0146b22befc2929bc556cfe62fa`, and review `5a55489fef8380f78854f10666a2fdd2983beeff`. All R1 commits are local and not pushed; the branch has no upstream and no remote branch. R2 is the only next separately gated module; W1/per-Run admission and downstream remain blocked. No schema/API/save/replay/permission change is authorized**

Product stage: `internal_preview`

Owner has authorized the A0/R/W architecture direction (same-DB adapter, Worker
orchestration, one-claimed-attempt runtime, and independent Research SSE work). Package
staging is strictly A1 contracts -> A1b/A2-foundation persistence -> A2a Research
persistence; no later-stage package scaffold is allowed early. The design re-audit is
accepted with `High=0`, `Medium=0`, `Low=0`. A1 was independently accepted on `2026-08-20`. A1b/A2-foundation was independently
accepted on `2026-08-21` by the follow-up Critical review (`High=0`, `Medium=0`, `Low=0`).
Implementation evidence is recorded in `reviews/a1b-persistence-implementation-2026-08-20.md`;
the reviewer-owned result is `reviews/a1b-persistence-critical-audit-2026-08-20.md`.
A2a/R0 were delivered by PR #21 at `origin/main@8674d4d`. R1 chain `8674d4d -> f4a1d1d(REWORK) -> 473213d -> 652cfd4 -> 559997d -> 80d395d -> 5a55489` is independently `ACCEPTED (High=0, Medium=0, Low=0)` on 2026-08-25. All R1 commits are local/not pushed with no upstream or remote branch. R2 is the only next separately gated module; W1/admission/downstream remain blocked. No schema/API/save/replay/permission changes are authorized.
G/M/P and GitHub repository settings remain unauthorized.

This package turns the 2026-08 architecture review into four bounded follow-up
lanes. A1 was independently accepted on `2026-08-20`; its evidence is recorded in
`reviews/a1-contracts-implementation-2026-08-20.md`. A1b/A2-foundation was independently
accepted on `2026-08-21` by the follow-up Critical review (`High=0`, `Medium=0`, `Low=0`).
Implementation evidence is recorded in `reviews/a1b-persistence-implementation-2026-08-20.md`;
the reviewer-owned result is `reviews/a1b-persistence-critical-audit-2026-08-20.md`.
A2a/R0 were delivered by PR #21 at `origin/main@8674d4d`. R1 chain `8674d4d -> f4a1d1d(REWORK) -> 473213d -> 652cfd4 -> 559997d -> 80d395d -> 5a55489` is independently `ACCEPTED (High=0, Medium=0, Low=0)` on 2026-08-25. All R1 commits are local/not pushed with no upstream or remote branch. R2 is the only next separately gated module; W1/admission/downstream remain blocked. No schema/API/save/replay/permission changes are
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
| [`reviews/a2a-persistence-implementation-2026-08-21.md`](reviews/a2a-persistence-implementation-2026-08-21.md) | Historical initial A2a snapshot evidence; superseded after Critical REWORK |
| [`reviews/a2a-persistence-critical-audit-2026-08-24.md`](reviews/a2a-persistence-critical-audit-2026-08-24.md) | Initial A2a Critical REWORK (`High=1`, `Medium=5`, `Low=1`) |
| [`reviews/a2a-persistence-rework-implementation-2026-08-24.md`](reviews/a2a-persistence-rework-implementation-2026-08-24.md) | Accepted immutable production/docs evidence and local delivery ledger |
| [`reviews/a2a-persistence-critical-reaudit-2026-08-24.md`](reviews/a2a-persistence-critical-reaudit-2026-08-24.md) | Final independent A2a Critical `ACCEPT (High=0, Medium=0, Low=0)`; record commit `eb97adf` |
| [`reviews/r0-lock-normalization-implementation-2026-08-24.md`](reviews/r0-lock-normalization-implementation-2026-08-24.md) | R0 implementation and durable ledger history |
| [`reviews/r0-lock-normalization-critical-review-2026-08-24.md`](reviews/r0-lock-normalization-critical-review-2026-08-24.md) | Final independent R0 Critical `ACCEPT (High=0, Medium=0, Low=0)`; delivered by PR #21 |
| [`reviews/r1-single-attempt-dispatcher-implementation-2026-08-24.md`](reviews/r1-single-attempt-dispatcher-implementation-2026-08-24.md) | Accepted R1 runtime/ledger evidence |
| [`reviews/r1-single-attempt-dispatcher-critical-review-2026-08-24.md`](reviews/r1-single-attempt-dispatcher-critical-review-2026-08-24.md) | Historical initial `REWORK`; final Critical `ACCEPT (High=0, Medium=0, Low=0)` at `5a55489` |

## Recommended Order

1. Record the owner-authorized A0/R/W direction and the accepted design re-audit (`High=0`, `Medium=0`, `Low=0`).
2. Preserve the final independent A1b follow-up Critical review ACCEPT (`High=0`, `Medium=0`, `Low=0`) and its clean-image evidence in the linked artifacts.
3. Preserve PR #21 delivery at `origin/main@8674d4d` and its `6/6` CI evidence; A2a/R0 are delivered, not local-pending work.
4. Preserve local R1 `ACCEPT` chain through review `5a55489`; remote push/PR/integration remains pending. R2 is the only next separately gated module. Keep W1/admission/downstream blocked.
5. Migrate all nine ingestion modalities in A3/A4 before claiming an API-source-free Worker candidate in A5.
6. Keep G/M/P and GitHub settings behind their own authorization gates.

Related current facts:

- [`docs/architecture/api-worker-boundary-follow-up-2026-08-18.md`](../../../docs/architecture/api-worker-boundary-follow-up-2026-08-18.md)
- [`specs/v5/architecture-hardening/`](../architecture-hardening/)
- [`specs/v5/multimodal-agent-product/current-execution-plan.md`](../multimodal-agent-product/current-execution-plan.md)
