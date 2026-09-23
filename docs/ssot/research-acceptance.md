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
