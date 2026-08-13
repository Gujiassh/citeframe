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
