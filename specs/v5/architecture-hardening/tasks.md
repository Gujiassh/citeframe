# Tasks: Architecture Hardening

## Package status

- [x] Spec + plan written (2026-08-15)
- [x] Plan audit (see reviews/)
- [ ] Owner start authorization for implementation
- [ ] Phase 1 implementation
- [ ] Implementation Critical review
- [ ] Merge to main

## Lane N — Narrative

- [ ] N1 Update `docs/architecture/implementation-progress.md` V5-F row + residuals
- [ ] N2 Update `docs/architecture/feature-map.md` nine kinds + depth ladder + Research advanced
- [ ] N3 Update `docs/ssot/product-design.md` production baseline wording
- [ ] N4 Update root `README.md` what-it-does + stage honesty
- [ ] N5 Pointer from `specs/v5/multimodal-agent-product/tasks.md` to this package

## Lane B — Service boundaries

- [ ] B1 Add visual enricher protocol + production registration
- [ ] B2 Wire `prepare_chat` through enricher only
- [ ] B3 Keep PDF crop helper; register as enricher implementation
- [ ] B4 Tests: auto-crop, soft-skip, import boundary
- [ ] B5 Document API/Worker same-version deploy invariant in system-architecture or deploy README

## Lane M — Modality extensibility

- [ ] M1 Write `docs/architecture/modality-onboarding-checklist.md`
- [ ] M2 Link from `modality-extension-contract.md`
- [ ] M3 Note forbidden shared-layer kind branches

## Lane R — Research architecture

- [ ] R1 Freeze notice in `research-workflow-runtime.md`
- [ ] R2 Add `docs/architecture/research-module-map.md`
- [ ] R3 Quick vs Research one-pager in feature-map or product-design
- [ ] R4 (optional Phase 2) `services/research/` package move — **not** required

## Explicitly not in this package

- [ ] R803 / M404
- [ ] New modalities
- [ ] Dynamic DAG
- [ ] `ai_pdf_*` rename
