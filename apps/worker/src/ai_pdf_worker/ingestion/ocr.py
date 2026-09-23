from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from typing import Any

import numpy as np


@dataclass(frozen=True)
class OcrRegionResult:
    text: str
    x: float
    y: float
    width: float
    height: float
    char_start: int
    char_end: int

    def as_block(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class OcrTextResult:
    text: str
    regions: tuple[OcrRegionResult, ...]


@lru_cache(maxsize=1)
def _build_ocr():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _recognized_text(result: object) -> str:
    """Extract text lines from RapidOCR's ``(rows, elapsed)`` result."""
    if isinstance(result, tuple):
        result = result[0]
    if not isinstance(result, list):
        return ""

    lines: list[str] = []
    for item in result:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        text = item[1]
        if isinstance(text, str) and text.strip():
            lines.append(text.strip())
    return "\n".join(lines)


def _recognized_rows(result: object) -> list[object]:
    if isinstance(result, tuple):
        result = result[0]
    return result if isinstance(result, list) else []


def _normalize_bbox(
    raw_bbox: object,
    width: int,
    height: int,
) -> tuple[float, float, float, float] | None:
    if width <= 0 or height <= 0:
        return None
    try:
        points = list(raw_bbox)  # type: ignore[arg-type]
    except TypeError:
        return None
    coordinates: list[tuple[float, float]] = []
    for point in points:
        try:
            x = float(point[0])  # type: ignore[index]
            y = float(point[1])  # type: ignore[index]
        except (IndexError, TypeError, ValueError):
            return None
        if not isfinite(x) or not isfinite(y):
            return None
        coordinates.append((x, y))
    if len(coordinates) < 2:
        return None

    x_min = max(0.0, min(1.0, min(x for x, _ in coordinates) / width))
    y_min = max(0.0, min(1.0, min(y for _, y in coordinates) / height))
    x_max = max(0.0, min(1.0, max(x for x, _ in coordinates) / width))
    y_max = max(0.0, min(1.0, max(y for _, y in coordinates) / height))
    if x_max <= x_min or y_max <= y_min:
        return None
    return x_min, y_min, x_max, y_max


def _recognized_blocks(result: object, width: int, height: int) -> list[dict[str, Any]]:
    return [region.as_block() for region in _recognized_content(result, width, height).regions]


def _recognized_content(
    result: object,
    width: int,
    height: int,
) -> OcrTextResult:
    lines: list[str] = []
    regions: list[OcrRegionResult] = []
    cursor = 0
    for item in _recognized_rows(result):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        raw_text = item[1]
        if not isinstance(raw_text, str) or not raw_text.strip():
            continue
        text = raw_text.strip()
        if lines:
            cursor += 1
        char_start = cursor
        cursor += len(text)
        lines.append(text)
        bbox = _normalize_bbox(item[0], width, height)
        if bbox is None:
            continue
        x_min, y_min, x_max, y_max = bbox
        regions.append(
            OcrRegionResult(
                text=text,
                x=x_min,
                y=y_min,
                width=x_max - x_min,
                height=y_max - y_min,
                char_start=char_start,
                char_end=cursor,
            )
        )
    return OcrTextResult(text="\n".join(lines), regions=tuple(regions))


def recognize_pixels(pixels: np.ndarray) -> OcrTextResult:
    if pixels.ndim != 3 or pixels.shape[0] < 1 or pixels.shape[1] < 1:
        raise ValueError("OCR pixels require a non-empty height x width x channels array")
    result = _build_ocr()(pixels)
    return _recognized_content(result, pixels.shape[1], pixels.shape[0])
