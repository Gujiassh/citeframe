# Grok 4.5 Handoff: V5-D Cross-Layer Integration

## Task

Implement one assigned V5-D lane from
[`v5d-detailed-spec.md`](v5d-detailed-spec.md) and
[`implementation-lanes-v5d.md`](implementation-lanes-v5d.md). The goal is to make
existing PDF, Image, Markdown Document, Quick Chat, and Research capabilities work
together as an internal-preview engineering release.

## Mandatory reading order

1. `specs/v5/multimodal-agent-product/decision-2026-08-11-v5d-scope.md`
2. `specs/v5/multimodal-agent-product/v5d-detailed-spec.md`
3. `specs/v5/multimodal-agent-product/implementation-lanes-v5d.md`
4. `specs/v5/multimodal-agent-product/verification-matrix-v5d.md`
5. `specs/v5/multimodal-agent-product/save-contract-checklist.md`
6. `docs/architecture/modality-extension-contract.md`
7. `docs/architecture/research-workflow-runtime.md`
8. Existing V5-B/V5-C acceptance records relevant to the assigned files.

## Before editing

Report the following first:

- assigned lane and exact file ownership;
- source SHA and branch/worktree path;
- `git status --short` classification of pre-existing changes;
- expected user-visible behavior and non-goals;
- tests and runtime evidence you will produce.

The canonical worktree currently contains uncommitted V5-C changes. Do not reset,
checkout, clean, stash, or overwrite unrelated changes. Do not create a second
worktree for the same repository unless the main controller explicitly assigns it.

## Hard constraints

- Preserve Asset/Evidence/Citation/NoteSource/Chat/Research save and replay semantics.
- Preserve frozen Research execution provider/model/limits/scope/retrievalTopK truth.
- Do not add a provider/model selector, fallback chain, compatibility layer, silent
  coercion, dynamic Agent, new modality, new locator family, or new registry version.
- Do not change database/API/OpenAPI/SSE/permission/cost meaning without stopping and
  filling `save-contract-checklist.md` for main-controller approval.
- Do not use MIME, field presence, array order, or first available value to infer kind.
- Do not claim R803 model quality or M404 user value from engineering tests.
- Do not commit or push unless the user explicitly requests it in the active turn.

## Lane assignment

Use exactly one of these scopes; do not mix them:

- `D-API-WORKER`: mixed scope/retrieval, Citation/NoteSource, delete/retry,
  Research restart/recovery, API/Worker tests.
- `D-WEB`: desktop/mobile Workspace, Quick Chat, Research, Viewer, Playwright and
  Web fixtures/tests.
- `D-OPS`: deployment profile, restart/restore harness, backup/object/row checksum,
  readiness and zero-residue evidence.
- `D-DOCS`: runbook, diagnostics, SSoT/spec links and acceptance record templates.

`D-ACCEPT` is main-controller/reviewer work and is not an implementation lane.

## Stop and report

Stop before changing code if you encounter:

- any database/API/save/replay/permission/cost/locator contract change;
- a need for provider selector, fallback, dynamic step/tool, or registry version;
- a file overlap with another lane or unexplained pre-existing dirty change;
- missing real fixture, authentication, PostgreSQL/MinIO, or production-start state;
- a test failure that may be a baseline regression without old/new comparison;
- conflict between this handoff and current code that existing contracts cannot resolve.

Your response must include the proposed impact and the smallest evidence needed; do
not implement a speculative side route.

## Required delivery report

1. Lane, owner, source SHA, worktree and changed files.
2. Goal alignment and explicit non-goals.
3. Contract/save/replay impact: `none`, or a stop report with decision ID.
4. Implementation summary and known residual risks.
5. Commands, exit codes, test counts, screenshots/logs/DOM/artifact paths.
6. Review findings and rework status.
7. Exact next handoff or acceptance blocker.

## Minimum lane checks

- D-API-WORKER: focused API/Worker tests, compileall, mixed scope and recovery oracles.
- D-WEB: Web unit, lint, tsc, build, production-start Playwright at `1440x1000`
  and `390x844`, screenshots and DOM/state evidence.
- D-OPS: `bash -n` for scripts, static harness tests, live PostgreSQL/MinIO
  acceptance where required, backup/restore checksums and zero-residue cleanup.
- D-DOCS: relative-link check, `git diff --check`, command/path audit and updated
  workbench/spec references.

A lane is not accepted because its local tests pass. Main controller must inspect the
diff, compare it with the assigned invariant, run the D matrix, and route review fixes
back to the original lane.
