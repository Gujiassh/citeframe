# S0 handoff: office kinds registry enablement

Lane: `office`  
Date: 2026-08-13  
Implementer: grok-4.5 (`019ffa01-715e-7d80-83e4-c26c3305d653`)

This slice ships **code + typed tables + isolated tests** for separate kinds
`docx`, `xlsx`, and `pptx`. It does **not** enable those kinds in
`build_production_registry()` or insert catalog rows.

## Why controller must enable

`ModalityRegistry.validate_catalog` requires code modules and DB catalog to
match exactly. Enabling office kinds in code without catalog rows (or the
reverse) fails readiness. Lane brief forbids shared registry enable here.

## What to enable (controller)

1. Add `DOCX_MODULE`, `XLSX_MODULE`, `PPTX_MODULE` from
   `apps/api/src/ai_pdf_api/modalities/office_modules.py` to
   `build_production_registry()` with `enabled=True`.
2. Additive catalog migration in the **same** deploy as code enablement:
   - `asset_types`: `docx`, `xlsx`, `pptx` (`enabled=true`, contract 1)
   - representations: `docx_source`/`docx_normalized`, `xlsx_*`, `pptx_*`
   - content units: `docx_text_chunk`, `xlsx_cell_text`, `pptx_shape_text`
   - locators: `docx_anchor`, `xlsx_range`, `pptx_shape` (`detail_family=record`)
3. Web production evidence registry + viewers (heading path / sheet-cell /
   slide index chips) after API catalog enable.
4. Do not introduce a vague `office` asset_kind.

## Already landed in this lane

- Shared OOXML inspect: `office_ooxml.py` (encrypted/OLE fail-closed, no macros)
- Parse/normalize + locators for all three kinds
- Additive tables: `docx_normalized_contents`, `docx_blocks`,
  `docx_locator_details`, `xlsx_locator_details`, `pptx_locator_details`
- Worker adapters registered for isolated ingest (upload still fail-closed)
- Locator codecs + public DTO kinds (serialization only)

## Residual

Production upload/catalog/readiness, mixed restore, and browser production-start
remain blocked on this S0 enablement.

---

# S0 handoff: enable HTML modality

HTML slice ships sanitizer, typed tables, adapter, fixtures, tests, and a
viewer. **Production registry/catalog are not enabled** in this PR.

Controller should apply these patches in one deploy so readiness stays aligned.

## 1. Registry last line

File: `apps/api/src/ai_pdf_api/modalities/registry.py`

Replace `build_production_registry` with:

```python
def build_production_registry() -> ModalityRegistry:
    return ModalityRegistry(
        (PDF_MODULE, IMAGE_MODULE, DOCUMENT_MODULE, HTML_MODULE),
        embedding_spaces=(TypeRegistration("text"),),
    )
```

`HTML_MODULE` and `build_html_ready_registry()` already exist.

## 2. Worker adapter registry

File: `apps/worker/src/ai_pdf_worker/main.py`

Add `HtmlIngestionAdapter()` next to `DocumentIngestionAdapter()`.

## 3. Catalog rows (same migration as enable)

Additive inserts only:

```sql
INSERT INTO asset_types(kind, contract_version, enabled)
VALUES ('html', 1, true);

INSERT INTO representation_types(kind, asset_kind, contract_version) VALUES
  ('html_source', 'html', 1),
  ('html_normalized', 'html', 1),
  ('html_sanitized', 'html', 1);

INSERT INTO content_unit_types(kind, asset_kind, contract_version) VALUES
  ('html_block', 'html', 1),
  ('html_text_chunk', 'html', 1);

INSERT INTO locator_types(kind, contract_version, detail_family)
VALUES ('html_anchor', 1, 'record');
```

Tables `html_normalized_contents`, `html_blocks`, `html_locator_details` already
ship in `i3c4d5e6f7a8`.

## 4. Web upload (optional same slice)

`production-registry.ts` already registers the HTML renderer with
`uploadAccept: []`. To accept uploads, add `text/html` to
`PRODUCTION_UPLOAD_MIME_TYPES` and the HTML module `uploadAccept`.

## 5. Tests that must flip

- `test_production_registry_enables_pdf_image_and_document_ingestion`
- any catalog snapshot equality tests
- worker `INGESTION_ADAPTERS` membership tests

Do not enable catalog without the worker adapter, or readiness will fail.

---

# S0 handoff: enable audio modality

Audio slice ships MIME freeze, typed tables, ASR-gated adapter, locator codec,
viewer, and tests. **Production registry/catalog are not enabled** in this PR.

Controller should apply these patches in one deploy so readiness stays aligned.

## 1. Registry

File: `apps/api/src/ai_pdf_api/modalities/registry.py`

Add `AUDIO_MODULE` to `build_production_registry()` (with any other S0 modules
already staged for the same deploy). Do not enable audio alone without catalog
rows and the worker adapter.

`AUDIO_MODULE` and `build_audio_ready_registry()` already exist.

## 2. Worker adapter registry

File: `apps/worker/src/ai_pdf_worker/main.py`

`AudioIngestionAdapter()` is already registered for isolated ingest. Keep it
when enabling production.

## 3. Catalog rows (same migration as enable)

Additive inserts only:

```sql
INSERT INTO asset_types(kind, contract_version, enabled)
VALUES ('audio', 1, true);

INSERT INTO representation_types(kind, asset_kind, contract_version) VALUES
  ('audio_source', 'audio', 1),
  ('audio_normalized', 'audio', 1);

INSERT INTO content_unit_types(kind, asset_kind, contract_version) VALUES
  ('audio_transcript_segment', 'audio', 1);

INSERT INTO locator_types(kind, contract_version, detail_family)
VALUES ('audio_range', 1, 'temporal');
```

Tables `audio_normalized_contents`, `audio_transcript_segments`,
`audio_locator_details` already ship in `k5e6f7a8b9c0`.

## 4. Web upload (optional same slice)

`production-registry.ts` already registers the audio renderer with
`uploadAccept: []`. To accept uploads, add the frozen MIME list
(`audio/mpeg`, `audio/wav`, `audio/mp4`, `audio/webm`) to upload accept.

## 5. ASR prerequisite

Production audio ingest **requires** a configured OpenAI ASR secret
(`AI_PDF_OPENAI_API_KEY` / `OPENAI_API_KEY`). Missing secret fails closed with
`asr_not_configured` before any representation or content-unit persist.
Never invent transcripts.

## 6. Tests that must flip

- production registry membership for `audio`
- catalog snapshot equality tests
- worker `INGESTION_ADAPTERS` membership if asserted against production-only set

Do not enable catalog without the worker adapter and ASR ops readiness.

