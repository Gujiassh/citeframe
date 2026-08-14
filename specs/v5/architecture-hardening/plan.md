# Plan: Architecture Hardening

## 1. Strategy

Smallest safe change. Prefer docs + thin ports over rewrites.  
Sequence: **N (docs) → B (chat enricher) → M (checklist + contract link) → R (freeze + module map)**.

Narrative first so subsequent code reviews use the same product language.

## 2. Lanes

| Lane | Name | Primary files | Does not touch |
| --- | --- | --- | --- |
| N | Narrative SSOT | `docs/architecture/implementation-progress.md`, `feature-map.md`, `docs/ssot/product-design.md`, `README.md`, pointer in v5 tasks | Runtime code |
| B | Boundaries / enricher | `services/chat.py`, new `services/visual_evidence.py` or `modalities/visual_enrichment.py`, `pdf_evidence_targets.py` (export only), tests | Research ledger, migrations |
| M | Modality purity | `docs/architecture/modality-extension-contract.md` (+ checklist section or sibling `modality-onboarding-checklist.md`), optional import test | New kinds |
| R | Research freeze | `docs/architecture/research-workflow-runtime.md`, new `research-module-map.md` | Graph nodes, agent schemas |

Parallelism: N ∥ R docs; B after N recommended; M docs can parallel B; B code is serial with chat tests.

## 3. Lane B design (normative)

### 3.1 Protocol

```python
class VisualEvidenceEnricher(Protocol):
    def enrich(
        self,
        db: Session,
        retrieved: Sequence[RetrievedContent],
        *,
        image_bytes_loader: ImageBytesLoader,
        max_images: int = 4,
    ) -> tuple[bytes, ...]:
        ...
```

### 3.2 Production composition

```text
PRODUCTION_VISUAL_ENRICHERS = (
    RetrievalPdfRegionCropEnricher(),  # wraps collect_retrieval_pdf_crop_payloads
)
# prepare_chat:
payloads = tuple chain of enricher.enrich(...) capped globally
```

### 3.3 Soft-skip

Enricher failures must not fail chat (preserve current PDF soft-skip). Log flat lines `visual_enrich skip reason=...`.

### 3.4 Tests

- Existing `test_retrieval_pdf_region_auto_crops_into_generation` still passes.
- New test: chat module does not import pdf_evidence_targets (AST or `importlib` + `__file__` dependency check).
- Soft-skip loader errors still empty extra images.

## 4. Lane M design

Add `docs/architecture/modality-onboarding-checklist.md`:

1. ModalityModule + MIME + byte inspector  
2. Catalog rows + contract_version  
3. Representations / content units / locator detail + codec  
4. Worker adapter + cleanup  
5. Retrieval channel type signatures  
6. Web production-registry + renderer  
7. SSE/DTO union if new locator kind  
8. Upload accept + tests  
9. S0 enable migration (catalog enabled)  
10. Restore/delete evidence  

Assert: shared Chat/retrieval only gain registry hooks, not kind switches.

## 5. Lane R design

### Freeze block (insert near topology)

```text
FREEZE (2026-08-15): Topology and role set are closed for product work.
New nodes/roles/tools require a new open decision. Prefer fixing
reliability and evidence coverage over graph expansion.
```

### Module map sections

- Versions / plan approval / runs / views (API)
- Worker ports: lease, provider, tools, completion, publication, evidence
- Executor engine (worker)
- Explicit: Evaluation/R803 scripts are **not** the product Research path

## 6. Lane N design

Concrete edits (content rules):

- Progress: V5-F row = engineering complete on main; residual = R803/M404 + live E2E ops.
- Feature-map: tree includes html/docx/xlsx/pptx/audio/video; mark Research advanced.
- Product-design: baseline paragraph updated; JTBD unchanged.
- README: “What it does” lists nine kinds with honesty about depth; stage line.

## 7. Verification

See `verification-matrix.md`. Minimum local:

```bash
uv run --project apps/api pytest apps/api/tests/test_chat_service.py apps/api/tests/test_pdf_evidence_targets.py -q
# plus new import guard test when B lands
pnpm --dir apps/web test  # if web copy changes only, optional
git diff --check
```

## 8. Delivery

- Prefer one PR for N+R docs, second PR for B+M code/docs, or single PR if small.
- English commits; identity gujishh for GitHub.
- After merge: memory note + close tasks checkboxes.

## 9. Effort estimate

| Lane | Effort |
| --- | --- |
| N | 0.5–1 day |
| R docs | 0.5 day |
| M checklist | 0.5 day |
| B enricher | 1–1.5 days + tests |
| Total Phase 1 | ~3 days |
| R package move Phase 2 | 2–4 days (optional, high conflict risk) |
