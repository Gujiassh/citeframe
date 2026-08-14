# Verification Matrix: Architecture Hardening

## Evidence classes

| Class | Claimable |
| --- | --- |
| Docs consistency | yes |
| Unit/integration | yes |
| Contract stability | yes (no locator meaning change) |
| Model quality | no |
| User value | no |

## Gates

| Gate | Meaning | Pass criteria |
| --- | --- | --- |
| AH-G0 | Decision + plan audit | decision present; plan audit ACCEPT |
| AH-G-N | Narrative | progress/feature-map/product-design/README match main; depth ladder present; no “V5-F not started” |
| AH-G-B | Boundaries | enricher port; chat without pdf_evidence_targets import; auto-crop behavior preserved; soft-skip preserved |
| AH-G-M | Modality checklist | checklist merged; modality-extension-contract links it; no new kind branches in chat/retrieval core |
| AH-G-R | Research freeze | freeze text + module map; no topology code change |
| AH-G-FULL | CI | api (+ worker if touched) green; web if docs-only N/A |

## Commands

```bash
# after Lane B
uv run --project apps/api pytest \
  apps/api/tests/test_chat_service.py \
  apps/api/tests/test_pdf_evidence_targets.py \
  apps/api/tests/test_chat_import_boundaries.py \  # name may vary
  -q --tb=short

# docs only
rg -n "待主人批准后实现|production baseline is PDF and PNG" docs/ README.md || true
# expect no stale V5-F-not-started in progress file
```

## Oracle

1. Chat generation with retrieved `pdf_region` still attaches PNG when loader works.
2. Chat still completes when PDF load fails (soft-skip).
3. `grep -n pdf_evidence_targets apps/api/src/ai_pdf_api/services/chat.py` → empty.
4. Research graph node list unchanged in `research_executor_engine.py`.
5. README mentions internal_preview and does not claim R803.

## Residual allowed after ACCEPT

- Optional Research package directory move (Phase 2).
- Optional UI preview badge.
- Package rename `ai_pdf_*`.
- Full live multimodal E2E (ops).
- R803/M404.
