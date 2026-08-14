# Decision: Architecture Hardening (boundaries, modality purity, Research load, narrative)

Date: 2026-08-15  
Status: **approved and implemented** (owner start 2026-08-15; full Phase 1+2)  
Author: architecture review closeout  
Depends on: V5-F engineering closeout on main

## 1. Intent

Harden four dimensions without expanding product scope:

1. **Service boundaries** — make ownership and dependency rules enforceable, not only documented.
2. **Modality extensibility** — keep shared Chat/retrieval/viewer free of kind-specific business branches.
3. **Research architecture** — freeze topology; reduce cognitive load; do not grow roles/tools.
4. **Product narrative** — make docs and UI-facing stage language match what is actually shipped.

## 2. Non-goals (explicit)

- No new modality kinds.
- No dynamic Research DAG / plugin platform.
- No R803 paid campaign / M404 user study (unless separate owner authorization).
- No rename of `ai_pdf_api` / `AI_PDF_*` in this package (tracked as optional later; high churn).
- No microservices split of Worker vs API.
- No change to Citation/NoteSource envelope field meanings.

## 3. Decisions

### D-B1 — Deployment unit remains modular monolith

API and Worker stay one deployable product version. Shared ORM is **allowed for ingestion adapters** only under rules:

- Single Alembic authority in `apps/api`.
- Worker and API must ship the **same git SHA / image tag** in deploy docs and CI.
- Research execution continues to own state via **API service ports** (existing design); new Research persistence must not invent a second ORM owner.

### D-B2 — Chat must not import modality-specific crop helpers

`prepare_chat` may attach generation images only through a **modality-agnostic** port:

```text
VisualEvidenceEnricher (protocol)
  enrich(db, retrieved, *, loader) -> tuple[bytes, ...]
```

Production registration may include PDF retrieval-auto-crop and (later) other kinds. Chat imports the registry, not `pdf_evidence_targets` directly.

### D-B3 — Modality special cases live in modules

Allowed in modality packages / codecs / adapters / resolvers / web renderers.  
Forbidden in: `services/chat.py` core orchestration, `services/retrieval.py` fusion core, Citation/NoteSource envelope serializers (beyond codec dispatch).

### D-R1 — Research topology freeze

Until a new OD reopens it:

- Graph nodes and role set stay: Planner, Researcher, Verifier, Critic, Synthesizer, publisher + existing HITL gates.
- No new tool kinds without a written brief + budget impact.
- Prefer documentation, tests, and file-map over new abstraction layers.

### D-R2 — Research package map (docs-first; optional move)

Document a canonical module map (ledger / executor / evidence tools / agent I/O / views).  
Physical package moves are **optional Phase 2** and must be pure renames with import shims if done at all.

### D-N1 — Narrative SSOT refresh is mandatory in this package

Update at least:

- `docs/architecture/implementation-progress.md` (V5-F done)
- `docs/architecture/feature-map.md` (nine kinds + depth ladder)
- `docs/ssot/product-design.md` § baseline (remove PDF/Image-only production wording where false)
- `README.md` “What it does” modality list + internal_preview badge language

### D-N2 — Depth ladder is product truth

Public/internal narrative must classify modalities:

| Tier | Kinds (current) | Meaning |
| --- | --- | --- |
| Deep | pdf, image | Full visual region + production viewer depth |
| Evidence-complete | document, html, docx, xlsx, pptx, audio, video | Upload→index→retrieve→cite→viewer; viewer may be text/structure-first |
| Quality | — | not_evaluable without R803 |
| User value | — | not_evaluable without M404 |

## 4. Success criteria

- Chat has zero direct imports from `pdf_evidence_targets` / kind-named crop modules.
- New modality checklist exists and is referenced from modality-extension-contract.
- Research freeze recorded in research-workflow-runtime + this decision.
- Narrative docs match main; no “V5-F not started” or “production only PDF/Image”.
- CI green; no locator meaning changes; unit tests for enricher registry.

## 5. Owner action

Implementation starts only after owner says start (same rule as prior V5 slices).  
Spec and plan audit may land on main as docs-only without implementation.
