# Grok Handoff: V5-F Modality + Agent Completion

## Task

Implement **one** assigned V5-F lane from `implementation-lanes-v5f.md` after the
owner has accepted `decision-2026-08-13-v5f-scope.md` and any required OD freeze
for that lane.

## Mandatory reading

1. `decision-2026-08-13-v5f-scope.md`
2. `v5f-detailed-spec.md`
3. `plan-audit-v5f.md`
4. `implementation-lanes-v5f.md`
5. `verification-matrix-v5f.md`
6. `docs/architecture/modality-extension-contract.md`
7. Relevant prior: `v5b-detailed-spec.md` / `v5c-detailed-spec.md`

## Hard constraints

- Fixed Research DAG only; no agent platform
- No paid R803 claims
- No MIME guessing / fallback chains
- No Citation/NoteSource envelope rewrite
- Stop on unapproved schema/API/save changes → `save-contract-checklist.md`
- Do not enable Audio without ASR capability contract
- Do not execute HTML scripts or Office macros

## Delivery report

Lane, files, contract impact, tests/commands, residuals, next handoff.
