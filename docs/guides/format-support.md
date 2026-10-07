# Supported formats

All listed formats have an ingestion adapter, searchable text content, and typed source locations. This describes current implementation capabilities; it does not establish extraction accuracy or answer quality for every file.

| Format | Accepted files | Retrieval and citations | Viewer and limitations |
| --- | --- | --- | --- |
| PDF | PDF | Native text, OCR regions, tables, and figure descriptions; page/region citations | PDF.js pages, text/OCR selection, and region overlays. OCR and layout extraction can lose or misread content. |
| Image | PNG, JPEG, WebP | OCR and caption text; image-region citations | Oriented image with zoom, pan, and region overlays. Captioning requires a configured provider. |
| Markdown | Markdown (`text/markdown`) | Normalized blocks and character-range anchors | Block-oriented document viewer; normalized content is the citation target. |
| HTML | HTML, XHTML | Sanitized blocks and character-range anchors | Sanitized content only; scripts, styles, and embedded frames are removed. Original page behavior and styling are not reproduced. |
| DOCX | Unencrypted, macro-free DOCX | Headings, paragraphs, list items, and table text; block/range anchors | Normalized text blocks and highlights. Original pagination and full Word styling are not reproduced. |
| XLSX | Unencrypted, macro-free XLSX | Extracted cell text; sheet/cell-range locators | Normalized cell content and source ranges. The parser does not calculate formulas or provide a spreadsheet editing engine. |
| PPTX | Unencrypted, macro-free PPTX | Slide/shape text; shape locators | Layout-aware shapes and available picture media, with normalized text fallback. Full PowerPoint rendering, fonts, animation, and effects are not guaranteed. |
| Audio | MP3/MPEG/MPGA, WAV, M4A/MP4, WebM with an accepted audio MIME | ASR transcript segments; time-range locators | Audio player and transcript. ASR must be configured; accuracy depends on the recording and model. |
| Video | MP4/M4V, WebM with an accepted video MIME | ASR transcript segments; time ranges and optional frame locators | Video player, transcript, and available keyframes. Extraction uses ffmpeg/ffprobe and may be skipped when tooling is missing or extraction fails. |

PDF and image workflows have the deepest visual evidence support. Other viewers focus on normalized content or media positions. Text embeddings are used for retrieval; a separate shared visual/audio embedding space is not enabled.

## Upload and processing constraints

The API validates declared MIME, file bytes, and size. A matching filename extension alone does not make a file valid. Office packages containing macros or encrypted content are rejected. The default upload limit is 100 MB, controlled by `AI_PDF_MAX_UPLOAD_BYTES`.

Successful upload is followed by asynchronous parsing and indexing. Missing model capabilities or invalid source data produce an explicit failure. Video keyframes have a documented soft-skip path; unavailable frames are never fabricated. See [uploads](uploads.md) and [model configuration](model-configuration.md).

## Implementation references

- [Modality registry](../../apps/api/src/ai_pdf_api/modalities/registry.py)
- [Worker ingestion adapters](../../apps/worker/src/ai_pdf_worker/ingestion/)
- [Evidence renderers](../../apps/web/src/components/evidence/)
- [Office package validation](../../apps/api/src/ai_pdf_api/modalities/office_ooxml.py)
