# Plan: Office canvas + Video keyframe + PDF crop (PV-4)

Status: **historical plan** — lanes landed on main (PV-4 / keyframe / office viewers; PPTX layout deepened 2026-08-17).  
Date: 2026-08-14 (plan); supersession note 2026-08-17  
Base: `origin/main` (post S0/F-AGENT/ops audit)  
Mode: lane-pair (implementer + Grok audit per lane); controller merges serial if conflicts

## 1. Goal

Close three engineering residuals after V5-F S0:

| Lane | ID | User-visible outcome |
| --- | --- | --- |
| A | **PV-4** | Chat with **PDF region** evidence targets attaches PNG crops into generation (same path as image regions) |
| B | **Video keyframe** | Video ingest extracts keyframes when tooling available; `video_keyframe_set` + strip; no invented frames |
| C | **Office canvas** | DOCX/XLSX/PPTX Evidence viewers show **normalized text/structure + highlight**, not chips only |

Out of scope: R803/M404, Ollama ASR, new Research step kinds, Office macro execution, full PowerPoint graphics canvas.

## 2. Non-goals / hard rules

1. Fail-closed: no fake keyframes, no fake crops, no unsanitized HTML/Office active content.
2. Do not change save/citation locator contracts without explicit note; prefer additive APIs.
3. Do not enable new asset kinds (already S0-enabled).
4. Smallest architecture-aligned change; reuse document/html content patterns and image crop path.
5. English commits; identity `gujishh`.

## 3. Lane A — PV-4 PDF region → generation crop

### Current

- `EvidenceTargetRequest` = **only** `ImageRegionEvidenceTarget`.
- `PRODUCTION_EVIDENCE_TARGET_RESOLVERS` registers only `ImageRegionEvidenceTargetResolver`.
- `prepare_chat` → `resolve_evidence_targets` → `_build_generation_user_message` already attaches `image_payloads` as `input_image`.
- Worker PDF visual already has `_crop_region_png` (PyMuPDF) for caption; API chat path does not reuse it for targets.

### Design

1. Add `PdfRegionEvidenceTarget` schema (mirror image):
   - `kind: "pdf_region"`
   - `assetId`, `processingGeneration`
   - `coordinateSpace: "pdf_crop_box_normalized_top_left_v1"`
   - `pageNumber: int >= 1`
   - `regions: SpatialRegion[]` (1–8)
   - optional `pageGeometry` if needed for validation parity with locators
2. `EvidenceTargetRequest = ImageRegionEvidenceTarget | PdfRegionEvidenceTarget` (discriminator `kind`).
3. New `PdfRegionEvidenceTargetResolver` in `apps/api/src/ai_pdf_api/modalities/pdf_evidence_targets.py`:
   - Load PDF source bytes (storage download by asset source object key / generation).
   - Open with PyMuPDF; crop normalized regions on page → PNG bytes (same coordinate basis as pdf visual).
   - Return `ResolvedEvidenceTarget` with excerpt (OCR text if available from content units optional; else short page label) + `image_payloads`.
   - Fail-closed: missing asset, wrong kind, bad page, empty crop → stable `EvidenceTargetError` codes.
4. Register resolver in `PRODUCTION_EVIDENCE_TARGET_RESOLVERS`.
5. Web: allow sending `pdf_region` evidence targets where image targets are sent today (if UI already has region select for PDF; if only image UI exists, wire API + unit tests first, minimal client if selection already emits regions).

### Tests

- Unit: crop geometry math / resolver with fixture PDF bytes (no live vision).
- Contract: `EvidenceTargetRequest` accepts pdf_region; rejects bad page.
- Chat prepare with pdf_region target includes ≥1 `input_image` in generation messages (mock providers).

### Acceptance

- [ ] Explicit chat `evidenceTargets: [{kind: pdf_region, ...}]` yields generation message with PNG data URLs.
- [ ] Image region path unchanged.
- [ ] No catalog/migration required.

### Residual after lane

- Auto-attach crops for **retrieval-only** pdf_figure hits (no explicit target) is **P1 follow-up**, not blocking PV-4 explicit-target gate.

## 4. Lane B — Video keyframe extraction

### Current

- Tables: `video_normalized_contents.keyframe_count`, `video_frame_locator_details.keyframe_object_key`.
- Ingest sets `keyframe_count=0`, `keyframes=[]`; representation `video_keyframe_set` typed but not populated.
- Viewer can show strip **if** keyframes exist.

### Design

1. **Tooling:** `ffmpeg` + `ffprobe` on PATH (document dependency). If missing at process start or per-job: fail-closed code `video_keyframe_tooling_unavailable` **only when** extraction is required; default policy:
   - **v1 product policy:** attempt extraction; if ffmpeg missing → log + leave `keyframe_count=0` (same as today) **OR** fail job — **choose: soft-skip with explicit metric** so ASR transcript still lands (transcript is primary). Hard-fail only if we later set `requireKeyframes=true`.
   - **Recommended:** soft-skip missing tooling; hard-fail only corrupt video when ffprobe fails after ffmpeg present.
2. Extraction strategy v1 (deterministic):
   - `ffprobe` duration_ms.
   - Sample N frames: `min(12, max(1, duration_s // 10))` at even timestamps (or I-frames via `-skip_frame nokey` if reliable).
   - Store PNGs under object keys: `{workspace}/{asset}/{gen}/keyframes/{index:04d}.png`.
   - Persist metadata in normalized JSON body: `keyframes: [{index, timestampMs, objectKey, contentSha256}]`, set `keyframe_count`.
   - Create `AssetRepresentation` `video_keyframe_set` pointing at a small JSON manifest object (or first key is index file).
3. Optionally create sample `video_frame` locators for strip click → not required for v1 if viewer reads manifest from normalized content.
4. Web video-viewer: render keyframe strip from normalized content / representation API.

### Tests

- Unit with mocked subprocess or tiny fixture mp4 if available in repo.
- Adapter: when ffmpeg mocked to succeed, keyframe_count > 0 and objects listed.
- When ffmpeg missing, transcript path still succeeds (soft-skip).

### Acceptance

- [ ] With ffmpeg present, ingest produces keyframe objects + count > 0 for short fixture.
- [ ] Without ffmpeg, ASR path still works; no invented frames.
- [ ] Viewer shows strip when count > 0.

## 5. Lane C — Office canvas viewers

### Current

- **Was (2026-08-14 baseline):** ingest + typed locators + chip-only `office-viewer.tsx`.
- **Now (main):** DOCX block list, XLSX text, PPTX `pptx-layout-v1` canvas + `/pptx-media`; content API for office kinds. See `S0_HANDOFF.md`.
- **Was:** Content API document/html only; no docx/xlsx/pptx content endpoint.
- DOCX has `docx_normalized_contents` + `docx_blocks` in DB.
- XLSX/PPTX: normalized text in object storage + locator details; no block tables like docx.

### Design

1. **API content**
   - Extend `GET .../representations/{id}/content` (or sibling routes) for:
     - `docx`: same shape as document blocks (reuse/adapt `DocumentNormalizedContentResponse` or `DocxNormalizedContentResponse`).
     - `xlsx` / `pptx`: return `{ normalizedText, contentSha256, processingGeneration, format }` from stored normalized object + representation row; optional structured cells/slides if parse metadata already in normalized text.
2. **Web**
   - ~~Replace chip-only DOCX viewer~~ **done:** document-viewer-like list + `docx_anchor` highlight.
   - XLSX: monospaced / table-ish text view + highlight line containing `startCell:endCell` or displayedText.
   - PPTX: slide sections if normalized text has markers; else full text + highlight displayedText.
3. Keep visual nesting ≤2 surfaces; no card-in-card.

### Tests

- API: docx content returns blocks; wrong kind 404.
- Web: unit tests for highlight helpers (like html-content tests).
- Registry still routes office kinds to new viewers.

### Acceptance

- [ ] Open DOCX citation shows body text with block highlight.
- [ ] XLSX/PPTX show normalized text + locator emphasis.
- [ ] Source file download unchanged.

## 6. Parallelism & ownership

| Lane | Worktree | Primary files | Avoid |
| --- | --- | --- | --- |
| A PV-4 | `citeframe-v5f-pv4-20260814` | `pdf_evidence_targets.py`, `schemas/chat.py`, `services/evidence_targets.py`, tests | worker pdf_ingestion (reuse logic via shared helper only if clean) |
| B Keyframe | `citeframe-v5f-keyframe-20260814` | `video_ingestion.py`, video content API if needed, `video-viewer.tsx`, tests | office/chat evidence targets |
| C Office | `citeframe-v5f-office-canvas-20260814` | `routers/assets.py`, schemas, `office-viewer.tsx`, `docx` content helpers, tests | video/chat targets |

Shared extract: if PV-4 needs crop helper, put pure function in `ai_pdf_api/modalities/pdf_region_crop.py` (API-side) without importing worker.

Merge order: **A → C → B** (A no migration; C API routes; B may add worker deps note). Or A∥C then B.

## 7. Verification matrix

| Gate | Command / check |
| --- | --- |
| PV-4 unit | `pytest … test_pdf_evidence_targets.py` |
| Keyframe unit | `pytest … test_video_ingestion.py` (+ ffmpeg or mock) |
| Office API | `pytest … test_office_content_api.py` |
| Web | `pnpm test` + eslint on touched viewers |
| Regression | focused modality registry + chat contract |

## 8. Docs / tasks updates

- Flip `PV-4` checkbox when A lands.
- Note keyframe tooling dependency in `local-env-profiles.md` or worker README.
- Update `S0_HANDOFF` residual section / verification matrix closeout.

## 9. Risks

| Risk | Mitigation |
| --- | --- |
| PyMuPDF in API process for PV-4 | Already used in worker; API may already depend via shared package — verify `apps/api` deps; else crop in worker-only path is wrong for sync chat. Prefer API pymupdf if already transitive. |
| ffmpeg not in CI | Soft-skip + mock tests; optional CI apt install ffmpeg |
| Large PDF crops in generation | Cap regions (max 8) and max edge px (e.g. 1280) |
| Office files huge | Content API streams/limits text size like document path |

## 10. Open decisions (defaults if no reply)

| OD | Default |
| --- | --- |
| Keyframe missing ffmpeg | **Soft-skip** (transcript still succeeds) |
| PV-4 retrieval auto-crop | **Out of v1** (explicit targets only) |
| PPTX graphics | **Text-first** canvas only |
