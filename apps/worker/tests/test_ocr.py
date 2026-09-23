import numpy as np
import pytest

import ai_pdf_worker.ingestion.ocr as ocr_module
from ai_pdf_worker.ingestion.ocr import (
    _recognized_blocks,
    _recognized_content,
    _recognized_text,
    recognize_pixels,
)


def test_recognized_text_unwraps_rapidocr_result() -> None:
    result = (
        [
            ([[0, 0], [10, 0], [10, 10], [0, 10]], "第一页标题", 0.99),
            ([[0, 20], [10, 20], [10, 30], [0, 30]], "正文内容", 0.98),
        ],
        [0.1, 0.2, 0.3],
    )

    assert _recognized_text(result) == "第一页标题\n正文内容"


def test_recognized_text_ignores_empty_and_malformed_rows() -> None:
    result = [
        None,
        [],
        ([[0, 0]], "  ", 0.1),
        ([[0, 0]], "有效文本", 0.9),
        ("invalid", 1),
    ]

    assert _recognized_text(result) == "有效文本"


def test_recognized_blocks_normalizes_and_clamps_bbox() -> None:
    result = [
        ([[-10, -20], [120, 0], [120, 220], [-10, 220]], "边界文本", 1.4),
        ([[20, 40], [60, 40], [60, 80], [20, 80]], "第二块", 0.75),
    ]

    blocks = _recognized_blocks(result, width=100, height=200)

    assert blocks[0] == {"text": "边界文本", "x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    assert blocks[1]["text"] == "第二块"
    assert blocks[1]["x"] == pytest.approx(0.2)
    assert blocks[1]["y"] == pytest.approx(0.2)
    assert blocks[1]["width"] == pytest.approx(0.4)
    assert blocks[1]["height"] == pytest.approx(0.2)


def test_recognized_page_content_preserves_text_ranges_for_regions() -> None:
    result = [
        ([[0, 0], [50, 0], [50, 20], [0, 20]], "第一行", 0.9),
        ([[0, 40], [80, 40], [80, 60], [0, 60]], "第二行", 0.8),
    ]

    recognized = _recognized_content(result, width=100, height=100)

    assert recognized.text == "第一行\n第二行"
    assert [region.text for region in recognized.regions] == ["第一行", "第二行"]
    assert [(region.char_start, region.char_end) for region in recognized.regions] == [
        (0, 3),
        (4, 7),
    ]


def test_recognize_pixels_calls_engine_with_pixel_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ocr_module,
        "_build_ocr",
        lambda: lambda image: (
            [([[10, 20], [60, 20], [60, 80], [10, 80]], "扫描文本", 0.91)],
            [0.01],
        ),
    )

    recognized = recognize_pixels(np.zeros((200, 100, 3), dtype=np.uint8))

    assert recognized.text == "扫描文本"
    assert len(recognized.regions) == 1
    assert recognized.regions[0].x == pytest.approx(0.1)
    assert recognized.regions[0].y == pytest.approx(0.1)
    assert recognized.regions[0].width == pytest.approx(0.5)
    assert recognized.regions[0].height == pytest.approx(0.3)
