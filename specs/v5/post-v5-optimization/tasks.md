# Tasks: Post-V5 Optimization

Status: **Design re-audit ACCEPT (High=0, Medium=0, Low=0); A1 independently accepted
on 2026-08-20; A1b/A2-foundation independently accepted on 2026-08-21 by the follow-up
Critical review (`High=0`, `Medium=0`, `Low=0`); PR #20 is merged at `origin/main@9f40241`; PR #21 head `1d81470` is merged at `origin/main@8674d4dc407048471f7b14b23b821e72529487bf` with `6/6` CI, delivering A2a and R0. A2a delivery includes Worker-environment CI fix `4b24181` and ledger `1d81470`. Current branch `work/research-r1-single-attempt-20260824` starts at `8674d4d`; R1 initial candidate `f4a1d1d7451d707d90948612791d1bb2aac410f3` is followed by immutable runtime rework `473213d79154f3fbcf6044e1c4e62ed65038e1c1`. The rework is committed locally, not pushed, and the branch has no upstream or remote branch. R1 is implementer-complete. Initial Critical review is `REWORK (High=0, Medium=4, Low=0)`; a new independent Critical follow-up is pending and no R1 `ACCEPT` is claimed. R2/W1/per-Run admission and downstream remain blocked. No schema/API/save/replay/permission change is authorized**.

Checkboxes distinguish authorization from implementation. The checked A1 item records
implementer-complete code and evidence; later checked authorization items do not claim
code, schema, API, SSE, repository settings, provider spend, or user research was implemented.

## Plan Closure

- [x] Verify architecture/import/line-count/modality/governance baseline
- [x] Write spec and sequenced plan
- [x] Independent plan audit ACCEPT (2026-08-19)
- [x] Record owner-authorized A0/R/W target direction in the implementation-ready design (2026-08-20; docs only)
- [x] Independent Critical re-audit of the revised design ACCEPT (High=0, Medium=0, Low=0)
- [x] Implement bounded A1 contracts slice (2026-08-20); independently accepted on 2026-08-20
- [x] Independent Critical review of the A1 implementation ACCEPT (2026-08-20)

## G: Delivery Governance

- [ ] G0 Approve exact `main` ruleset, available reviewer count, and emergency bypass
- [ ] G1 Require PR + resolved conversations + six CI checks; block force-push/delete
- [ ] G2 Add concurrency cancellation and missing timeouts
- [ ] G3 Upgrade Node 20-era action versions and prove job parity

G0-G3 and all GitHub repository settings remain unauthorized.

## A/R/W: Boundary And Research Runtime

### Authorized direction, documentation only

- [x] A0 Freeze same-DB adapter; API HTTP/auth/Alembic/schema governance; Worker orchestration; Worker-side Research UoW commit-process ownership
- [x] A0 Freeze `citeframe_contracts` / `citeframe_persistence` / `citeframe_research_persistence` ownership; prohibit copied mappings/transitions and `citeframe_research_persistence -> ai_pdf_api` imports
- [x] A0 Freeze unchanged Step/Attempt/Claim/Event/save/replay/permission semantics and the existing lock/fencing contract
- [x] R/W Freeze PostgreSQL-only orchestration, one-claimed-attempt dispatcher target, admission target semantics, and independent SSE target; freeze does not authorize admission implementation
- [x] R0 Freeze Run-first lock normalization target; accepted implementation remains separate from A2a/R1

### Production implementation, R1 rework implementer-complete; Critical follow-up pending

- [x] A1 Add only `citeframe-backend-contracts` / `citeframe_contracts` pure DTO/Protocol package; API/Worker add only its local path and stage-specific export/smoke; no persistence or Research package scaffold (independently accepted 2026-08-20)
- [x] A1b / A2-foundation Add `citeframe-backend-persistence` / `citeframe_persistence` on top of A1 as unique Base/metadata and all-model mapping distribution; extend manifests, Docker COPY/PYTHONPATH, and smoke with zero DDL drift (implementer-complete 2026-08-20; independently accepted 2026-08-21 by follow-up Critical review: High=0, Medium=0, Low=0)
- [x] A2a initial snapshot `20d411e` implemented the third package but failed independent Critical review (`REWORK`, High=1, Medium=5, Low=1)
- [x] A2a bounded core/supply-chain repair accepted at `215cd52` and later delivered through PR #21
- [x] Candidate neutral production composition (`uowEnterCount=38`), final differential/boundary `8 passed`, full API/Worker partitions, deploy `6+2`, and same-pinned-digest mirror image/runtime smokes recorded
- [x] Final independent A2a Critical `ACCEPT (High=0, Medium=0, Low=0)` in [`reviews/a2a-persistence-critical-reaudit-2026-08-24.md`](reviews/a2a-persistence-critical-reaudit-2026-08-24.md), local review commit `eb97adf`
- [x] Deliver A2a/R0 through PR #21 head `1d81470` to `origin/main@8674d4d` with `6/6` CI; includes A2a CI fix `4b24181` and exact Worker-environment ledger `1d81470`
- [x] R0 Normalize all mutation lock acquisition to `Run -> Step -> Attempt -> Call -> Ledger` at production `39766c37`, preserving save/API semantics
- [x] R0 final ledger closure `6b8ab475` and independent Critical [`ACCEPT (High=0, Medium=0, Low=0)`](reviews/r0-lock-normalization-critical-review-2026-08-24.md) at review `9d4297f8`; delivered through PR #21
- [x] R0 evidence: PostgreSQL 17.10 `7/7`, report `95f2608e...`, deadlocks `0 -> 0`, no `40P01`/`55P03`, focused `8`, API `90+49`, Worker `43`, A2a equal `7/7`
- [x] Integrate the accepted R0 chain through PR #21
- [x] R1 candidate `f4a1d1d` implements one outer claim / one handler and bounded independent dispatcher loops from start `8674d4d`
- [x] R1 immutable runtime rework `473213d` (local/no-push/no-upstream/no-remote) closes the human-owned gate mutation and simultaneous ingestion/dispatcher error-loss paths; post-rework Worker `349`, gate `64+40`, API `132`, A2a handled `3 -> 8` / UoW `43`, PostgreSQL `7/7` deadlocks `0`
- [x] R1 canonical M4 status sync records PR #21 delivery, candidate/rework state, exact evidence, initial REWORK, and blocked downstream gates
- [ ] New independent R1 Critical follow-up after initial [`REWORK (High=0, Medium=4, Low=0)`](reviews/r1-single-attempt-dispatcher-critical-review-2026-08-24.md); no `ACCEPT` claimed
- [ ] R2 Prove two-or-more Worker contention, cap=1/N, cap-full Run skipping/fairness/no-starvation, equal-time Step ordering, lease expiry/late completion, cancel/provider races, join/conflict/recovery on real PostgreSQL
- [ ] W1 Implement single-flight/dirty rerun, monotonic event gate, Run-switch abort/discard, event-directed artifact cache, terminal flush, and replay fallback
- [ ] A3 Freeze ingestion result/object/hash/compensation contract and pilot one modality; pilot is not an A5 entry gate
- [ ] A4 Migrate the other eight modalities and composition root
- [ ] A5 Prove candidate Worker import/compile/start/ingest/Research/recovery/version-mismatch without API source/editable dependency/PYTHONPATH
- [ ] A6 Replace legacy Worker target only after A5 and pass deploy/restore regression

A1b/A2-foundation, A2a, and R0 are accepted; A2a/R0 were delivered by PR #21 at
`origin/main@8674d4d` with `6/6` CI. R1 chain `f4a1d1d -> 473213d` is implementer-complete; `473213d` is local/not pushed with no upstream or remote branch but not accepted. The initial Critical review is
`REWORK (High=0, Medium=4, Low=0)` and the follow-up is pending. Human-owned gates now prove
zero mutation and simultaneous ingestion/dispatcher errors are preserved. R2/W1/per-Run
admission and downstream remain blocked; no schema/API/save/replay/permission change is
authorized.

## M: Maintainability

- [ ] M0 Add reproducible size/import/function baseline and ownership map
- [ ] M1 Split `modalities/evidence.py` without semantic change
- [ ] M2 Split `routers/assets.py` without HTTP/auth/streaming change
- [ ] M3 Split M402 execution service with byte-identical report
- [ ] M4 Split `test_r803_campaign_v5.py` without changing test/frozen evidence meaning
- [ ] M5 Split restore acceptance script without changing CLI/report/cleanup
- [ ] M6 Split M402 tests without reducing adversarial coverage

M work remains unstarted and is not authorized by A0/R/W.

## P: Product Completeness

- [ ] P0 Approve users/tasks/weights and publish nine-modality capability/value matrix
- [ ] P1a Authorize and run a new R803 campaign; preserve frozen v1
- [ ] P1b Approve and run M404 protocol with qualified users
- [ ] P1c Hold separate engineering/model-quality/user-value release review
- [ ] P2 Select Office depth only if matrix evidence ranks it first
- [ ] P3 Select Audio depth only if matrix evidence ranks it first
- [ ] P4 Select Video depth only if matrix evidence ranks it first

P work, provider spend, and user research remain unapproved.

## Contract Stop Rules

- [ ] Any persistence/API/save/replay/permission meaning change stops for `A-DATA` approval
- [ ] Any GitHub repository setting mutation stops for `G0` approval
- [ ] Any provider spend stops for `P-R803` approval
- [ ] Any user research stops for `P-M404` approval
- [ ] Any unproved lock-order change stops for an independent Critical design and deadlock proof
- [ ] Any depth slice lacking a real fixture and measurable user task remains unstarted
