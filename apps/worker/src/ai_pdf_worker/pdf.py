from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from math import isclose
import re

import fitz
import numpy as np
from pypdf import PdfReader

from ai_pdf_api.modalities.pdf_ingestion import (
    PageArtifactResult,
    PageTextResult,
    PdfPageGeometryResult,
    SpatialRegionResult,
)
from ai_pdf_api.modalities.ingestion import IngestionError


_FIGURE_CAPTION_PREFIX = re.compile(
    r"^(?:figure|fig|chart|image|photo|图表?|图片)"
    r"(?:\s*(?:\d+[a-z]?|[一二三四五六七八九十]+)\s*(?:[:.：、-]\s*)?|\s*[:.：、-]\s*)\S+",
    re.IGNORECASE,
)
_FIGURE_CAPTION_CONTINUATION = re.compile(
    r"^(?:(?:supporting|continued)\s+caption|caption\s+continued)(?:\s*[:.：、-]\s*|\s+)\S+"
    r"|^(?:source|note|来源|注)\s*[:：]\s*\S+",
    re.IGNORECASE,
)


def _box_points(box: object) -> tuple[float, float, float, float]:
    try:
        values = tuple(float(value) for value in box)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise IngestionError("pdf_geometry_invalid", "PDF page box is invalid.") from error
    if len(values) != 4:
        raise IngestionError("pdf_geometry_invalid", "PDF page box must contain four points.")
    return values


def _close_box(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return all(isclose(a, b, abs_tol=0.01) for a, b in zip(left, right, strict=True))


def _page_geometry(pdf_page: object, layout_page: fitz.Page) -> PdfPageGeometryResult:
    try:
        media_box = _box_points(pdf_page.mediabox)  # type: ignore[attr-defined]
        pdf_crop_box = _box_points(pdf_page.cropbox)  # type: ignore[attr-defined]
        rotation = int(pdf_page.get("/Rotate", 0) or 0) % 360  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError) as error:
        raise IngestionError("pdf_geometry_invalid", "PDF page geometry is invalid.") from error

    # PyMuPDF exposes CropBox in an unrotated top-left coordinate system. Convert
    # it directly to PDF user space; transformation_matrix changes on rotated,
    # cropped pages and cannot reliably recover the original box there.
    media_box = layout_page.mediabox
    layout_crop_box = layout_page.cropbox
    layout_crop = (
        layout_crop_box.x0,
        media_box.y1 - layout_crop_box.y1,
        layout_crop_box.x1,
        media_box.y1 - layout_crop_box.y0,
    )
    if not _close_box(pdf_crop_box, layout_crop):
        raise IngestionError(
            "pdf_geometry_mismatch",
            "PDF parsers disagree on the page CropBox.",
        )
    if rotation != layout_page.rotation:
        raise IngestionError(
            "pdf_geometry_mismatch",
            "PDF parsers disagree on the page rotation.",
        )
    return PdfPageGeometryResult(
        media_box_points=media_box,
        crop_box_points=pdf_crop_box,
        rotation_degrees=rotation,
        display_width_points=layout_page.rect.width,
        display_height_points=layout_page.rect.height,
    )


def _normalized_region(rect: fitz.Rect, page: fitz.Page, *, display_space: bool) -> SpatialRegionResult:
    display_rect = rect if display_space else rect * page.rotation_matrix
    display_rect &= page.rect
    if display_rect.is_empty or display_rect.width <= 0 or display_rect.height <= 0:
        raise ValueError("PDF artifact region is outside the displayed page")
    return SpatialRegionResult(
        x=display_rect.x0 / page.rect.width,
        y=display_rect.y0 / page.rect.height,
        width=display_rect.width / page.rect.width,
        height=display_rect.height / page.rect.height,
    )


@dataclass(frozen=True)
class _MappedWord:
    rect: fitz.Rect
    char_start: int
    char_end: int


def _map_page_words(page: fitz.Page, page_text: str) -> tuple[_MappedWord, ...]:
    mapped: list[_MappedWord] = []
    cursor = 0
    for word in page.get_text("words", sort=False):
        text = str(word[4]).strip()
        if not text:
            continue
        match = re.search(re.escape(text), page_text[cursor:])
        if match is None:
            return ()
        if page_text[cursor : cursor + match.start()].strip():
            return ()
        char_start = cursor + match.start()
        char_end = cursor + match.end()
        mapped.append(
            _MappedWord(
                rect=fitz.Rect(word[:4]),
                char_start=char_start,
                char_end=char_end,
            )
        )
        cursor = char_end
    if page_text[cursor:].strip():
        return ()
    return tuple(mapped)


def _source_text_ranges(
    page_text: str,
    mapped_words: tuple[_MappedWord, ...],
    source_rects: list[fitz.Rect],
) -> tuple[tuple[int, int], ...]:
    ranges = [
        (word.char_start, word.char_end)
        for word in mapped_words
        if any(rect.contains(word.rect.tl + (word.rect.br - word.rect.tl) / 2) for rect in source_rects)
    ]
    if not ranges:
        return ()
    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and page_text[merged[-1][1] : start].isspace():
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return tuple(merged)


def _table_markdown(rows: list[list[str | None]]) -> tuple[str, list[str]] | None:
    normalized = [
        [cell.strip() if isinstance(cell, str) else "" for cell in row]
        for row in rows
    ]
    normalized = [row for row in normalized if any(row)]
    if len(normalized) < 2 or sum(sum(bool(cell) for cell in row) >= 2 for row in normalized) < 2:
        return None
    width = max(len(row) for row in normalized)
    normalized = [row + [""] * (width - len(row)) for row in normalized]
    header, *body = normalized
    markdown_rows = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
        *("| " + " | ".join(row) + " |" for row in body),
    ]
    return "\n".join(markdown_rows), [cell for row in normalized for cell in row if cell]


def _text_lines(page: fitz.Page) -> list[tuple[fitz.Rect, str]]:
    lines: list[tuple[fitz.Rect, str]] = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            text = "".join(str(span["text"]) for span in line["spans"]).strip()
            if text:
                lines.append((fitz.Rect(line["bbox"]), text))
    return lines


def _horizontal_overlap_ratio(left: fitz.Rect, right: fitz.Rect) -> float:
    overlap = max(0.0, min(left.x1, right.x1) - max(left.x0, right.x0))
    return overlap / min(left.width, right.width)


def _captions_below(
    source_rect: fitz.Rect,
    lines: list[tuple[fitz.Rect, str]],
) -> list[tuple[fitz.Rect, str]]:
    candidates = [
        (rect, text)
        for rect, text in lines
        if 0 <= rect.y0 - source_rect.y1 <= 36
        and rect.width <= source_rect.width + 48
        and _horizontal_overlap_ratio(source_rect, rect) >= 0.5
    ]
    candidates.sort(key=lambda item: (item[0].y0, item[0].x0))
    if not candidates or _FIGURE_CAPTION_PREFIX.match(candidates[0][1]) is None:
        return []
    captions = [candidates[0]]
    for candidate in sorted(lines, key=lambda item: (item[0].y0, item[0].x0)):
        if len(captions) >= 3:
            break
        rect, text = candidate
        previous_rect = captions[-1][0]
        if rect.y0 <= previous_rect.y0:
            continue
        if not 0 <= rect.y0 - previous_rect.y1 <= 28:
            continue
        if rect.width > source_rect.width + 48:
            continue
        if _horizontal_overlap_ratio(source_rect, rect) < 0.5:
            continue
        if _FIGURE_CAPTION_CONTINUATION.match(text) is None:
            continue
        captions.append((rect, text))
    if sum(len(text) for _rect, text in captions) > 500:
        return []
    return captions


def _rect_overlap_ratio(left: fitz.Rect, right: fitz.Rect) -> float:
    intersection = left & right
    if intersection.is_empty:
        return 0.0
    return intersection.get_area() / min(left.get_area(), right.get_area())


def _display_rect(rect: fitz.Rect, page: fitz.Page) -> fitz.Rect:
    return (rect * page.rotation_matrix) & page.rect


def _figure_size_ok(display_rect: fitz.Rect, page_area: float) -> bool:
    if display_rect.is_empty or display_rect.width <= 0 or display_rect.height <= 0:
        return False
    area_ratio = display_rect.get_area() / page_area
    return (
        0.02 <= area_ratio < 0.9
        and display_rect.width >= 96
        and display_rect.height >= 72
    )


def _embedded_and_drawing_figure_rects(
    page: fitz.Page,
    table_rects: list[fitz.Rect],
) -> list[fitz.Rect]:
    figure_rects: list[fitz.Rect] = []
    page_area = page.rect.width * page.rect.height
    for image in page.get_image_info():
        rect = fitz.Rect(image["bbox"])
        if _figure_size_ok(_display_rect(rect, page), page_area):
            figure_rects.append(rect)

    drawings = page.get_drawings()
    for cluster in page.cluster_drawings(drawings=drawings):
        rect = fitz.Rect(cluster)
        member_count = sum(rect.intersects(fitz.Rect(drawing["rect"])) for drawing in drawings)
        overlaps_table = any(rect.intersects(table_rect) for table_rect in table_rects)
        if (
            member_count >= 4
            and not overlaps_table
            and _figure_size_ok(_display_rect(rect, page), page_area)
        ):
            figure_rects.append(rect)
    return figure_rects


def detect_rendered_visual_rects(page: fitz.Page) -> list[fitz.Rect]:
    """Find figure-like ink blocks from a raster, without Image XObjects."""
    zoom = 1.0
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    pixels = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height,
        pixmap.width,
        pixmap.n,
    )[:, :, :3]
    luminance = pixels.mean(axis=2)
    chroma = pixels.max(axis=2) - pixels.min(axis=2)
    ink = (luminance < 246) | (chroma > 16)

    text_mask = np.zeros((pixmap.height, pixmap.width), dtype=bool)
    for word in page.get_text("words"):
        display = _display_rect(fitz.Rect(word[:4]), page)
        x0 = max(0, int(display.x0 * zoom))
        y0 = max(0, int(display.y0 * zoom))
        x1 = min(pixmap.width, int(display.x1 * zoom) + 1)
        y1 = min(pixmap.height, int(display.y1 * zoom) + 1)
        if x1 > x0 and y1 > y0:
            text_mask[y0:y1, x0:x1] = True
    visual = ink & ~text_mask

    cell = 8
    height, width = visual.shape
    grid_h, grid_w = height // cell, width // cell
    if grid_h < 2 or grid_w < 2:
        return []
    grid = visual[: grid_h * cell, : grid_w * cell].reshape(grid_h, cell, grid_w, cell).any(axis=(1, 3))
    visited = np.zeros_like(grid, dtype=bool)
    page_area = page.rect.width * page.rect.height
    rects: list[fitz.Rect] = []
    neighbors = ((1, 0), (-1, 0), (0, 1), (0, -1))
    for start_y in range(grid_h):
        for start_x in range(grid_w):
            if not grid[start_y, start_x] or visited[start_y, start_x]:
                continue
            stack = [(start_y, start_x)]
            visited[start_y, start_x] = True
            min_y = max_y = start_y
            min_x = max_x = start_x
            cells = 0
            while stack:
                cy, cx = stack.pop()
                cells += 1
                min_y, max_y = min(min_y, cy), max(max_y, cy)
                min_x, max_x = min(min_x, cx), max(max_x, cx)
                for dy, dx in neighbors:
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < grid_h and 0 <= nx < grid_w and grid[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))
            if cells < 8:
                continue
            rect = fitz.Rect(
                min_x * cell / zoom,
                min_y * cell / zoom,
                min((max_x + 1) * cell, width) / zoom,
                min((max_y + 1) * cell, height) / zoom,
            )
            display = rect & page.rect
            if _figure_size_ok(display, page_area):
                # Store in unrotated user space so _normalized_region(display_space=False) matches figures.
                user_rect = display * ~page.rotation_matrix
                rects.append(user_rect)
    return _merge_figure_rects(rects)


def detect_visual_region_rects(page: fitz.Page, table_rects: list[fitz.Rect] | None = None) -> list[fitz.Rect]:
    tables = table_rects or []
    return _merge_figure_rects(
        _embedded_and_drawing_figure_rects(page, tables) + detect_rendered_visual_rects(page)
    )


def _merge_figure_rects(rects: list[fitz.Rect]) -> list[fitz.Rect]:
    candidates = sorted(
        (fitz.Rect(rect) for rect in rects),
        key=lambda rect: (rect.y0, rect.x0, rect.y1, rect.x1),
    )
    merged: list[fitz.Rect] = []
    visited: set[int] = set()
    for start_index in range(len(candidates)):
        if start_index in visited:
            continue
        component: list[int] = []
        pending = [start_index]
        visited.add(start_index)
        while pending:
            current_index = pending.pop()
            component.append(current_index)
            for candidate_index, candidate in enumerate(candidates):
                if candidate_index in visited:
                    continue
                if _rect_overlap_ratio(candidates[current_index], candidate) >= 0.6:
                    visited.add(candidate_index)
                    pending.append(candidate_index)
        combined = fitz.Rect(candidates[component[0]])
        for candidate_index in component[1:]:
            combined |= candidates[candidate_index]
        merged.append(combined)
    return sorted(merged, key=lambda rect: (rect.y0, rect.x0, rect.y1, rect.x1))


def _ranges_overlap(
    left: tuple[tuple[int, int], ...],
    right: tuple[tuple[int, int], ...],
) -> bool:
    return any(
        left_start < right_end and left_end > right_start
        for left_start, left_end in left
        for right_start, right_end in right
    )


def _table_results(page: fitz.Page) -> list[tuple[fitz.Rect, list[list[str | None]]]]:
    page.set_rotation(0)
    crop_box = tuple(page.cropbox)
    page_rect = tuple(page.rect)
    try:
        tables = page.find_tables().tables
    except Exception:
        return []
    if not _close_box(crop_box, tuple(page.cropbox)) or not _close_box(page_rect, tuple(page.rect)):
        return []
    return [(fitz.Rect(table.bbox), table.extract()) for table in tables]


def _extract_page_artifacts(
    page: fitz.Page,
    table_page: fitz.Page,
    page_text: str,
) -> tuple[PageArtifactResult, ...]:
    artifacts: list[PageArtifactResult] = []
    claimed_ranges: list[tuple[tuple[int, int], ...]] = []
    mapped_words = _map_page_words(page, page_text)
    if not mapped_words:
        return ()
    table_rects: list[fitz.Rect] = []
    for table_rect, rows in _table_results(table_page):
        table_data = _table_markdown(rows)
        if table_data is None:
            continue
        markdown, _source_cells = table_data
        char_ranges = _source_text_ranges(page_text, mapped_words, [table_rect])
        if not char_ranges:
            continue
        if any(_ranges_overlap(char_ranges, existing) for existing in claimed_ranges):
            continue
        table_rects.append(table_rect)
        claimed_ranges.append(char_ranges)
        artifacts.append(
            PageArtifactResult(
                text=markdown,
                unit_kind="pdf_table",
                regions=(_normalized_region(table_rect, page, display_space=False),),
                char_ranges=char_ranges,
            )
        )

    lines = _text_lines(page)
    figure_rects = _embedded_and_drawing_figure_rects(page, table_rects)

    proposals: list[
        tuple[float, float, PageArtifactResult]
    ] = []
    for source_rect in _merge_figure_rects(figure_rects):
        captions = _captions_below(source_rect, lines)
        if not captions:
            continue
        caption_texts = [text for _rect, text in captions]
        char_ranges = _source_text_ranges(
            page_text,
            mapped_words,
            [rect for rect, _text in captions],
        )
        if not char_ranges:
            continue
        try:
            artifact = PageArtifactResult(
                    text="\n".join(caption_texts),
                    unit_kind="pdf_figure",
                    regions=(
                        _normalized_region(source_rect, page, display_space=False),
                        *(
                            _normalized_region(rect, page, display_space=False)
                            for rect, _text in captions
                        ),
                    ),
                    char_ranges=char_ranges,
                )
        except ValueError:
            continue
        proposals.append(
            (
                captions[0][0].y0 - source_rect.y1,
                -source_rect.get_area(),
                artifact,
            )
        )
    for _gap, _area, artifact in sorted(proposals, key=lambda item: (item[0], item[1])):
        if any(_ranges_overlap(artifact.char_ranges, existing) for existing in claimed_ranges):
            continue
        claimed_ranges.append(artifact.char_ranges)
        artifacts.append(artifact)
    return tuple(artifacts)


def extract_pdf_page_layout(payload: bytes) -> list[PageTextResult]:
    try:
        text_reader = PdfReader(BytesIO(payload))
        layout_document = fitz.open(stream=payload, filetype="pdf")
    except Exception as error:
        raise IngestionError("pdf_parse_failed", "PDF parser could not open the file.") from error

    try:
        if len(text_reader.pages) != len(layout_document):
            raise IngestionError(
                "pdf_page_count_mismatch",
                "PDF parsers disagree on the page count.",
            )
        table_document = fitz.open(stream=payload, filetype="pdf")
        pages: list[PageTextResult] = []
        for page_number, (text_page, layout_page, table_page) in enumerate(
            zip(text_reader.pages, layout_document, table_document, strict=True),
            start=1,
        ):
            page_text = text_page.extract_text() or ""
            pages.append(
                PageTextResult(
                    page_number=page_number,
                    text=page_text,
                    geometry=_page_geometry(text_page, layout_page),
                    artifacts=_extract_page_artifacts(layout_page, table_page, page_text),
                )
            )
        return pages
    finally:
        if "table_document" in locals():
            table_document.close()
        layout_document.close()
