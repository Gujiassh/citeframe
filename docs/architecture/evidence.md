# Evidence and saved sources

## Domain responsibilities

- **Asset**: Workspace ownership, source identity, type, and lifecycle.
- **Representation**: immutable versioned parsing, OCR, layout, caption, or transcript output.
- **ContentUnit**: addressable text, region, cell, shape, or media segment used for retrieval.
- **Embedding**: rebuildable index projection bound to a content unit and model contract.
- **EvidenceLocator**: typed source position and version.
- **Citation**: answer-time locator, excerpt/title, and source-version snapshot.
- **NoteSource**: independent copy of the source and locator snapshot.

Locators have a closed discriminator/version contract and typed detail tables. Unknown kinds/versions fail validation. New formats supply their own codec and renderer.

## Spatial coordinates

`pdf_page` has a 1-based `pageNumber` and denotes an entire page. Historical page-only citations retain page-only meaning.

`pdf_region` uses `pdf_crop_box_normalized_top_left_v1`: coordinates normalize to the displayed CropBox after rotation, with origin at top left, x increasing rightward and y downward. `pageGeometry` freezes CropBox points, rotation, and displayed dimensions. OCR pixmaps already include CropBox/rotation; normalize their boxes by pixmap size. Native layout coordinates use the page rotation matrix to reach display coordinates.

`image_region` uses `image_normalized_top_left_v1` on EXIF-oriented pixels. `widthPixels`, `heightPixels`, and `orientationApplied` describe that space. Viewer uses the canonical oriented representation, while OCR/caption representation identity remains the cited evidence source.

Regions have `0 <= x,y <= 1`, positive width/height, and stay inside their page/image. Multiple regions are ordered and jointly support one citation within one page/image. Cross-page evidence uses separate citations. Full-image evidence uses a whole-image region.

## Text and temporal locations

Markdown, HTML, and DOCX anchors bind normalized blocks and character ranges to frozen generation/representation and content hashes. XLSX uses sheet/cell ranges; PPTX uses slide/shape identities. Audio uses transcript time ranges; video supports time ranges and available frame identities. Display and retrieval validate typed locators against their matching representations.

## History, deletion, and reindexing

Citation indices start at 0 within one assistant message; rendered `[n]` references map to `citationIndex = n - 1`. Citation-to-note accepts actual citations from the current Workspace and copies full source snapshots.

Reindexing replaces current retrieval projections without rewriting saved locator, title, excerpt, or source versions. Asset deletion cleans source/derived objects and current content projections; historical representations/locators and citation/note snapshots remain for replay. `sourceAvailable` reflects present availability without mutating snapshots. Deleted sources cannot reopen in Viewer.

Source identity is fixed after the first upload PUT. Finalization checks size/hash under the Asset lock. A different source requires a new Asset.

Viewer zoom, scroll, focus, and drafts are not persisted locator semantics. Aggregate counts/distributions require structured analysis; retrieved samples cannot establish complete dataset totals.

## Migration and recovery

The Document-to-Asset migration is not an in-place reversible downgrade. Recovering the old Document model requires a matching pre-migration PostgreSQL/object-storage backup. Legacy page citations map mechanically to `pdf_page`; no regions are inferred.

Schema, codec, API union, viewer, cleanup, and replay must evolve together when adding/changing locators. Fixtures cover rotation/CropBox, scans, EXIF, ordered multi-region evidence, deleted sources, reindexing, and backup/restore. [Fixtures](../fixtures/evidence-contract/) retain historical payload examples; runtime schemas are defined in [API schemas](../../apps/api/src/ai_pdf_api/schemas/) and [locator codecs](../../apps/api/src/ai_pdf_api/modalities/).
