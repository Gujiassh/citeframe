# Grok 4.5 Handoff: V5-C Usage-First Research Productization

Date: 2026-08-10
Repository: `/home/cc/code/citeframe`
Base: `main@4f2129c`
Model: `sourcesdata/grok-4.5` with xhigh reasoning

## Mission

Implement the approved V5-C contract in
`decision-2026-08-10-v5c-product-contract.md`. This is a production Research
productization and contract-hardening slice, not a general Agent platform.

## Non-negotiable semantics

- Research starts when provider/profile/security/configuration is valid even if
  no pricing-book row exists.
- Do not show money, unit prices, estimated cost or billing in the Research UI.
- Show provider/model and usage: provider calls, tool calls, input/output tokens,
  branches, retries, elapsed time, limits, remaining limits and safe failure
  reasons. Mark measured versus estimated usage.
- Input/output Token limits are per provider-call context/output limits. They are
  not cumulative Run budgets. Cumulative usage is telemetry only.
- Implement a versioned strict production Agent I/O registry. New Runs use the
  strict approved version. The registry is the fixed-topology extension point:
  each role version binds schema, prompt/hash, validator, runtime adapter,
  cross-role invariants, API/Web mapping and historical recovery reader as one
  immutable unit. Future fields/capabilities require a new registry version and
  fixtures, never permissive fields, heuristics or a new-run fallback path.
- `execution.provider.retrievalTopK` is the frozen maximum for every Researcher
  evidence search. Remove local `top_k=8` behavior.
- Compact/batch must preserve evidence handles, Claim IDs, source snapshots,
  branch scope, order and schema invariants. If mandatory content cannot fit,
  fail closed before the provider request.
- Do not alter Quick Chat, Citation, NoteSource, Asset, or finished artifact
  semantics except for explicitly additive Research contract fields.

## Ownership and expected files

API/Worker contract and budget/context work may touch the real Research service,
models, schemas, migrations, runtime ports and tests. Web work owns only Research
components, Research product helpers, i18n keys and the dedicated V5-C E2E spec.
Do not spread `if research` branches into Document/PDF/Image evidence owners.

Expected contract areas to inspect first:

- `apps/api/src/ai_pdf_api/models/research_run.py`
- `apps/api/src/ai_pdf_api/models/research_execution.py`
- `apps/api/src/ai_pdf_api/schemas/research.py`
- `apps/api/src/ai_pdf_api/services/research_worker_policy.py`
- `apps/api/src/ai_pdf_api/services/research_worker_provider.py`
- `apps/api/src/ai_pdf_api/services/research_worker_plan.py`
- `apps/worker/src/ai_pdf_worker/research_runtime_agents.py`
- `apps/worker/src/ai_pdf_worker/research_agent_schemas.py`
- `apps/worker/src/ai_pdf_worker/research_runtime_ports.py`
- `apps/web/src/components/research-run-panel.tsx`
- `apps/web/src/lib/research/`

## Required implementation slices

1. Establish one production registry entry per role version and persist
   `agentResultSchemaVersion`, `contextPolicyVersion` and `compactPolicyVersion`
   on the Research plan/execution snapshot. Backfill historical rows to an
   explicit legacy registry entry; new Runs must reject unavailable current
   versions. Validate strict role schemas and cross-role set, branch and
   evidence provenance. Preserve server-generated Claim IDs.
2. Make cost/pricing optional. Unknown cost must be represented as unknown, not
   zero. Remove price presence and cumulative input/output Token checks from the
   start/reserve gates. Keep calls/tools/time/parallelism/attempt limits.
3. Add per-call context policy: prompt assembly, a frozen soft compact
   threshold, typed deterministic compaction/batching, hard overflow failure
   before send (`research_context_limit_exceeded`), and a provider-enforced
   single-response output cap. Truncation/incomplete output must fail with
   `research_provider_output_incomplete`. Freeze mandatory-field order and
   policy versions; record compact decisions and usage safely without persisting
   raw provider output or hidden reasoning.
4. Make all Researcher evidence searches use the frozen execution `retrievalTopK`.
5. Add usage-only API/Web DTO mapping and Research UI timeline, branch grouping,
   controls, evidence/artifact drill-down and responsive production-start E2E.

## Acceptance evidence required

- API focused contract/context/budget tests and full API suite.
- Worker focused role-I/O/context/retrieval tests and full Worker suite.
- Web focused usage/timeline/control tests, TypeScript/lint/build and full Web
  unit suite.
- Production-start desktop and mobile Research E2E with SSE reconnect/replay,
  usage-only assertions and no cost text.
- A new isolated full R800 acceptance covering role-I/O, snapshot version lookup,
  legacy read/new-run rejection, retry/recovery, context overflow-before-send,
  actual output cap, incomplete-output failure, pricing-unknown start and frozen
  retrievalTopK. This is mandatory because persistence/recovery/provider
  reservation semantics changed.
- `python3 -m compileall`, `git diff --check`, no secrets/raw provider output in
  logs or DTOs, and an independent Critical review.

## Delivery rules

- Do not commit or push.
- Do not modify the existing B008 artifacts.
- Do not claim model quality/user value from scripted-provider engineering tests.
- Report changed files, tests, unresolved risks and exact acceptance evidence.
