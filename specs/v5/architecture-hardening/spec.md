# Spec: Architecture Hardening

## 1. Problem statement

After V5-F, Citeframe’s **kernel** (Asset/Evidence) is strong, but four frictions remain:

1. **Boundaries** are partly cultural (docs) rather than structural (imports/ports).
2. **Modality purity** is mostly held, but Chat already special-cases PDF retrieval crops.
3. **Research** is a correct fixed DAG that has grown into a second cognitive product.
4. **Narrative** still describes older baselines, which will mis-steer the next work.

## 2. Goals

| ID | Goal |
| --- | --- |
| G1 | Enforce service and module ownership with tests and import rules where cheap |
| G2 | Make modality extension the only place for kind-specific behavior |
| G3 | Freeze Research growth; improve map and onboarding without new roles |
| G4 | Align SSoT/README/feature-map with main and the depth ladder |

## 3. Requirements

### 3.1 Service boundaries (Lane B)

| ID | Requirement | Priority |
| --- | --- | --- |
| B-REQ-1 | Document deploy invariant: API+Worker same version; single Alembic head | P0 |
| B-REQ-2 | Introduce `VisualEvidenceEnricher` (or equivalent name) protocol used by `prepare_chat` | P0 |
| B-REQ-3 | Move `collect_retrieval_pdf_crop_payloads` behind production enricher registration | P0 |
| B-REQ-4 | Keep explicit `evidenceTargets` resolution on existing resolver registry (already OK) | P0 |
| B-REQ-5 | Add a lightweight import/architecture test: `services/chat.py` must not import `modalities.pdf_evidence_targets` | P1 |
| B-REQ-6 | Research state mutations remain on API services; Worker research path uses ports only (document + spot-check, no rewrite) | P1 |
| B-REQ-7 | Ingestion Worker may use shared ORM; list allowed modules in `docs/ssot/system-architecture.md` | P1 |

**Out of scope:** splitting databases, gRPC, event buses, renaming Python packages.

### 3.2 Modality extensibility (Lane M)

| ID | Requirement | Priority |
| --- | --- | --- |
| M-REQ-1 | Publish “New modality checklist” (registry, catalog migration, codec, adapter, retrieval signature, viewer, tests, S0 enable) | P0 |
| M-REQ-2 | Link checklist from `modality-extension-contract.md` | P0 |
| M-REQ-3 | Forbid new kind branches in `retrieval.py` fusion core and Chat prompt assembly beyond enricher/registry dispatch | P0 |
| M-REQ-4 | Web: production-registry remains single place for renderer binding (already); document invariant | P1 |
| M-REQ-5 | Optional: shared “generation attachment cap” config (max images) used by enrichers, not hardcoded only in PDF helper | P2 |

### 3.3 Research architecture (Lane R)

| ID | Requirement | Priority |
| --- | --- | --- |
| R-REQ-1 | Write freeze notice into `research-workflow-runtime.md` (topology + non-goals) | P0 |
| R-REQ-2 | Add `docs/architecture/research-module-map.md` listing API `research_*.py` and worker `research_*.py` responsibilities | P0 |
| R-REQ-3 | No new graph nodes/roles/tools in this package | P0 |
| R-REQ-4 | Optional Phase 2: pure file regroup under `services/research/` package with re-export shims — only if owner wants; not required for ACCEPT | P2 |
| R-REQ-5 | Capture “when to use Quick vs Research” in product-design or feature-map (one screen of prose) | P1 |

### 3.4 Product narrative (Lane N)

| ID | Requirement | Priority |
| --- | --- | --- |
| N-REQ-1 | `implementation-progress.md`: mark V5-F engineering complete; list residuals honestly | P0 |
| N-REQ-2 | `feature-map.md`: nine kinds + depth ladder + Research as advanced path | P0 |
| N-REQ-3 | `product-design.md`: production baseline includes S0 kinds; PDF/Image are deep tier not sole kinds | P0 |
| N-REQ-4 | `README.md`: multimodal list + internal_preview + quality not claimed | P0 |
| N-REQ-5 | Specs index `specs/v5/multimodal-agent-product/tasks.md` note pointer to this package | P1 |
| N-REQ-6 | Do not claim R803/M404; keep stage `internal_preview` | P0 |

## 4. Data / contract constraints

- **No** change to locator kind meanings, Citation/NoteSource columns, or save semantics.
- **No** change to Research Agent I/O registry versions unless a bugfix requires it (then separate OD).
- Visual enricher only adds generation `input_image` payloads; does not alter citation rows.

## 5. Acceptance (package-level)

Package ACCEPT when:

1. Plan audit ACCEPT (this repo docs).
2. All P0 requirements done in code and/or docs as specified.
3. Focused tests: enricher + chat import guard + existing chat/pdf crop tests green.
4. Narrative docs updated; spot-check no contradictory “V5-F not started”.
5. Critical review of the implementation slice ACCEPT or ACCEPT with residuals (no contract break).

## 6. Risks

| Risk | Mitigation |
| --- | --- |
| Enricher refactor breaks multimodal chat tests | Keep behavior identical; reuse crop helper; expand FakeGenerationProvider coverage |
| Doc-only merge ignored | Treat N as P0; block “done” without progress/feature-map |
| Research map bitrots | Map generated from file list + one-line ownership; update when research_* files change |
| Scope creep into package rename | Explicit non-goal |

## 7. Open questions (need owner only if implementing Phase 2)

| ID | Question | Default |
| --- | --- | --- |
| OQ-1 | Physical `services/research/` package move? | **No** in Phase 1 |
| OQ-2 | Rename `ai_pdf_*` packages? | **Out of package** |
| OQ-3 | UI badge “internal preview” in app chrome? | Optional P2; docs first |
