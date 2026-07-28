# R800 Critical Acceptance Plan

## Status

Acceptance plan approved under the Owner's autonomous V4 authorization. Results remain open until runtime evidence exists.

## Evidence layers

1. Engineering contract: deterministic fixtures, persistence, concurrency, recovery, permissions, and provenance.
2. Real-model quality: paired Quick/Research runs with identical comparison keys and an explicitly configured non-scripted provider.
3. User value: M404 task evidence from real target users. Until available, this gate is `not_evaluable`, never pass or fail by proxy.

## Critical security review

| Oracle | Required evidence |
| --- | --- |
| Cross-Workspace isolation | API and Worker corruption tests for Run, Step, Decision, Artifact, Claim, Evidence handle, provider/tool call, and Evaluation IDs |
| Creator/owner permissions | plan/conflict/retry/cancel/read matrix tests plus reader browser evidence |
| Prompt injection/tool boundary | malicious Evidence/provider outputs cannot name arbitrary tools, widen Asset scope, load sibling handles, set provider URL/model/header, or bypass Verifier |
| Provider/data boundary | frozen approved profile only; no secrets/auth/object keys in payload, logs, trace, Event, Artifact, or Evaluation DTO |
| Budget/cost | reserve before send, reconcile actual/estimated, retry shares the same budget, unknown outcome remains accounted, hard limits stop new calls |
| Lease/restart | expired lease becomes abandoned; stale token cannot publish; restart does not duplicate provider/tool calls, Events, Claims, or Artifact |
| Artifact integrity | bytes/size/hash, typed locator/source versions, claim marker set, section/status matrix, and Run/Workspace chain validated atomically |
| Web rendering | Markdown remains sanitized; unknown locator/event/artifact fields fail closed; creator controls never render for reader |

## Runtime scenarios

- approved Plan creates the frozen DAG and bounded Researcher fan-out; timestamps prove real overlap without exceeding the limit;
- an unsupported claim is withheld from final facts/conclusions;
- a conflict publishes an immutable `conflict_report`, waits, accepts only the creator's bound Decision, then resumes from committed state;
- one transient branch failure retries only that logical branch;
- client SSE disconnect/reconnect replays exact persisted sequence and de-duplicates delivery;
- API restart preserves read/SSE behavior; Worker restart abandons/reclaims leases and resumes without duplicated terminal facts;
- cancel racing with publish yields either committed completion before cancel CAS or committed cancellation without a final Artifact, never both;
- PostgreSQL/MinIO backup and restore preserve Event seq, Artifact bytes/hash, Claim/Evidence provenance, and Evaluation import hashes.

## Paired quality report

For every pair, assert the R700 comparison keys before scoring. Report per-case and aggregate claim support, Evidence recall/precision, locator accuracy, conflict detection, refusal correctness, latency, provider calls, tokens, cost, retries, recovery, and intervention time.

A real-model report may be produced only when both Quick and Research use the same fixture scope and approved provider/model profile. Any mismatch is `not_evaluable`. One successful run is not a release threshold; the report records the observed sample count and residual uncertainty.

## Deliverables

- `docs/evals/r800-critical-review.md`
- `docs/evals/artifacts/r800-v1/` with hashes, logs, state snapshots, paired reports, and desktop/mobile screenshots
- architecture/runbook updates and a 5-minute demo script
- exact verification commands and environment facts without secrets
