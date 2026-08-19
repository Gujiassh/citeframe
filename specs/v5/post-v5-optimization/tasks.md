# Tasks: Post-V5 Optimization

Status: **all implementation blocked pending explicit owner authorization**.

Checkboxes describe scope and progress only. They do not authorize code, contract,
repository-setting, paid-provider, or user-study changes.

## Plan Closure

- [x] Verify architecture/import/line-count/modality/governance baseline
- [x] Write spec and sequenced plan
- [x] Independent plan audit ACCEPT (2026-08-19)
- [ ] Owner chooses which decision gate to open first

## G: Delivery Governance

- [ ] G0 Approve exact `main` ruleset, available reviewer count, and emergency bypass
- [ ] G1 Require PR + resolved conversations + six CI checks; block force-push/delete
- [ ] G2 Add concurrency cancellation and missing timeouts
- [ ] G3 Upgrade Node 20-era action versions and prove job parity

## A: API / Worker Boundary

- [ ] A0 Approve schema, mutation, session/commit, and transport owners separately
- [ ] A1 Add pure Python DTO/Protocol contracts package
- [ ] A2 Migrate Research port/transaction boundary with old/new oracle
- [ ] A3 Freeze ingestion result/object/hash/compensation contract and pilot one modality
- [ ] A4 Migrate all remaining modalities and composition root
- [ ] A5 Prove API-source-free candidate Worker build
- [ ] A6 Replace legacy target and remove old dependencies last

## M: Maintainability

- [ ] M0 Add reproducible size/dependency baseline and ownership map
- [ ] M1 Split `modalities/evidence.py` without semantic change
- [ ] M2 Split `routers/assets.py` without HTTP/auth/streaming change
- [ ] M3 Split M402 execution service with byte-identical report
- [ ] M4 Split R803 campaign tests without changing test/frozen evidence meaning
- [ ] M5 Split restore acceptance script without changing CLI/report/cleanup
- [ ] M6 Split M402 tests without reducing adversarial coverage

## P: Product Completeness

- [ ] P0 Approve users/tasks/weights and publish nine-modality capability/value matrix
- [ ] P1a Authorize and run a new R803 campaign; preserve frozen v1
- [ ] P1b Approve and run M404 protocol with qualified users
- [ ] P1c Hold separate engineering/model-quality/user-value release review
- [ ] P2 Select Office depth only if matrix evidence ranks it first
- [ ] P3 Select Audio depth only if matrix evidence ranks it first
- [ ] P4 Select Video depth only if matrix evidence ranks it first

## Contract Stop Rules

- [ ] Any persistence/API/save/replay/permission meaning change stops for `A-DATA` approval
- [ ] Any GitHub repository setting mutation stops for `G0` approval
- [ ] Any provider spend stops for `P-R803` approval
- [ ] Any user research stops for `P-M404` approval
- [ ] Any depth slice lacking a real fixture and measurable user task remains unstarted
