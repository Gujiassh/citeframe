# Research execution and recovery

Research is a versioned bounded workflow with frozen asset scope, prompts, provider bindings, and budgets. PostgreSQL holds durable execution state; object storage holds immutable artifacts. Quick Answer has a separate request/stream path.

## Workflow versions

Roles include Planner, bounded Researcher branches, join, Verifier, Critic, conflict handling, Synthesizer, and publication. Workflow/Agent I/O versions select strict schemas, validators, prompt bindings, and historical readers.

Older runs retain their original approval path. Newer policies can materialize validated plans automatically, perform bounded supplemental retrieval, and report unresolved conflicts. Current conflict investigation is stored separately from original claims; insufficient evidence or exhausted bounds leaves unresolved originals/gaps visible. Models do not create arbitrary graph nodes/tools.

Report edits create independent Markdown editions, preserving original evidence, claims, and verification status. Concurrent saves require displayed original artifact identity/hash and expected version.

## Ownership and dispatch

Web renders persisted Run/Step/Event state and submits authorized controls. API owns HTTP/authentication and migrations. `citeframe_persistence` owns neutral mappings; `citeframe_research_persistence` owns DB-only transitions and UoW/repositories. Worker composes orchestration, persistence, and provider/tool execution.

The production dispatcher claims one eligible Step, creates one leased Attempt, invokes its handler, commits its outcome/newly ready dependents, and returns to the loop. Independent loops support branch overlap. Default handlers do not load LangGraph or carry a cross-step in-memory checkpoint authority.

Handlers validate persisted dependencies, snapshot identity/hash, and artifact/claim/evidence provenance. PostgreSQL owns readiness, joins, event sequences, retry/cancel/reclaim, and budgets.

## Locks, leases, and admission

```text
ResearchRun -> ResearchStep -> ResearchStepAttempt -> provider/tool Call -> ResearchBudgetLedger
```

ID lookups locate parents without making decisions, then lock/refresh and revalidate scope/state/lease/expiry in this order. Claim uses `FOR UPDATE SKIP LOCKED`, stable work ordering, and locked per-run admission. Cap-full candidates roll back without Step/Attempt/event mutation, exclude that Run locally, and scan other eligible work.

Heartbeat extends only the current running Attempt. Expiry abandons the old Attempt; retry creates a new one. Expired Attempts are never revived. Prior successful evidence is reusable only under the same Step/frozen input/execution binding.

## Calls and recovery

Calls have explicit reservation, input binding, outcome, and usage ledger. Deterministic packing and provider output caps enforce per-call limits; incomplete structured output fails. Run limits bound provider/tool calls, time, parallelism, and attempts. Cumulative tokens are usage observations; pricing is optional metadata.

Adaptive turns persist request/result hashes under bounded step/turn keys. Recovery replays committed decisions and successful tools. Unknown call outcomes are reconciled rather than blindly resent. A Workspace model edit may allow a previously authorized call to finish with its captured connection; later reservations fail on drift.

## Publication and authorization

Publication intents coordinate database state and immutable bytes. Reconciliation handles ambiguous commit outcomes and compensation. Final adoption rechecks creator membership inside its commit transaction; revocation prevents final publication.

Conflict journals retain immutable operation identities/hashes. Replay validates originating/current Attempt ownership, Step input/order/snapshot/terminal state. Corrected conclusions remain distinct from originals and are exposed separately in report/API.

## Events and client recovery

Per-Run event sequences are contiguous/unique and allocated with persistence. SSE replays with `Last-Event-ID`. Run switching aborts/discards stale requests; refreshes respect applied sequence. Terminal events flush pending refreshes. Gaps/cursor conflicts trigger authoritative reload. Artifact content is keyed by identity/hash.

Membership validation uses short-lived sessions. Notification is a wakeup optimization; persisted events/replay remain authoritative.

## Verification scope

Deterministic providers validate state, concurrency, leases, authorization, and recovery. Model-quality and target-user evaluation remain pending for Preview. [Evaluation](../development/evaluation.md) describes reproducibility/negative controls.

PostgreSQL locks, multiple consumers, publication, and restart need service-backed tests. UI coverage additionally verifies replay, edits, and citation navigation. See [development commands](../development/README.md).
