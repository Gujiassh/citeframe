# Research module map

Date: 2026-08-15

Canonical ownership for the fixed Research product path. Evaluation/R803 scripts are **not** the product path.

Current delivery state: A2a/R0 are delivered by PR #21 at `origin/main@8674d4d` (`6/6` CI). R1 branch starts at `8674d4d`; R1 chain `f4a1d1d -> 473213d` is implementer-complete; `473213d` is local/not pushed with no upstream or remote branch after initial Critical `REWORK (High=0, Medium=4, Low=0)`. Follow-up pending; no `ACCEPT`. R2/W1/admission remain blocked.

## API package (`apps/api/src/ai_pdf_api/services/research/`)

Import path: `ai_pdf_api.services.research.*`. Compatibility shims remain at `ai_pdf_api.services.research_*` (sys.modules aliases).

## API modules

| File | Responsibility (one line) |
| --- | --- |
| `research.py` | High-level research service entry (if present) |
| `research_agent_io_registry.py` | Versioned agent I/O contracts |
| `research_artifacts.py` | Artifact rows/bytes linkage |
| `research_constants.py` | Shared constants |
| `research_context_policy.py` | Context packing / limits |
| `research_decisions.py` | Conflict and control decisions |
| `research_events.py` | SSE/event sequencing |
| `research_evidence_provenance.py` | Claim/evidence provenance |
| `research_idempotency.py` | Idempotency keys |
| `research_plan_approval.py` | Plan HITL approval |
| `research_prompt_provenance.py` | Prompt/template provenance |
| `research_recovery.py` | Recovery helpers |
| `research_runs.py` | Run lifecycle create/list/detail |
| `research_versions_service.py` | Workflow/prompt versions |
| `research_views.py` | Read models / DTO assembly for Web |
| `research_worker.py` | Facade re-exports for worker-facing ports |
| `research_worker_completion.py` | Compatibility/composition facade for neutral completion commands |
| `research_worker_evidence.py` | Frozen evidence search/load/restore |
| `research_worker_failure.py` | Step failure recording |
| `research_worker_lease.py` | Compatibility facade for neutral lease commands |
| `research_worker_membership.py` | Research subsystem support module — see source module docstring/imports |
| `research_worker_plan.py` | Compatibility/composition facade for neutral plan publication |
| `research_worker_policy.py` | Research subsystem support module — see source module docstring/imports |
| `research_worker_provider.py` | Provider call reserve/send/reconcile |
| `research_worker_publication.py` | Compatibility/composition facade for neutral publication/conflict commands |
| `research_worker_state.py` | Compatibility facade for neutral state/reclaim/control commands |
| `research_worker_tools.py` | Tool call ledger begin/complete |
| `research_worker_types.py` | Research subsystem support module — see source module docstring/imports |

## Worker (`apps/worker/src/ai_pdf_worker/`)

| File | Responsibility |
| --- | --- |
| `research_agent_schemas.py` | Agent result schemas |
| `research_executor.py` | Executor entry wiring |
| `research_executor_contracts.py` | Executor typed contracts |
| `research_executor_engine.py` | Current fixed LangGraph `StateGraph(ResearchState)` / `BoundedResearchExecutor` engine; R1 target removes runtime step execution |
| `research_executor_tools.py` | Executor-side tool adapters |
| `research_runtime.py` | Runtime loop entry |
| `research_runtime_agents.py` | Generation-backed role agents |
| `research_runtime_core.py` | Shared runtime types/helpers |
| `research_runtime_ports.py` | SQL/API ledger and tool ports |
| `research_runtime_processor.py` | Claimed work processor |
| `research_persistence_service.py` | Default Worker composition over neutral Research UoW/repository/commands |

## Not product Research path

## Neutral Research persistence (`packages/research-persistence/`)

`citeframe_research_persistence` is the repair worktree owner for DB-only plan, lease, completion, publication, retry, cancellation, state/reclaim, provider, and tool transitions plus repositories/UoW. API modules retain compatibility and external-adapter composition. This map describes the implementer-complete repair and remains subject to the new Critical re-audit.

- `r803_*`, `r800_*` evaluation/acceptance packages: quality campaigns and engineering gates only.

## Freeze

Package staging is A1 contracts (independently accepted on 2026-08-20) ->
A1b/A2-foundation persistence mappings (independently accepted on 2026-08-21 by the
follow-up Critical review: High=0, Medium=0, Low=0) -> A2a Research persistence behavior.
A2a and R0 are delivered at `origin/main@8674d4d`. R1 chain `f4a1d1d -> 473213d` is implementer-complete but remains `REWORK` pending follow-up. R2/W1/admission/downstream remain blocked behind named gates,
and no schema/API/save/replay/permission changes are authorized. No behavior-free
`citeframe_research_persistence` scaffold is permitted before A2a; see topology freeze in
[`research-workflow-runtime.md`](research-workflow-runtime.md).

## Phase 2 package move (2026-08-15)

- Canonical modules live under `services/research/`.
- `27` implementation modules + `__init__.py` facade.
- Old `services/research_*.py` paths are **aliases** (same module object) for monkeypatch/import compatibility.
