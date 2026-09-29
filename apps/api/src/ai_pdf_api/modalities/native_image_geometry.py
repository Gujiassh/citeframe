"""Unactivated numeric crop planning; callers own source provenance and resource limits."""
from dataclasses import dataclass
from decimal import (
    Context, Decimal, DivisionByZero, InvalidOperation, Overflow,
    ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext,
)
import math


_INVALID = "native_image_geometry_invalid"
_EMPTY = "native_image_geometry_empty"
_ENGINE = "native_image_geometry_engine_unsupported"


def _coordinates(value: object) -> tuple:
    if type(value) is not tuple or len(value) != 4:
        raise ValueError(_INVALID)
    try:
        if any(type(item) not in (int, float) or not math.isfinite(item) for item in value):
            raise ValueError(_INVALID)
    except OverflowError:
        raise ValueError(_INVALID) from None
    return value


def _region(value: object) -> tuple[float, float, float, float]:
    x, y, width, height = _coordinates(value)
    if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < width <= 1 and 0 < height <= 1
            and x + width <= 1 and y + height <= 1):
        raise ValueError(_INVALID)
    return tuple(float(item) for item in (x, y, width, height))


def _rectangle(value: object) -> tuple:
    rect = _coordinates(value)
    if any(abs(item) > 1_000_000 for item in rect) or rect[2] <= rect[0] or rect[3] <= rect[1]:
        raise ValueError(_INVALID)
    return rect


def png_crop_bounds(
    *, width_pixels: int, height_pixels: int,
    region: tuple[float, float, float, float],
) -> tuple[int, int, int, int]:
    if any(type(size) is not int or not 1 <= size <= 2**31 - 1 for size in (width_pixels, height_pixels)):
        raise ValueError(_INVALID)
    x, y, width, height = _region(region)
    context = Context(prec=28, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                      capitals=1, clamp=0, flags=[], traps=[InvalidOperation, DivisionByZero, Overflow])
    with localcontext(context):
        dx, dy, dw, dh = (Decimal(str(item)) for item in (x, y, width, height))
        bounds = (
            max(0, int((dx * width_pixels).to_integral_value(rounding=ROUND_FLOOR))),
            max(0, int((dy * height_pixels).to_integral_value(rounding=ROUND_FLOOR))),
            min(width_pixels, int(((dx + dw) * width_pixels).to_integral_value(rounding=ROUND_CEILING))),
            min(height_pixels, int(((dy + dh) * height_pixels).to_integral_value(rounding=ROUND_CEILING))),
        )
    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        raise ValueError(_EMPTY)
    return bounds


@dataclass(frozen=True)
class PdfRenderPlan:
    clip: tuple[float, float, float, float]
    first_bbox: tuple[int, int, int, int]
    final_bbox: tuple[int, int, int, int]
    matrix: tuple[float, float, float, float, float, float] | None
    dpi: int | None


def pdf_render_plan(
    *, cropbox: tuple[float, float, float, float],
    display_list_bounds: tuple[float, float, float, float],
    region: tuple[float, float, float, float],
) -> PdfRenderPlan:
    crop = _rectangle(cropbox)
    display = _rectangle(display_list_bounds)
    x, y, width, height = _region(region)
    try:
        import pymupdf as fitz
        if fitz.VersionBind != "1.28.2" or any(not callable(symbol) for symbol in (
            fitz.Rect, fitz.Matrix, fitz.JM_rect_from_py, fitz.JM_matrix_from_py,
            fitz.mupdf.FzRect, fitz.mupdf.fz_intersect_rect,
            fitz.mupdf.fz_transform_rect, fitz.mupdf.fz_round_rect,
        )):
            raise ValueError(_ENGINE)
    except (ImportError, AttributeError, OSError):
        raise ValueError(_ENGINE) from None

    def raster_bbox(clip, matrix):
        rect = fitz.mupdf.FzRect(*display)
        rect = fitz.mupdf.fz_intersect_rect(rect, fitz.JM_rect_from_py(clip))
        rect = fitz.mupdf.fz_transform_rect(rect, fitz.JM_matrix_from_py(matrix))
        if not all(math.isfinite(getattr(rect, key)) for key in ("x0", "y0", "x1", "y1")):
            raise ValueError(_INVALID)
        box = fitz.mupdf.fz_round_rect(rect)
        result = tuple(getattr(box, key) for key in ("x0", "y0", "x1", "y1"))
        if any(type(item) is not int or not -(2**31) <= item <= 2**31 - 1 for item in result):
            raise ValueError(_INVALID)
        if result[2] <= result[0] or result[3] <= result[1]:
            raise ValueError(_EMPTY)
        return result

    try:
        rect = fitz.Rect(*crop)
        clip = fitz.Rect(rect.x0 + x * rect.width, rect.y0 + y * rect.height,
                         rect.x0 + (x + width) * rect.width, rect.y0 + (y + height) * rect.height) & rect
        if not all(math.isfinite(item) for item in clip):
            raise ValueError(_INVALID)
        if clip.is_empty or clip.width < 0.5 or clip.height < 0.5:
            raise ValueError(_EMPTY)
        initial = fitz.Matrix(150 / 72, 150 / 72)
        first = raster_bbox(clip, initial)
        longest = max(first[2] - first[0], first[3] - first[1])
        if longest <= 1280:
            return PdfRenderPlan(tuple(clip), first, first, None, 150)
        scale = 1280 / float(longest)
        matrix = initial * fitz.Matrix(scale, scale)
        if not all(math.isfinite(item) for item in matrix):
            raise ValueError(_INVALID)
        return PdfRenderPlan(tuple(clip), first, raster_bbox(clip, matrix), tuple(matrix), None)
    except ValueError as error:
        if str(error) in (_INVALID, _EMPTY):
            raise
        raise ValueError(_INVALID) from None
    except (OverflowError, TypeError, RuntimeError):
        raise ValueError(_INVALID) from None
