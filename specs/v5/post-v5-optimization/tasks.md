# Tasks: Post-V5 Optimization

Status: **Design re-audit ACCEPT (High=0, Medium=0, Low=0); A1 independently accepted
on 2026-08-20; A1b/A2-foundation independently accepted on 2026-08-21 by the follow-up
Critical review (`High=0`, `Medium=0`, `Low=0`); PR #20 is merged at `origin/main@9f40241`; PR #21 head `1d81470` is merged at `origin/main@8674d4dc407048471f7b14b23b821e72529487bf` with `6/6` CI, delivering A2a/R0. R1 was independently `ACCEPTED` on 2026-08-25 (`High=0`, `Medium=0`, `Low=0`) across start `8674d4dc407048471f7b14b23b821e72529487bf`, historical initial candidate `f4a1d1d7451d707d90948612791d1bb2aac410f3` (`REWORK`), runtime rework `473213d79154f3fbcf6044e1c4e62ed65038e1c1`, ledger `652cfd47f8bc462038e1bd623afc2b33a4ce511a`, canonical docs `559997d073cc2d26fb346c30e2ab9f20550b673f`, delivery truth `80d395d4fd19c0146b22befc2929bc556cfe62fa`, and review `5a55489fef8380f78854f10666a2fdd2983beeff`. The complete R1 chain was delivered by PR #22 at `origin/main@a616eea1350b095c6f229890d2c47e5010902330` with `6/6` CI. R1.5 admission is independently Critical ACCEPTED (findings=0). R2 A-J/L are independently accepted proof-only checkpoints; K remains stopped at `A-DATA`, so R2/W1/downstream are not complete. No schema/API/save/replay/permission change is authorized**.

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

### Production implementation, R1 delivered; R1.5 admission precedes R2 proof-only

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
- [x] R1 ledger `652cfd4`, canonical docs `559997d`, delivery truth `80d395d`, and final independent [`ACCEPT (High=0, Medium=0, Low=0)`](reviews/r1-single-attempt-dispatcher-critical-review-2026-08-24.md) at review `5a55489`
- [x] Deliver the accepted R1 chain through PR #22 to `origin/main@a616eea` with `6/6` CI
- [x] R1.5 Implement per-Run researcher admission using the existing positive `SmallInteger` snapshot cap and Attempt rows: DB-time active-lease count after locking Run; cap-full whole-UoW rollback with zero Step/Attempt/Event/Run mutation; nonresearcher work remains eligible; invocation-local Run exclusion gives eligible other Runs progress without promising round-robin. Independently Critical `ACCEPT` on 2026-09-01 with findings=0.
- [ ] R2 After R1.5 independent ACCEPT, prove two-or-more Worker contention, cap=1/N, cap-full Run skipping, equal-time Step ordering, lease expiry/late completion, cancel/provider races, join/conflict/recovery on real PostgreSQL. R2 is proof-only and must not add admission production logic.
  - [x] R2 A-J/L proof checkpoint: real PostgreSQL 17.11 aggregate passes; H join,
    I conflict decision/resume, J crash recovery, and L budget/reconcile each received
    independent `ACCEPT` with Critical/High/Medium/Low all zero.
  - [ ] R2-K durable publication outcome-unknown recovery. Current production can verify
    committed or absent immediately, but if verification itself remains unknown it persists
    no publication intent/compensation owner for a later independent process. Any durable
    intent/saga, migration, save, retry, or replay semantic change requires owner `A-DATA`
    authorization before implementation.
R1.5 is independently Critical **ACCEPTED** on 2026-09-01 with findings=0. Focused
unit/boundary tests passed and the real PostgreSQL admission matrix is recorded at
[`docs/evals/r15-postgres-admission-2026-08-31.json`](../../../docs/evals/r15-postgres-admission-2026-08-31.json).
Artifact SHA-256 is `eab095bd68a78972c5b80713d2746a816551eaf1d21bb24ee48016615104d9be`.
R2 is the next stage; no commit or push is claimed here.
- [ ] W1 Implement single-flight/dirty rerun, monotonic event gate, Run-switch abort/discard, event-directed artifact cache, terminal flush, and replay fallback
- [ ] A3 Freeze ingestion result/object/hash/compensation contract and pilot one modality; pilot is not an A5 entry gate
- [ ] A4 Migrate the other eight modalities and composition root
- [ ] A5 Prove candidate Worker import/compile/start/ingest/Research/recovery/version-mismatch without API source/editable dependency/PYTHONPATH
- [ ] A6 Replace legacy Worker target only after A5 and pass deploy/restore regression

A1b/A2-foundation, A2a, R0, and R1 are accepted. A2a/R0 are delivered at `origin/main@8674d4d`; R1 is accepted through review `5a55489` and delivered by PR #22 at `origin/main@a616eea` with `6/6` CI. Worker `349`, gate `64+40`, API `132`, A2a handled `3 -> 8` / UoW `43`, PostgreSQL `7/7` deadlocks `0`, human zero-mutation, causal error preservation, and LangGraph absence pass. R1.5 admission is independently Critical ACCEPTED (findings=0); R2 proof-only is next; W1 SSE/downstream remain blocked; no schema/API/save/replay/permission change is authorized.

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
