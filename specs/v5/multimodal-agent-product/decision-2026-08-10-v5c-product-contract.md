# V5-C Product Contract Decision: Usage-First Research and Versioned Agent I/O

Date: 2026-08-10
Status: approved for implementation
Owner approval: current-turn owner decision

## Decision summary

V5-C is an extensible productization of the existing fixed Research executor. It
must make Research understandable and controllable without turning Citeframe
into a general-purpose agent runtime. The production Agent I/O contract is
upgraded to a strict, versioned contract before the Web product surface is
expanded.

## Product decisions

### C1: Productization scope

Use the existing fixed planner -> approval -> researcher branches -> join ->
verifier -> critic -> conflict decision -> synthesizer -> publisher flow. Add
entry, timeline, branch comprehension, control state, artifact/evidence drill-
down, usage display, and frozen profile display. Do not add dynamic DAG editing,
new step kinds, arbitrary tools, model-selected topology, or hidden long-term
memory.

### C2: First user-visible surface

The first Research product surface includes:

- explicit Research entry separate from Quick Answer;
- server-seq timeline projection with phase, status, branch and safe failure;
- researcher branch grouping in plan order;
- plan, evidence bundle, conflict report when present, and final report drill-down;
- approve, revise, conflict decision, retry, cancel, reconnect and recovery states;
- provider/model profile display;
- usage-only summary: provider calls, tool calls, input/output tokens, branches,
  retries, elapsed time, configured limits, remaining limits and bounded failure
  reasons;
- responsive desktop/mobile controls that never hide the timeline or evidence.

Money, unit prices, estimated cost and per-call billing are not a V5-C user
surface. Verification records remain internal; user-facing claims and evidence
remain traceable through the existing artifact/evidence policy.

### C3: Retrieval top-k

`researchExecution.execution.provider.retrievalTopK` is the frozen maximum number
of evidence results returned by every Researcher evidence search in that
execution. It is not a run-wide evidence total. The Worker must not use a local
literal such as `top_k=8`. A Researcher search uses the frozen value and records
actual result count as usage/telemetry.

### C4: Usage-first budget and pricing

Research creation and execution do not require a pricing-book entry. Pricing is
optional future accounting metadata, never a start gate and never a product
budget gate in this slice.

Hard execution limits are provider calls, tool-call attempts, wall-clock/step
timeouts, maximum parallel researchers, and retry/attempt limits. Input and
output Token limits are **per provider call context limits**, not cumulative run
budgets:

- `maxInputTokens` bounds the assembled prompt/context for one provider call;
- the soft compact threshold runs before the hard bound;
- deterministic typed compaction or batching preserves mandatory IDs,
  evidence handles, provenance and schema fields;
- if mandatory context still cannot fit, fail closed before provider send with
  stable code `research_context_limit_exceeded`;
- `maxOutputTokens` is passed to the provider adapter and bounds one provider
  response; a provider response that is truncated, incomplete, or cannot be
  proven complete fails closed with `research_provider_output_incomplete`, not
  silent success;
- cumulative input/output Tokens are recorded as usage only and never terminate
  a Run by themselves.

The persistence layer must represent unknown pricing as unknown (`null`/explicit
unavailable state), never as a fake zero. Existing historical cost values remain
historical; V5-C user DTOs do not expose money. R803/evaluation cost contracts
remain separate and unchanged.

### C5: Verification scope

Web-only presentation changes require focused Research production-start E2E plus
full API/Worker/Web regression. This slice changes snapshot, context packing,
provider reservation, role-I/O and recovery behavior, so full R800 acceptance is
mandatory, not conditional. The R800 report must include role contract version
lookup, old-version read, new-run version rejection, actual provider output cap,
context overflow-before-send, pricing-unknown start, frozen retrievalTopK and
retry/recovery oracles.

### C8: Production Agent I/O upgrade

Promote the strict role schemas to a single versioned production contract before
shipping the V5-C surface. The first production version freezes the existing
canonical role payloads, with strict `additionalProperties=false`, type/length/
uniqueness checks and cross-role set/provenance checks:

- Planner: summary, known gaps, estimated provider calls and ordered subproblems;
- Researcher: non-empty claims whose evidence handle IDs come from that branch;
- Verifier: exactly the researcher Claim ID set with supported/unsupported status;
- Critic: only IDs from the verified Claim set;
- Synthesizer: only verified/unresolved Claim IDs, never free-form facts.

The model does not create canonical Claim IDs; the server remains the identity
owner. The contract registry is the production extension point inside the fixed
Research topology. Each registered role version freezes, as one immutable unit:

- input/output JSON schema and strict validator;
- prompt template, variable binding and prompt hash;
- runtime adapter and cross-role invariants;
- API persistence/DTO mapping, Web fixtures and snapshot metadata;
- recovery reader and safe failure taxonomy.

The registry must support at least one approved version per role, explicit
version lookup for historical Runs, deterministic capability metadata, and a
single compatibility direction: readers may understand older versions, while a
new Run may bind only an approved current version. Future role fields or bounded
capabilities are added by publishing a new registry version with migration and
fixtures; they are never smuggled through `additionalProperties`, name-based
heuristics, or a new-run fallback. The model remains an untrusted producer and
cannot introduce new roles, tools, permissions, topology, or persistence facts.

New Runs use the approved production version. Historical persisted Runs keep
recovery/readability through the versioned contract registry; no raw provider
output becomes business truth and no compatibility fallback is used for new
Runs.

This is a deliberate production upgrade, not an evaluator-only toggle. It does
not introduce new role kinds, change Citation/NoteSource semantics, rewrite
finished artifacts, or add a provider selector. Because stricter validation and
future versioning change failure behavior, the relevant R800 role-I/O, retry and
recovery scenarios are mandatory.

## Implementation spans

1. `C-G1/C-G3 contract`: update decision/spec/task/lane records; define the
   versioned production role registry, usage-first semantics, context
   packing/compact policy, stable failure codes, legacy reader and migration/save
   impact.
2. `C-API-WORKER`: add `agentResultSchemaVersion`, `contextPolicyVersion` and
   `compactPolicyVersion` to frozen Research snapshots; backfill historical rows
   to an explicit legacy registry entry; make pricing optional; remove
   cumulative Token and pricing start gates; enforce per-call context/output
   limits; implement deterministic typed compaction or batching; and add strict
   role validators and boundary tests.
3. `C-WEB-PRODUCT`: implement timeline/branch/control/artifact/evidence surfaces,
   usage-only DTO presentation and desktop/mobile production-start coverage.
4. `C-ACCEPTANCE`: run API/Worker/Web full suites, focused context/I-O/budget
   tests, production-start desktop/mobile replay, affected R800 scenarios, live
   restore/recovery where applicable, independent Critical review, and durable
   SSoT/workbench writeback.

## Acceptance criteria

- Research starts with a configured provider even when pricing is absent.
- No user-facing Research screen renders money or a billing estimate.
- Provider/tool calls, input/output Tokens, branch/retry counts and limits are
  visible; estimated usage is labeled when the provider did not report actuals.
- A cumulative Token count cannot end a Run; only calls/tools/time/parallelism/
  attempt limits and per-call context/output gates can stop new work.
- No provider request exceeds the frozen per-call context limit, and the actual
  provider request contains the frozen single-call output cap.
- Compact/batch paths preserve Claim IDs, Evidence handle scope, source
  versions, branch ownership and role schema; mandatory overflow fails before
  send with `research_context_limit_exceeded`.
- Truncated or incomplete provider output fails with
  `research_provider_output_incomplete`; the response is never persisted as a
  successful role result.
- Every new Run uses the strict production contract version; malformed, extra,
  duplicate or cross-branch output fails closed.
- Every snapshot has explicit role/context/compact contract versions. Historical
  rows without the new fields are backfilled to a named legacy registry entry;
  old Runs read through that entry, while a new Run is rejected if its approved
  current registry version is unavailable. Finished artifacts are not rewritten.
- Quick Chat, Citation, NoteSource, save/replay, workspace authorization and
  provider fingerprint semantics remain green.
- Desktop/mobile Research flows pass production-start E2E; affected R800
  scenarios and independent Critical review pass.
