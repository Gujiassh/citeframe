# Tasks: Architecture Hardening

## Package status

- [x] Spec + plan written (2026-08-15)
- [x] Plan audit (see reviews/)
- [x] Owner start authorization for implementation (2026-08-15)
- [x] Phase 1 implementation (N/B/M/R docs + enricher)
- [x] Phase 2 Research package move (`services/research/` + shims)
- [x] Implementation Critical review (controller ACCEPT)
- [ ] Merge to main

## Lane N — Narrative

- [x] N1 Update `docs/architecture/implementation-progress.md` V5-F row + residuals
- [x] N2 Update `docs/architecture/feature-map.md` nine kinds + depth ladder + Research advanced
- [x] N3 Update `docs/ssot/product-design.md` production baseline wording
- [x] N4 Update root `README.md` what-it-does + stage honesty
- [x] N5 Pointer from `specs/v5/multimodal-agent-product/tasks.md` to this package

## Lane B — Service boundaries

- [x] B1 Add visual enricher protocol + production registration
- [x] B2 Wire `prepare_chat` through enricher only
- [x] B3 Keep PDF crop helper; register as enricher implementation
- [x] B4 Tests: auto-crop, soft-skip, import boundary
- [x] B5 Document API/Worker same-version deploy invariant in system-architecture

## Lane M — Modality extensibility

- [x] M1 Write `docs/architecture/modality-onboarding-checklist.md`
- [x] M2 Link from `modality-extension-contract.md`
- [x] M3 Note forbidden shared-layer kind branches

## Lane R — Research architecture

- [x] R1 Freeze notice in `research-workflow-runtime.md`
- [x] R2 Add `docs/architecture/research-module-map.md`
- [x] R3 Quick vs Research one-pager in product-design
- [x] R4 Phase 2 `services/research/` package move + sys.modules shims

## Explicitly not in this package

- [ ] R803 / M404
- [ ] New modalities
- [ ] Dynamic DAG
- [ ] `ai_pdf_*` rename
