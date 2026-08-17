# S0 handoff status (V5-F)

**Status: IMPLEMENTED** on main (unified S0 enable + subsequent depth slices).

Production enable for office + HTML + audio + video is a single deploy baseline:

| Piece | Location |
| --- | --- |
| Registry | `build_production_registry()` includes docx/xlsx/pptx/html/audio/video |
| Catalog | alembic `m7a8b9c0d1e2_s0_enable_v5f_modality_catalog.py` |
| Worker | `HtmlIngestionAdapter` + office/audio/video adapters registered |
| Web upload | `production-upload.ts` + `production-registry.ts` accept lists |
| Office viewers | `office-viewer.tsx`: DOCX block list; XLSX normalized text; **PPTX `pptx-layout-v1` canvas** (EMU geometry + embedded pictures via `/pptx-media`) with legacy text-line fallback |

## Depth notes (post-S0)

- **PPTX layout** (2026-08-17, PR #16/#17): parse stores layout JSON; content API returns slides/geometry; viewer canvas highlights shapes; media restricted to `ppt/media/`. Not full PowerPoint fidelity (no masters/animation/SmartArt/z-order polish).
- **DOCX/XLSX**: structured/normalized text viewers; not WYSIWYG Office.
- Audio/video ingest still fail closed without OpenAI ASR secret.
- Image caption still fail closed without vision secret (lazy at ingest).
- Research evidence locator union for S0 kinds landed with F-AGENT; further multi-kind seed suites remain ops residual.

Historical per-lane enable recipes below are superseded by the unified S0 migration.

---

(Previous lane-specific handoff text archived in git history before this revision.)
