# pdf-visual-v1 worker slice

Date: 2026-08-13

## Commands

```bash
uv run --python 3.12 --project apps/worker python -m pytest \
  apps/worker/tests/test_pdf.py \
  apps/worker/tests/test_pdf_ingestion.py -q
```

Result: `22 passed`.

## Scope

- Detection: Image XObjects ∪ drawing clusters ∪ rendered ink blocks
- Region OCR + required caption for abstract figures (existing vision capability)
- Fail-closed when vision is not configured
- No Chat save-contract change
