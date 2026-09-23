# Research acceptance scenario drivers

## Ownership and invariants

The offline `tools/evaluation` package owns scenario orchestration, raw observation,
and acceptance decisions. Product Worker, API, persistence and scheduling remain
unchanged. The R800 historical schema/version and stored reports retain their
original meaning and provenance. Issue#31 repairs the driver, not past results.

The main scenario approves through the real API, then runs two independent
production `ResearchWorkProcessor` consumers through the existing production
`ResearchDispatcherPool`. Each consumer has its own service, session-factory
identity and worker ID. HTTP polling does not call a processor while that group
is active. Provider/attempt raw timestamps and identity chains are retained;
`parallelFanout` still requires maxActive>=2 and additionally requires real
provider interval overlap and overlapping distinct branch/consumer attempts.

The reclaim scenario captures the original step/attempt/input/execution snapshot,
expires only the test lease as before, and performs real scheduling with a bounded
30-second observation loop. Another step completing cannot satisfy the oracle.
The original attempt must be abandoned; the same step must have a succeeded next
attempt with matching run/workspace/input/snapshot identity. The loop stops on
that evidence or its deadline; cleanup cancellation follows observation.

## Guard semantics and negative controls

Raw run/step/attempt/snapshot, final artifact rows, memberships, provider/tool calls
and ledgers are collected before the separate membership-removal scenario.
Oracles derive scope, unique final publication, creator membership, retry and
parallel limits, call counters/reservations and per-call token limits from those
facts. See the approved [C4 contract](../../specs/v5/multimodal-agent-product/decision-2026-08-10-v5c-product-contract.md).
Cumulative token totals are usage, not run caps. Planning and execution ledgers
are separate; estimated/unknown usage remains recorded and accounting is checked.
Pricing is not a hard execution gate.

Actual Docker negative control uses `run-scenarios --serial-main` in a fresh
isolated project. Its main run must complete but its original concurrency gate
must fail. This is a negative-control test, not a successful scenario run.
Other controls execute the oracles against mutated copies of raw observations:
serial timestamps despite unchanged maxActive; another step's success without
original-step recovery; a live old attempt; snapshot drift; duplicate final rows;
removed creator membership; provider cap/per-call context violations; and ledger
accounting/reservation mismatch. No fake rows are written to the database.
The real membership-removal API refusal and Worker cancellation scenario remains.

Missing/malformed evidence is an error, not an inferred pass. New results contain
`negativeControls` with this explicit mutation scope. Original schemas, fixture
IDs and thresholds are unchanged; historical raw results are never overwritten.

## Evidence integrity repair (PR #32)

The 6a830f45 run35897451227 remains failed. Hubble independently reproduced three
false positives: empty ledger/call collections, a changed snapshot body with an
unchanged stored hash, and unrelated provider intervals paired with local attempts.
The corrected gate requires complete planning/execution ledger coverage, per-step
attempt-number coverage, per-attempt provider/tool counters, unique rows and all
call-to-ledger/attempt/step/snapshot scope links. Missing evidence fails closed.

Reclaim compares the entire frozen snapshot row and ordered frozen asset/prompt
rows. It also reconstructs the existing approval hash through the production
`build_execution_snapshot_hash_payload` and canonical serializer, using the
persisted revision/decision and frozen execution children. Snapshot policy/body
fields must match that revision. Snapshot id, timestamps and cost ceilings are
outside that hash's domain and remain protected by complete before/after equality;
no stored hash is normalized or re-signed.

The evaluation-only Compose override starts `infra/testing/r800_provider_proofs.py`
on the existing API image, mounting it read-only. Production images/entry points
and the historical provider stub are unchanged. This opt-in synthetic-fixture
server keeps the original wire timeline and adds `/__r800__/request-proofs`, storing
exact received JSON bytes, route, ticket epoch/sequence and receipt wall time.
It never records headers. These artifacts contain synthetic prompts/evidence and
must not be used with real user data or production providers.

The oracle recomputes the raw-wire digest separately from the ledger canonical
`nodeKey/messages/maxOutputTokens` digest, using actual Responses `input` and
`max_output_tokens`. It requires one uniquely matching persisted sent call by
canonical digest, node, model, output limit and receipt within its sent/finished
window. Each send is used once; repeated retry hashes require unique time windows.
Every persisted send must be proven. Foreign, missing, duplicate, ambiguous or
wrong-limit proofs reject the concurrency gate. Overlap must belong to two linked
researcher requests whose actual attempts have different consumers/branches in
this run. Original maxActive>=2 remains required.

The bounded researcher delay is1500ms so the existing first503 and one-second retry
can coexist with a different branch's real request. No runtime cap or polling
timeout is relaxed. The separate forced-serial project must complete every other
scenario, retain valid request links and reject concurrency with maxActive=1.
Membership removal expects exactly404/workspace_not_found with no run payload,
matching the product's anti-enumeration contract.

Three named Hubble regression tests execute before Docker scenarios in the same
workflow. Additional controls cover partial row loss, orphan ledgers, missing
snapshot fields/children, body/hash mismatch and wire-proof tampering. Unit inputs
are explicitly synthetic; service artifacts are captured from actual received
requests and persisted rows. Runtime acceptance applies only to its recorded SHA.
