# Plan audit: Architecture Hardening

Date: 2026-08-15  
Auditor: independent review (same session as authoring; adversarial checklist applied)  
Plan under review: `specs/v5/architecture-hardening/`

## Verdict: **ACCEPT**

Proceed with Phase 1 after owner start. Do **not** start Phase 2 package moves by default.

## Checklist

| Gate | Result | Notes |
| --- | --- | --- |
| Goal alignment | **pass** | Four review gaps only; no modality/R803 creep |
| Smallest safe change | **pass** | Docs + thin enricher; no ORM split |
| Contract safety | **pass** | Explicit no locator/save semantic change |
| Parallel ownership | **pass** | N/R docs parallel; B owns chat; M docs |
| Fail-closed | **pass** | Soft-skip enrichers preserved |
| Test plan | **pass** | Behavior + import guard |
| Residuals explicit | **pass** | Phase 2 move, rename, quality gates out |
| Research freeze honesty | **pass** | Freeze is product decision, not fake refactor |
| Narrative first | **pass** | Correct sequencing to stop doc-driven wrong work |
| Over-abstraction risk | **pass with note** | Single protocol is enough; reject multi-layer “enrichment framework” |

## Findings

### F1 — Non-blocking: enricher placement

Prefer `ai_pdf_api/modalities/visual_enrichment.py` (next to targets) **or** `services/visual_evidence.py`.  
Either is fine; do not put protocol inside `chat.py`.

### F2 — Non-blocking: import test fragility

AST import test is better than runtime import side effects. Accept string-grep on `chat.py` as sufficient P1.

### F3 — Non-blocking: Research map accuracy

Module map must be generated from current file list (~28 API research_*.py) so it does not invent layers.

### F4 — Watch: dual PR vs one PR

Docs-only N+R can merge alone if code B delays. Do not leave narrative half-updated relative to enricher behavior (behavior already on main; narrative is the lag).

## What would make this REWORK

- Proposing microservices or removing shared ORM for ingestion in Phase 1.
- Changing Research graph “while we are here”.
- Bundling R803.
- Silent change to citation/save contracts for “cleaner” enricher persistence.

## Decision defaults confirmed

| Topic | Default |
| --- | --- |
| Phase 1 | N + B + M + R docs/freeze |
| Phase 2 research package move | off unless owner asks |
| Package rename | out of scope |
| Owner start | required before code PR |

## Residual risks after plan ACCEPT

1. Implementers expand enricher into a plugin system — reject in code review.
2. Docs updated but progress file still lists old alembic head numbers — verify against reality when editing.
3. Import guard not added — boundary regresses on next PDF special case.

## Sign-off

**ACCEPT** for plan quality and scope. Implementation Critical review still required when code lands.
