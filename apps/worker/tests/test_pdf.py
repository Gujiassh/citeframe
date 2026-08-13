import json
from pathlib import Path

import fitz
import numpy as np
import pytest

from ai_pdf_api.modalities.ingestion import IngestionError
from ai_pdf_worker.pdf import (
    _map_page_words,
    _merge_figure_rects,
    detect_visual_region_rects,
    extract_pdf_page_layout,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPOSITORY_ROOT / "docs" / "fixtures" / "evidence-contract"
ARTIFACT_MATRIX_PDF = FIXTURE_ROOT / "pdf-artifact-matrix-fixture.pdf"
ARTIFACT_MATRIX_MANIFEST = FIXTURE_ROOT / "pdf-artifact-matrix-fixture.json"


def test_pdf_layout_adapter_matches_approved_geometry_fixture() -> None:
    manifest = json.loads((FIXTURE_ROOT / "pdf-coordinate-fixture.json").read_text())
    pages = extract_pdf_page_layout((FIXTURE_ROOT / "pdf-coordinate-fixture.pdf").read_bytes())

    assert len(pages) == len(manifest["pages"]) == 12
    for page, expected in zip(pages, manifest["pages"], strict=True):
        geometry = page.geometry
        assert geometry is not None
        assert page.page_number == expected["pageNumber"]
        assert list(geometry.media_box_points) == pytest.approx(expected["mediaBoxPoints"])
        assert list(geometry.crop_box_points) == pytest.approx(expected["cropBoxPoints"])
        assert geometry.rotation_degrees == expected["rotationDegrees"]
        assert geometry.display_width_points == pytest.approx(expected["displayWidthPoints"])
        assert geometry.display_height_points == pytest.approx(expected["displayHeightPoints"])

    for page in pages[4:8]:
        assert page.geometry is not None
        assert page.geometry.crop_box_points == pytest.approx((36.0, 72.0, 576.0, 738.0))
    assert [page.geometry.rotation_degrees for page in pages[4:8] if page.geometry] == [
        0,
        90,
        180,
        270,
    ]
    assert all(not page.artifacts for page in pages[:8])
    assert pages[11].text == ""
    assert pages[11].artifacts == ()


def test_pdf_layout_adapter_matches_approved_artifact_fixture() -> None:
    manifest = json.loads((FIXTURE_ROOT / "pdf-coordinate-fixture.json").read_text())
    pages = extract_pdf_page_layout((FIXTURE_ROOT / "pdf-coordinate-fixture.pdf").read_bytes())

    for page, expected_page in zip(pages, manifest["pages"], strict=True):
        expected_artifacts = expected_page.get("artifacts", [])
        assert len(page.artifacts) == len(expected_artifacts)
        for artifact, expected in zip(page.artifacts, expected_artifacts, strict=True):
            assert artifact.unit_kind == expected["kind"]
            assert artifact.text == expected["text"]
            assert all(page.text[start:end].strip() for start, end in artifact.char_ranges)
            for region, expected_region in zip(
                artifact.regions,
                expected["regions"],
                strict=True,
            ):
                assert [region.x, region.y, region.width, region.height] == pytest.approx(
                    [
                        expected_region["x"],
                        expected_region["y"],
                        expected_region["width"],
                        expected_region["height"],
                    ],
                    abs=1e-6,
                )

    assert [artifact.unit_kind for artifact in pages[8].artifacts] == ["pdf_table"]
    assert [artifact.unit_kind for artifact in pages[9].artifacts] == ["pdf_figure"]
    assert [artifact.unit_kind for artifact in pages[10].artifacts] == ["pdf_figure"]


def test_artifact_matrix_combines_rotation_cropbox_and_spatial_text_mapping() -> None:
    manifest = json.loads(ARTIFACT_MATRIX_MANIFEST.read_text())
    pages = extract_pdf_page_layout(ARTIFACT_MATRIX_PDF.read_bytes())

    assert len(pages) == len(manifest["pages"]) == 12
    for page, expected in zip(pages, manifest["pages"], strict=True):
        geometry = page.geometry
        assert geometry is not None
        assert list(geometry.crop_box_points) == pytest.approx(expected["cropBoxPoints"])
        assert geometry.rotation_degrees == expected["rotationDegrees"]
        assert geometry.display_width_points == pytest.approx(expected["displayWidthPoints"])
        assert geometry.display_height_points == pytest.approx(expected["displayHeightPoints"])
        assert len(page.artifacts) == 1
        artifact = page.artifacts[0]
        assert artifact.unit_kind == expected["artifactKind"]
        assert artifact.text == expected["artifactText"]
        assert len(artifact.regions) == len(expected["regions"])
        for region, expected_region in zip(artifact.regions, expected["regions"], strict=True):
            assert [region.x, region.y, region.width, region.height] == pytest.approx(
                [
                    expected_region["x"],
                    expected_region["y"],
                    expected_region["width"],
                    expected_region["height"],
                ],
                abs=1e-6,
            )

    for page in pages[:4]:
        table = page.artifacts[0]
        assert page.text[table.char_ranges[0][0] : table.char_ranges[0][1]] == (
            "Model Score\nAtlas 91.4"
        )
        assert table.char_ranges[0][0] == page.text.rindex("Model Score")


def test_page_word_mapping_rejects_any_non_whitespace_parser_mismatch() -> None:
    class FakePage:
        def get_text(self, mode: str, *, sort: bool) -> list[tuple[object, ...]]:
            assert mode == "words"
            assert sort is False
            return [
                (0, 0, 10, 10, "A"),
                (12, 0, 22, 10, "B"),
            ]

    page = FakePage()
    assert [(word.char_start, word.char_end) for word in _map_page_words(page, "A\nB")] == [
        (0, 1),
        (2, 3),
    ]
    assert _map_page_words(page, "B A B") == ()
    assert _map_page_words(page, "A X B") == ()
    assert _map_page_words(page, "A B X") == ()


def _colored_pixel_region(page: fitz.Page, pixel_class: str) -> tuple[float, float, float, float]:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    pixels = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height,
        pixmap.width,
        pixmap.n,
    )[:, :, :3]
    red, green, blue = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]
    if pixel_class == "table":
        mask = (red > 150) & (green < 100) & (blue < 100)
    elif pixel_class == "raster":
        mask = (blue > 140) & (green > 50) & (green < 160) & (red < 80)
    else:
        mask = (green > 100) & (red < 100) & (blue < 120)
    y_values, x_values = np.nonzero(mask)
    assert len(x_values) > 20
    return (
        x_values.min() / pixmap.width,
        y_values.min() / pixmap.height,
        (x_values.max() + 1 - x_values.min()) / pixmap.width,
        (y_values.max() + 1 - y_values.min()) / pixmap.height,
    )


def test_artifact_matrix_source_regions_match_rendered_colored_pixels() -> None:
    manifest = json.loads(ARTIFACT_MATRIX_MANIFEST.read_text())
    document = fitz.open(ARTIFACT_MATRIX_PDF)
    try:
        for page, expected in zip(document, manifest["pages"], strict=True):
            measured = _colored_pixel_region(page, expected["pixelClass"])
            source = expected["sourceRegion"]
            assert measured == pytest.approx(
                [source["x"], source["y"], source["width"], source["height"]],
                abs=0.008,
            )
    finally:
        document.close()


def _image_stream(width: int = 180, height: int = 120) -> bytes:
    document = fitz.open()
    page = document.new_page(width=width, height=height)
    page.draw_rect(page.rect, fill=(0.2, 0.45, 0.8), color=(0.2, 0.45, 0.8))
    pixmap = page.get_pixmap(alpha=False)
    payload = pixmap.tobytes("png")
    document.close()
    return payload


def test_pdf_figure_detection_fails_closed_for_decorations_and_unlabelled_images() -> None:
    document = fitz.open()
    icon_page = document.new_page(width=612, height=792)
    icon_page.insert_image(fitz.Rect(72, 90, 136, 154), stream=_image_stream(64, 64))
    icon_page.insert_text((72, 178), "Profile summary", fontsize=16)
    icon_page.insert_text((72, 204), "Ordinary body text must remain searchable.", fontsize=11)

    avatar_page = document.new_page(width=612, height=792)
    avatar_page.insert_image(fitz.Rect(72, 120, 200, 248), stream=_image_stream())
    avatar_page.insert_text((72, 274), "Author biography", fontsize=14)
    avatar_page.insert_text((72, 300), "This is not a figure caption.", fontsize=11)

    photo_page = document.new_page(width=612, height=792)
    photo_page.insert_image(fitz.Rect(72, 160, 480, 420), stream=_image_stream())
    photo_page.insert_text((72, 452), "Unlabelled result photograph.", fontsize=11)

    pages = extract_pdf_page_layout(document.tobytes())
    document.close()

    assert all(page.artifacts == () for page in pages)
    assert "Ordinary body text must remain searchable." in pages[0].text


def test_pdf_figure_detection_requires_an_explicit_caption_marker() -> None:
    document = fitz.open()
    for first_line in (
        "Figure out the next optimization step.",
        "Image processing remains deterministic.",
        "Chart performance across the release.",
    ):
        page = document.new_page(width=612, height=792)
        page.insert_image(fitz.Rect(72, 160, 480, 420), stream=_image_stream())
        page.insert_text((72, 452), first_line, fontsize=11)
        page.insert_text((72, 478), "This second body line must remain ordinary text.", fontsize=11)

    pages = extract_pdf_page_layout(document.tobytes())
    document.close()

    assert all(page.artifacts == () for page in pages)
    assert all("second body line" in page.text for page in pages)


def test_pdf_figure_detection_does_not_absorb_body_text_after_caption() -> None:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_image(fitz.Rect(72, 160, 480, 420), stream=_image_stream())
    page.insert_text((72, 452), "Figure 7. Retrieval latency.", fontsize=11)
    page.insert_text((72, 478), "The next paragraph explains the experiment.", fontsize=11)
    payload = document.tobytes()
    document.close()

    result = extract_pdf_page_layout(payload)[0]

    assert len(result.artifacts) == 1
    assert result.artifacts[0].text == "Figure 7. Retrieval latency."
    assert "next paragraph" in result.text


def test_pdf_figure_detection_deduplicates_mixed_raster_vector_chart() -> None:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    source_rect = fitz.Rect(90, 200, 510, 430)
    page.insert_image(source_rect, stream=_image_stream(420, 230), keep_proportion=False)
    points = [(110, 390), (200, 320), (290, 350), (390, 260), (490, 230)]
    page.draw_polyline(points, color=(0.05, 0.8, 0.2), width=4)
    for point in points:
        page.draw_circle(point, 5, color=(0.05, 0.8, 0.2), fill=(0.05, 0.8, 0.2))
    page.insert_text((90, 462), "Figure 3. Mixed raster vector result.", fontsize=11)
    payload = document.tobytes()
    document.close()

    result = extract_pdf_page_layout(payload)[0]

    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.unit_kind == "pdf_figure"
    assert artifact.text == "Figure 3. Mixed raster vector result."
    assert len(artifact.regions) == 2
    assert [
        artifact.regions[0].x,
        artifact.regions[0].y,
        artifact.regions[0].width,
        artifact.regions[0].height,
    ] == pytest.approx([90 / 612, 200 / 792, 420 / 612, 230 / 792], abs=1e-6)


def _drawing_only_flowchart_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    boxes = [
        fitz.Rect(80, 140, 220, 210),
        fitz.Rect(320, 140, 500, 210),
        fitz.Rect(80, 300, 220, 370),
        fitz.Rect(320, 300, 500, 370),
    ]
    for box in boxes:
        page.draw_rect(box, color=(0.05, 0.15, 0.45), width=2, fill=(0.82, 0.88, 0.96))
    page.draw_line((220, 175), (320, 175), color=(0.05, 0.15, 0.45), width=3)
    page.draw_line((150, 210), (150, 300), color=(0.05, 0.15, 0.45), width=3)
    page.draw_line((410, 210), (410, 300), color=(0.05, 0.15, 0.45), width=3)
    page.insert_text((72, 88), "System architecture overview", fontsize=16)
    payload = document.tobytes()
    document.close()
    return payload


def test_visual_region_detection_finds_drawing_only_figures_without_image_xobjects() -> None:
    payload = _drawing_only_flowchart_pdf()
    document = fitz.open(stream=payload, filetype="pdf")
    try:
        page = document[0]
        assert page.get_image_info() == []
        rects = detect_visual_region_rects(page)
    finally:
        document.close()

    assert rects
    assert any(rect.get_area() > 20_000 for rect in rects)
    assert extract_pdf_page_layout(payload)[0].artifacts == ()


def test_figure_rect_merge_closes_transitive_overlaps_independent_of_input_order() -> None:
    rects = [
        fitz.Rect(0, 0, 100, 100),
        fitz.Rect(200, 0, 300, 100),
        fitz.Rect(0, 10, 270, 100),
    ]

    forward = _merge_figure_rects(rects)
    reverse = _merge_figure_rects(list(reversed(rects)))

    assert [tuple(rect) for rect in forward] == [tuple(fitz.Rect(0, 0, 300, 100))]
    assert [tuple(rect) for rect in reverse] == [tuple(fitz.Rect(0, 0, 300, 100))]

    asymmetric_chain = [
        fitz.Rect(0, 0, 10, 10),
        fitz.Rect(4, 0, 14, 10),
        fitz.Rect(8, 0, 108, 10),
    ]
    assert [tuple(rect) for rect in _merge_figure_rects(asymmetric_chain)] == [
        tuple(fitz.Rect(0, 0, 108, 10))
    ]
    assert [tuple(rect) for rect in _merge_figure_rects(list(reversed(asymmetric_chain)))] == [
        tuple(fitz.Rect(0, 0, 108, 10))
    ]


def test_pdf_layout_adapter_rejects_invalid_pdf() -> None:
    with pytest.raises(IngestionError, match="could not open"):
        extract_pdf_page_layout(b"not a pdf")


def test_approved_regions_are_normalized_in_rotated_display_space() -> None:
    manifest = json.loads((FIXTURE_ROOT / "pdf-coordinate-fixture.json").read_text())
    document = fitz.open(FIXTURE_ROOT / "pdf-coordinate-fixture.pdf")
    source_regions = [
        fitz.Rect(72, 132, 324, 204),
        fitz.Rect(72, 132, 324, 204),
        fitz.Rect(72, 132, 324, 204),
        fitz.Rect(72, 132, 324, 204),
        fitz.Rect(90, 150, 330, 222),
        fitz.Rect(90, 150, 330, 222),
        fitz.Rect(90, 150, 330, 222),
        fitz.Rect(90, 150, 330, 222),
    ]
    try:
        for page, source, expected in zip(
            list(document)[:8],
            source_regions,
            manifest["pages"][:8],
            strict=True,
        ):
            display = source * page.rotation_matrix
            normalized = [
                display.x0 / page.rect.width,
                display.y0 / page.rect.height,
                display.width / page.rect.width,
                display.height / page.rect.height,
            ]
            region = expected["regions"][0]
            assert normalized == pytest.approx(
                [region["x"], region["y"], region["width"], region["height"]],
                abs=1e-6,
            )
    finally:
        document.close()
