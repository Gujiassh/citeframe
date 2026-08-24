# Tasks: Post-V5 Optimization

Status: **Design re-audit ACCEPT (High=0, Medium=0, Low=0); A1 independently accepted
on 2026-08-20; A1b/A2-foundation independently accepted on 2026-08-21 by the follow-up
Critical review (`High=0`, `Medium=0`, `Low=0`); A2a initial snapshot `20d411e` received independent Critical `REWORK` (`High=1`, `Medium=5`, `Low=1`). The bounded rework on `work/research-boundary-runtime-20260824` is implementer-complete but remains uncommitted and unpushed; a new independent Critical re-audit against an immutable repair snapshot is pending. No A2a `ACCEPT` is claimed. R0/R1/R2/W1 and downstream remain blocked**.

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
- [x] R/W Freeze PostgreSQL-only orchestration, one-claimed-attempt dispatcher target, per-Run admission, and independent SSE target
- [x] R0 Freeze Run-first lock normalization target; implementation remains conditional and separate from A2a/R1

### Production implementation, A2a rework awaiting a new Critical gate; later slices blocked

- [x] A1 Add only `citeframe-backend-contracts` / `citeframe_contracts` pure DTO/Protocol package; API/Worker add only its local path and stage-specific export/smoke; no persistence or Research package scaffold (independently accepted 2026-08-20)
- [x] A1b / A2-foundation Add `citeframe-backend-persistence` / `citeframe_persistence` on top of A1 as unique Base/metadata and all-model mapping distribution; extend manifests, Docker COPY/PYTHONPATH, and smoke with zero DDL drift (implementer-complete 2026-08-20; independently accepted 2026-08-21 by follow-up Critical review: High=0, Medium=0, Low=0)
- [x] A2a initial snapshot `20d411e` implemented the third package but failed independent Critical review (`REWORK`, High=1, Medium=5, Low=1)
- [x] A2a bounded core/supply-chain rework on `work/research-boundary-runtime-20260824` restores compatibility, completes neutral ownership, adds executable differential/deploy gates, and preserves current multi-step `process_one` and mixed locks (implementer-complete; uncommitted/unpushed)
- [ ] New independent A2a Critical re-audit against one immutable repair snapshot, including clean-image runtime proof
- [ ] R0 Normalize all mutation lock acquisition to `Run -> Step -> Attempt -> Call -> Ledger`; prove real PostgreSQL lock/deadlock evidence without save/API semantic change
- [ ] R1 Change `process_one` into bounded concurrent dispatcher loops; each loop creates one `ResearchStepAttempt` lease and executes exactly that newly claimed Attempt with its step-kind handler; prove production-shaped two-loop overlap; keep separate from A2a
- [ ] R2 Prove two-or-more Worker contention, cap=1/N, cap-full Run skipping/fairness/no-starvation, equal-time Step ordering, lease expiry/late completion, cancel/provider races, join/conflict/recovery on real PostgreSQL
- [ ] W1 Implement single-flight/dirty rerun, monotonic event gate, Run-switch abort/discard, event-directed artifact cache, terminal flush, and replay fallback
- [ ] A3 Freeze ingestion result/object/hash/compensation contract and pilot one modality; pilot is not an A5 entry gate
- [ ] A4 Migrate the other eight modalities and composition root
- [ ] A5 Prove candidate Worker import/compile/start/ingest/Research/recovery/version-mismatch without API source/editable dependency/PYTHONPATH
- [ ] A6 Replace legacy Worker target only after A5 and pass deploy/restore regression

A1b/A2-foundation was independently accepted on 2026-08-21 (follow-up Critical review ACCEPT; High=0, Medium=0, Low=0). The initial A2a snapshot was rejected; the repair is implementer-complete but not accepted. R0/R1/R2/W1 and downstream remain blocked. No schema/API/save/replay/permission changes are authorized. A2a preserves the current multi-step `process_one` LangGraph
behavior and current mixed lock behavior. After a new A2a Critical `ACCEPT`, R0 is the
next implementation slice and only changes lock
acquisition order; R1 is the later slice that removes LangGraph runtime step execution and
introduces one-claimed-attempt dispatch. A5 cannot be claimed until A3/A4 cover all nine
modalities and Research runtime, composition, and recovery gates pass.

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
