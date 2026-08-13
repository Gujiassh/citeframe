# V5-F Detailed Spec: Complete Modalities + Complete Multi-Agent Collaboration

## Status

`proposed-spec` (2026-08-13). Depends on owner approval of
[`decision-2026-08-13-v5f-scope.md`](decision-2026-08-13-v5f-scope.md).

## 0. Reading order

1. `docs/architecture/modality-extension-contract.md`
2. `v5b-detailed-spec.md` (Markdown document pattern to clone)
3. `v5c-detailed-spec.md` + `decision-2026-08-10-v5c-product-contract.md`
4. This file
5. `implementation-lanes-v5f.md`
6. `verification-matrix-v5f.md`
7. `plan-audit-v5f.md`

## 1. Goals

### 1.1 Modality completion

For each remaining modality, deliver the full vertical loop:

```text
upload-session → MIME/byte fail-closed → Asset
  → ingest job → immutable Representations + typed ContentUnits + typed locators
  → retrieval channels → Quick Chat / Research EvidenceCandidate
  → Citation / NoteSource clone → Web renderer
  → retry / reprocess / delete / empty-target restore
```

### 1.2 Agent collaboration completion

Make the **existing** fixed Research DAG multi-modal complete:

```text
planner → plan approval → researcher* (parallel)
  → join → verifier → critic → conflict?
  → synthesizer → publisher
```

Users must be able to:

- start Research over a mixed multi-modal scope
- see evidence from every enabled kind with correct typed locators
- approve/retry/cancel/recover without losing finished artifact identity
- open evidence in the correct Viewer (page/region/time/frame/document anchor)

## 2. Non-goals

- General agent platform / dynamic DAG / free tools
- Provider selector UI
- Paid R803 quality pass or M404 user-value pass
- Auto-enabling a modality because MIME is recognized without registry/catalog
- Treating HTML as “Markdown with tags”
- Treating Video as “Audio with a picture”

## 3. Shared kernel requirements (all modalities)

### 3.1 Registry module checklist

Every modality module must provide:

| Piece | Requirement |
|---|---|
| `assetKind` | exact literal in code + `asset_types` catalog |
| `supportedMimeTypes` | closed list; no `*/*` |
| `byteInspector` | header-based; mismatch fail-closed at upload |
| `ingestionAdapter` | Worker adapter; no orchestrator business branching |
| `representationKinds` | immutable derived objects |
| `contentUnitKinds` | retrieval/analysis units |
| `locatorCodecs` | typed detail tables + DTO union variants |
| `retrievalChannels` | registered signatures only |
| `cleanupPolicy` | delete/retry object keys |
| fixtures | at least one golden file under `docs/fixtures/` |
| tests | unit + mixed + restore gates per matrix |

### 3.2 Forbidden heuristics

- infer kind from file extension alone
- “first available field” as semantics
- MIME substring matching to pick renderer
- silent empty retrieval on embedding mismatch (must keep V5-A fail-closed)
- writing runtime UI state into durable models

### 3.3 Citation / NoteSource

Public envelope unchanged. Only extend locator discriminator:

```text
pdf_page | pdf_region | image_region | document_anchor
  | html_anchor | docx_anchor | xlsx_cell | pptx_shape
  | audio_range | video_range | video_frame
```

(Exact literals freeze in each modality brief before coding.)

## 4. Per-modality contracts

### 4.1 HTML (`asset_kind` proposal: `html` **or** document-family with `document` + `html` representation)

**Recommendation:** separate `asset_kind=html` (clearer registry and cleanup) **or** extend `document` with `source_format=html` only if OD freezes a single document family. Default for V5-F: **`html` kind** to avoid overloading Markdown document adapter.

Required freezes before implementation:

- sanitizer policy: allowlist tags/attrs; strip script/style/event handlers
- external resource policy: block remote scripts; images either blocked or rewritten to safe local fetch policy (pick one; default **block remote active content**, allow data/relative only after sanitize)
- canonical text normalization version (new string, not reuse `document-normalization-v1` without review)
- locator: `html_anchor` with `block_id`, `char_start/end`, `text_sha256`, optional `css_path_hint` (hint only, not truth)
- Viewer: sanitized static render + block highlight; no script execution

OD-B5 must move `rejected` → `approved` with the above policy text.

### 4.2 DOCX (`docx`)

- MIME: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- Parse to normalized blocks (heading/paragraph/table/list)
- Locator: `docx_anchor` (block_id + char range + text_sha256)
- Representation: `docx_normalized_text` (+ optional structure JSON)
- No macro execution; reject encrypted/passworded files fail-closed

### 4.3 XLSX (`xlsx`)

- MIME: spreadsheet OOXML
- ContentUnits: sheet + cell/range text
- Locator: `xlsx_range` with `sheet_name`, `start_cell`, `end_cell`, `text_sha256`
- Viewer: sheet grid or read-only table preview for cited range
- Formula results: store displayed/calculated text snapshot at ingest; do not re-execute untrusted macros

### 4.4 PPTX (`pptx`)

- MIME: presentation OOXML
- ContentUnits: slide text blocks; optional notes
- Locator: `pptx_shape` or `pptx_slide_range` with `slide_index`, shape/block id, text hash
- Viewer: slide canvas/text list + highlight

### 4.5 Audio (`audio`)

**Prerequisite F-ASR:** capability registry must expose real ASR profile or fail-closed `asr_not_configured` before any audio ingest persistence.

- MIME: closed list (propose `audio/mpeg`, `audio/wav`, `audio/mp4`, `audio/webm` — freeze after fixture audit)
- Representations: `audio_normalized` (+ optional waveform peaks object)
- ContentUnits: `audio_transcript_segment` with start_ms/end_ms, speaker optional
- Locator: `audio_range` (`start_ms`, `end_ms`, `text_sha256`)
- Viewer: player + range highlight; no silent ASR skip

### 4.6 Video (`video`)

Depends on F-ASR transcript path + visual keyframe path.

- MIME: closed list (propose `video/mp4`, `video/webm`)
- Representations: `video_normalized`, `video_keyframe_set`, transcript representation
- ContentUnits: transcript segments + optional shot units
- Locators:
  - `video_range` (start_ms/end_ms)
  - `video_frame` (frame_index or timestamp_ms + keyframe object key)
- Viewer: player + timeline + keyframe strip
- Must not register as `audio` with a thumbnail

## 5. Agent collaboration completion contracts

### 5.1 Keep fixed topology

No new step kinds by default. If a new step kind is required, stop and open OD + role-I/O registry version (out of default V5-F).

### 5.2 Multi-modal Research invariants

| ID | Invariant |
|---|---|
| A1 | Researcher `evidence.search` respects frozen scope + only enabled kinds + current generation/index |
| A2 | Returned candidates always include valid typed locator for their kind |
| A3 | Claim evidence handles resolve to immutable snapshots; deleted source → `sourceAvailable=false` |
| A4 | Final report artifact bytes immutable across retry/recovery (F5 oracle retained) |
| A5 | Plan approval freezes asset scope including new kinds; revise creates new revision |
| A6 | Timeline projection shows branch failures with stable error codes (no provider secret leak) |
| A7 | Web can open any cited locator in the correct Evidence module |
| A8 | Mixed-modality Research production-start desktop+mobile passes with scripted provider |

### 5.3 Product UX completion (fixed DAG)

These are productization deltas, not a new platform:

1. **Evidence bundle by modality** — group evidence in Research UI by kind without changing ledger truth.
2. **Temporal evidence affordances** — when locator is audio/video range, show time label and deep-link to player position.
3. **Document/Office anchor affordances** — show heading path / sheet-cell / slide index in citation chips.
4. **Scope clarity** — selected-scope chips list kind icons for all enabled assets.
5. **Failure taxonomy copy** — map existing error codes to user-visible reasons for multi-modal ingest/Research failures (no new business codes unless necessary).
6. **Recovery narrative** — reconnect SSE + restore after refresh remains consistent with multi-modal evidence.

### 5.4 Explicitly deferred agent ideas

Not in V5-F without a new decision:

- user-defined agents/roles
- tool marketplace
- automatic modality-specific sub-agent spawning beyond fixed researcher branches
- cross-workspace multi-agent

## 6. Data / migration policy

- Prefer **additive** tables: `html_locator_details`, `docx_locator_details`, `xlsx_locator_details`, `pptx_locator_details`, `audio_locator_details`, `video_locator_details`, temporal range tables as needed.
- Catalog enablement rows ship in the same migration as code enablement.
- Online migration must be reversible only where safe; catalog disable path must fail readiness if code module missing (existing rule).

## 7. Security policy highlights

| Modality | Hard rule |
|---|---|
| HTML | no script execution; sanitizer mandatory |
| Office | no macro execution; encrypted files rejected |
| Audio/Video | size/duration limits; ASR timeout fail-closed |
| All | Workspace isolation; internal token boundary unchanged |

## 8. Acceptance language

A modality is **production-enabled** only when:

1. registry + catalog + contract_version match
2. focused + mixed tests green
3. production-start browser path green for that kind (or shared mixed gate explicitly covering it)
4. backup/restore identity includes that kind’s objects/rows
5. Critical review for that slice is `ACCEPT` or `ACCEPT with recorded residuals`

Agent collaboration is **complete for V5-F** when A1–A8 hold for the full enabled modality set.
