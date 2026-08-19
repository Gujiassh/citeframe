# Spec: Post-V5 Optimization

## 1. Objective

Raise Citeframe's structural and delivery quality without reopening completed V5
scope or disguising engineering coverage as model quality or user value.

The target is not a microservice rewrite or uniform feature depth. The target is:

- enforceable dependency direction;
- smaller, single-responsibility modules with unchanged behavior;
- evidence-led depth decisions across the nine enabled modalities;
- a protected `main` branch whose green checks are actual merge gates.

## 2. Verified Baseline

### 2.1 Architecture boundary

- `apps/worker/src` contains **41** Python source modules. **28 affected modules** contain
  **96** direct import statements referencing `ai_pdf_api`; **12** Worker modules directly
  import SQLAlchemy.
- API and Worker are separate processes but remain one versioned product with shared
  source, ORM, database, and transaction boundaries.
- API owns schema/migration and mutation-logic definitions. Research Worker `_ApiPort`
  currently creates sessions and commits/rolls back. Ingestion shares a Session/ORM
  boundary with modality adapters.

### 2.2 Maintainability

Current line-count baseline:

| File | Lines | Risk |
| --- | ---: | --- |
| `modalities/evidence.py` | 1587 | contracts, codecs, registry, and operations converge |
| `routers/assets.py` | 1526 | lifecycle, representation, and media endpoints converge |
| `test_r803_campaign_v5.py` | 2461 | campaign, integrity, retry, and scoring cases converge |
| `v5b_document_restore_acceptance.py` | 2006 | backup, restore, verify, and CLI converge |
| `services/multimodal_execution.py` | 1027 | schemas, provenance, validation, and report rendering converge |
| `test_multimodal_execution.py` | 1036 | baseline, tamper, provenance, and report tests converge |

Line count is a signal, not the acceptance criterion. A split is useful only when each
resulting module has one responsibility and the before/after behavior oracle is equal.

### 2.3 Product completeness

- Enabled kinds: `pdf`, `image`, `document`, `html`, `docx`, `xlsx`, `pptx`, `audio`, `video`.
- PDF/Image are `Deep`; the remaining seven are `Evidence-complete`.
- Model quality remains `not_evaluable` without an authorized R803 successor campaign.
- User value remains `not_evaluable` without an approved M404 protocol and qualified users.
- Known depth candidates include Office fidelity, Audio diarization/time-range UX, and
  richer Video shot/keyframe analysis with cost/latency limits.

### 2.4 Delivery governance

- GitHub `main` branch protection: absent.
- GitHub repository rulesets: empty.
- CI currently exposes six passing jobs: `api`, `worker-fast`, `worker-acceptance`,
  `worker-evaluation`, `web`, and `web-e2e`.
- Because the branch is unprotected, those jobs are evidence but not mandatory merge gates.

## 3. Goals

| ID | Goal |
| --- | --- |
| A | Remove Worker dependence on API internals through an approved ownership/transport target and measurable migration gates |
| M | Split the highest-risk mixed-responsibility files without changing runtime, HTTP, persistence, or evaluation semantics |
| P | Make modality depth investment depend on user tasks, quality evidence, latency, and cost rather than format count |
| G | Make reviewed PRs and the six CI jobs enforceable on `main` |

## 4. Non-goals

- No immediate microservice split, event-bus migration, database split, or package rename.
- No change to Asset/Representation/ContentUnit/EvidenceLocator, Citation, NoteSource,
  Research, API, SSE, save, replay, or permission semantics.
- No attempt to make all nine modalities equally deep in one release.
- No paid R803 run, M404 study, or public-release claim without separate authorization.
- No GitHub branch/ruleset mutation without explicit owner authorization.
- No implementation work is authorized by accepting this plan.

## 5. Owner Decision Gates

| Gate | Decision required before implementation |
| --- | --- |
| `G0` | Approve exact `main` protection/ruleset policy and permitted owner bypass |
| `A0` | Separately decide schema/migration owner, mutation-logic owner, session/commit process owner, and transport |
| `A-DATA` | Approve any proposed persistence, payload, API, save, or replay contract change before code |
| `P0` | Approve priority user segment/tasks and modality scoring weights |
| `P-R803` | Approve provider/profile, budget ceiling, threshold, and new artifact directory |
| `P-M404` | Approve protocol, qualified users, task set, success criteria, and privacy boundary |

## 6. Architecture Recommendation

For the current `internal_preview` stage, default to a **versioned pure contracts boundary
plus same-database adapter pilot** before introducing internal HTTP. This removes modality
and Research runtime dependence on API internals while preserving the existing PostgreSQL
job path and avoiding a new network failure domain.

This recommendation does not pre-decide session ownership. `A0` must name it explicitly.
Choose API-process HTTP/RPC only when independent API/Worker deployment, scaling, or
security isolation is a real requirement worth the operational cost.

## 7. Success Measures

- No new Worker `ai_pdf_api` or SQLAlchemy import is added after baseline guards land.
- Final boundary target: Worker runtime imports `ai_pdf_api` = 0, or a small owner-approved
  allowlist with an expiry condition; modality/domain code imports SQLAlchemy = 0.
- Non-semantic splits preserve OpenAPI, JSON/payload, canonical report, error-code,
  permission, and frozen-artifact oracles.
- Every enabled modality has an explicit task/depth/quality/cost row; only evidence-backed
  depth work is promoted.
- A deliberately failing PR cannot merge to `main`; a fully green reviewed PR can.
