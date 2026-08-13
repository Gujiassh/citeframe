# V5-F Implementation Lanes

## Lane ownership rules

- One modality implementation lane owns that modality’s adapter, locator, fixtures, tests.
- Shared kernel changes (ingestion seam, retrieval fusion, OpenAPI union assembly) require a **shared owner** and serial review.
- `F-AGENT` may not invent new step kinds.
- No second worktree for the same repo without controller approval.
- No commit/push unless owner asks in the active turn (workspace rule).

## Lanes

| Lane | Owns | Must not touch |
|---|---|---|
| F-DOCS | this package, open-decisions updates, progress/tasks | production code |
| F-HTML | html module, sanitizer, fixtures, tests, web renderer | audio/video/office |
| F-DOCX | docx adapter/locator/viewer/tests | other office kinds except shared OOXML utils if extracted with owner |
| F-XLSX | xlsx slice | docx/pptx business rules |
| F-PPTX | pptx slice | docx/xlsx business rules |
| F-ASR | capability registry ASR contract, errors, readiness | enabling audio registry row alone |
| F-AUDIO | audio ingest/locator/viewer/tests | video |
| F-VIDEO | video ingest/locator/viewer/tests | audio-only registry hacks |
| F-AGENT | Research multi-modal evidence UX + tests + scripted E2E | modality parsers |
| F-MIX | mixed all-kinds seed/restore/compose acceptance | business contract changes |
| F-ACCEPT | full matrix + Critical | implementation shortcuts |

## Execution order

**Authoritative parallel plan:** [`parallel-execution-plan-v5f.md`](parallel-execution-plan-v5f.md)

- Wave 1: HTML ∥ DOCX ∥ XLSX ∥ PPTX ∥ ASR ∥ AGENT (document-class)
- Shared kernel (S0) is serial
- Audio/Video start only after ASR is green, then in parallel
- MIX + ACCEPT last

## Per-lane minimum delivery

### Modality lane

- modality brief freeze paragraph in `v5f-detailed-spec.md` or sibling brief file
- migration + catalog
- adapter + codecs
- API/Web union registration
- unit/integration tests
- fixture files
- restore/mixed hooks or explicit handoff to F-MIX

### F-AGENT lane

- Research evidence multi-kind fixtures
- Web timeline/evidence grouping + temporal/document chips
- production-start Research with mixed scope (scripted provider)
- recovery/retry oracles including multi-kind citations

### F-MIX lane

- seed script for all enabled kinds
- empty-target compose backup/restore
- zero residue
- report.json engineering gates only
