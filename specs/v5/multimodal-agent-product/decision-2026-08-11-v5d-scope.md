# V5-D Scope Decision: Cross-Layer Integration and Engineering Stability

Date: 2026-08-11
Status: implementation-ready, contract-preserving baseline

## Decision

V5-D is the integration and reliability slice after the accepted V5-A, V5-B
Markdown document, and V5-C Research productization slices. It combines the
already enabled PDF, Image, and Markdown `document` capabilities with Quick
Chat and Research into one stable Workspace experience.

The first V5-D implementation must preserve existing Asset, Evidence, Citation,
NoteSource, Chat, Research ledger, provider snapshot, and backup/restore
semantics. This decision does not approve a new database schema, a new public
API contract, a provider selector, a new modality, or a new Agent runtime.

## In Scope

- Mixed PDF/Image/Markdown asset scope and retrieval from the existing registry.
- Citation, NoteSource, Evidence Viewer, Quick Chat, and Research paths over a
  mixed Workspace.
- Desktop and mobile primary flows using production-start Web.
- API/Worker/Web restart, lease recovery, delete retry, permission, backup and
  restore evidence for the existing contracts.
- Unified user-facing provider/model, usage, status, and stable failure display
  using the V5-A/V5-C DTOs already present.
- Deployment profile, runbook, diagnostics, and durable acceptance artifacts.

## Explicit Non-Goals

- HTML, Office, Audio, Video, ASR, or new locator families.
- User or Workspace provider selection.
- Dynamic DAGs, arbitrary plugins, recursive Agents, arbitrary network/Shell/ORM
  tools, or long-term model memory.
- Replacing Asset/Evidence/Citation/NoteSource/Research storage contracts.
- Money or per-call billing UI; unknown pricing remains unknown/null.
- R803 model-quality claims or M404 user-value claims.

## Required Invariants

1. `assetScope` remains the authority for Chat and Research asset selection; the
   effective scope is frozen according to the existing request/run contract.
2. Research execution snapshots remain the only runtime truth for provider,
   model, limits, retrieval configuration, permissions, and budget controls.
3. Current Settings profiles are never used as a fallback for a frozen Run or
   revision snapshot.
4. Citation and NoteSource keep immutable locator/source-version snapshots;
   reprocess, reindex, delete, and restore do not rewrite historical meaning.
5. Unknown or unavailable modality, locator, provider, or profile fails closed;
   no MIME/field/order/first-available guessing is allowed.
6. Runtime-only Web state does not enter persistent business models.
7. Any proposed API, database, save, replay, permission, cost, or locator change
   stops implementation and follows `save-contract-checklist.md`.

## Entry Gate

Before an implementation lane starts, the main controller records:

- canonical source SHA and worktree status;
- disposition of the existing V5-C dirty worktree;
- F1 executable registry mapping evidence;
- F5 historical-row bytes/hash evidence, or an explicit reason it is deferred;
- lane ownership and file boundaries;
- the exact acceptance profile and artifact directory.

F1/F5 closure is a precondition before enabling another registry version. V5-D
must not introduce another registry version merely to make integration easier.

## Exit Gate

V5-D is accepted only when the D verification matrix is complete, all required
existing suites remain green, desktop/mobile production-start flows pass, live
PostgreSQL/MinIO restore evidence is recorded where applicable, the independent
Critical review is `ACCEPT`, and all residual risks are written to the acceptance
record. The result is an internal-preview engineering release, not a model
quality or user-value release.
