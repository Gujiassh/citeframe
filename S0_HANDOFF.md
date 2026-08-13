# S0 handoff status (V5-F)

**Status: IMPLEMENTED** on branch `work/v5f-s0-enable-20260813` / main after merge.

Production enable for office + HTML + audio + video is a single deploy:

| Piece | Location |
| --- | --- |
| Registry | `build_production_registry()` includes docx/xlsx/pptx/html/audio/video |
| Catalog | alembic `m7a8b9c0d1e2_s0_enable_v5f_modality_catalog.py` |
| Worker | `HtmlIngestionAdapter` + office/audio/video adapters registered |
| Web upload | `production-upload.ts` + `production-registry.ts` accept lists |
| Office viewers | chip/metadata viewers in `office-viewer.tsx` (text canvas follow-up) |

## Ops notes

- Audio/video ingest still fail closed without OpenAI ASR secret.
- Image caption still fail closed without vision secret (lazy at ingest).
- Office viewers are locator chips only; richer canvas is F-AGENT / polish residual.
- Research executor locator union expansion remains F-AGENT.

Historical per-lane enable recipes below are superseded by the unified S0 migration.

---

(Previous lane-specific handoff text archived in git history before this revision.)
