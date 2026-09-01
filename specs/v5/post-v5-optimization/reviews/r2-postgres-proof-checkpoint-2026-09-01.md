# R2 PostgreSQL Multi-Worker Proof Checkpoint

Date: 2026-09-01
Baseline: `6793027c3fa27590d69dc48f3cfb4e02d89392e8`

## Verdict

This is an accepted checkpoint for the currently implemented proof-only scenarios, not a
final R2 acceptance:

```text
R2 A-J/L checkpoint: ACCEPT
Critical=0
High=0
Medium=0
Low=0

R2 overall: REWORK / waiting for A-DATA
```

The runner reports the missing K coverage explicitly through
`coverage.blockedScenarios` and `coverage.r2Complete=false`. Its `passed=true` means every
implemented scenario in that invocation passed; it must not be read as final R2 completion
or as model-quality/user-value evidence.

## Accepted proof scope

- distinct OS processes and PostgreSQL backends;
- same-Step exclusion, processor exclusion, cap=1/N and other-Run progress;
- equal-time Step ordering;
- natural lease expiry, reclaim, replacement, and late-completion fencing;
- cancellation/provider/tool reconciliation races;
- join readiness and downstream queue ordering;
- persisted conflict decision, idempotent replay, synthesis resume, and provenance;
- Windows hard-crash recovery with protected secret IPC and exact DACL evidence;
- Provider/Tool/BudgetLedger exhaustion and recovery with snapshot/request bindings.

H, I, J, and L each received an independent final review with
Critical/High/Medium/Low all zero. The aggregate real PostgreSQL 17.11 run covers 12 named
scenarios (`identity_probe`, A-J excluding K, and L), uses temporary databases, and records
successful forced cleanup. Production source directories remain unchanged.

## Automated gates

- R2 focused contracts: `181 passed`;
- Ruff: passed for all runner/scenario/worker/test files;
- `git diff --check`: passed;
- production diff under Research persistence, Worker runtime, and API source: empty;
- aggregate real PostgreSQL 17.11 implemented-scenario run: passed;
- aggregate checkpoint artifact SHA-256:
  `f6f6b25161907279a189d568012b181a437e702c72b95154b59cd6f4e2004c0a`;
- canonical payload-without-hash-field SHA-256:
  `3da784a705ddedb57cd6f795e86246b5f5f38380ed20ad15024bb5ed2071bd65`;
- database URL/password, lease token, SID, and unredacted lease-token hash scrub: passed;
- temporary database `DROP ... WITH (FORCE)`: attempted and succeeded.

## R2-K stop condition

Current final publication can converge when immediate verification proves `committed` or
`absent`. If the object upload completed, the database commit raised, and verification is
itself unavailable/unknown, production persists no durable publication intent or later
reconcile responsibility. A proof-only scenario cannot manufacture that missing
cross-process recovery contract.

The minimum production repair is an internal durable publication intent/saga (or an
equivalent outbox-owned state machine), plus later Worker reconciliation and compensation.
Because that changes schema and persistence/save/retry semantics, implementation is blocked
until the owner explicitly approves `A-DATA`. Public API behavior should remain unchanged
unless separately authorized.

## Delivery meaning

This checkpoint may be committed and pushed as reviewed proof infrastructure. It does not:

- check the R2 task as complete;
- publish the final canonical A-L artifact;
- unblock W1 or downstream slices;
- authorize schema, API, save/replay, permission, provider-spend, or repository-setting
  changes.
