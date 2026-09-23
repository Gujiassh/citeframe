from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ai_pdf_api.modalities.ingestion import IngestionError
from ai_pdf_worker.ingestion.image import (
    EXIF_ORIENTATION_TAG,
    MAX_IMAGE_PIXELS,
    _validate_decoded_header,
    normalize_image,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPOSITORY_ROOT / "docs" / "fixtures" / "evidence-contract"
IMAGE_MATRIX_MANIFEST = FIXTURE_ROOT / "image-ingestion-matrix-fixture.json"


def _base_image(*, mode: str = "RGB") -> Image.Image:
    image = Image.new("RGBA", (12, 8), (18, 24, 32, 255))
    pixels = image.load()
    assert pixels is not None
    for y in range(image.height):
        for x in range(image.width):
            pixels[x, y] = (
                (x * 19 + y * 7) % 256,
                (x * 5 + y * 31) % 256,
                (x * 37 + y * 11) % 256,
                80 + ((x * 13 + y * 17) % 176),
            )
    return image.convert(mode)


def _encode(
    image: Image.Image,
    image_format: str,
    *,
    orientation: int | None = None,
    save_all: bool = False,
    append_images: list[Image.Image] | None = None,
) -> bytes:
    output = BytesIO()
    options: dict[str, object] = {}
    if image_format == "JPEG":
        options.update(quality=95, subsampling=0, optimize=False, progressive=False)
    elif image_format == "PNG":
        options.update(optimize=False, compress_level=9)
    elif image_format == "WEBP":
        options.update(lossless=True, method=6, exact=True)
    if orientation is not None:
        exif = Image.Exif()
        exif[EXIF_ORIENTATION_TAG] = orientation
        options["exif"] = exif
    if save_all:
        options.update(save_all=True, append_images=append_images or [], duration=100, loop=0)
    image.save(output, image_format, **options)
    return output.getvalue()


def _decoded_rgb(payload: bytes) -> np.ndarray:
    with Image.open(BytesIO(payload)) as image:
        image.load()
        return np.asarray(image.convert("RGB"))


def _encode_lossy_webp(image: Image.Image, *, orientation: int | None = None) -> bytes:
    output = BytesIO()
    options: dict[str, object] = {"quality": 90, "method": 6, "exact": True}
    if orientation is not None:
        exif = Image.Exif()
        exif[EXIF_ORIENTATION_TAG] = orientation
        options["exif"] = exif
    image.save(output, "WEBP", **options)
    return output.getvalue()


def _pixel_sha256(payload: bytes) -> str:
    with Image.open(BytesIO(payload)) as image:
        image.load()
        rgb = image.convert("RGB")
    header = f"RGB:{rgb.width}x{rgb.height}\0".encode("ascii")
    return hashlib.sha256(header + rgb.tobytes()).hexdigest()


def _webp_chunks(payload: bytes) -> list[bytes]:
    chunks: list[bytes] = []
    position = 12
    while position < len(payload):
        data_length = int.from_bytes(payload[position + 4 : position + 8], "little")
        chunk_end = position + 8 + data_length + (data_length % 2)
        chunks.append(payload[position:chunk_end])
        position = chunk_end
    return chunks


def _webp_from_chunks(chunks: list[bytes]) -> bytes:
    body = b"".join(chunks)
    return b"RIFF" + (len(body) + 4).to_bytes(4, "little") + b"WEBP" + body


def _replace_webp_chunk_data(chunk: bytes, data: bytes) -> bytes:
    chunk_type = chunk[:4]
    padding = b"\x00" if len(data) % 2 else b""
    return chunk_type + len(data).to_bytes(4, "little") + data + padding


def _expected_orientation(pixels: np.ndarray, orientation: int) -> np.ndarray:
    if orientation == 1:
        return pixels
    if orientation == 2:
        return pixels[:, ::-1]
    if orientation == 3:
        return pixels[::-1, ::-1]
    if orientation == 4:
        return pixels[::-1]
    if orientation == 5:
        return np.transpose(pixels, (1, 0, 2))
    if orientation == 6:
        return np.rot90(pixels, 3)
    if orientation == 7:
        return np.transpose(pixels, (1, 0, 2))[::-1, ::-1]
    if orientation == 8:
        return np.rot90(pixels, 1)
    raise AssertionError(f"Unsupported test orientation: {orientation}")


@pytest.mark.parametrize("orientation", range(1, 9))
def test_jpeg_exif_orientations_match_independent_pixel_oracle(orientation: int) -> None:
    source = _encode(_base_image(mode="RGB"), "JPEG", orientation=orientation)
    source_snapshot = bytes(source)
    decoded_source = _decoded_rgb(source)

    result = normalize_image(source, expected_mime_type="image/jpeg")

    assert source == source_snapshot
    assert result.orientation_applied is True
    assert (result.width_pixels, result.height_pixels) == (
        (12, 8) if orientation <= 4 else (8, 12)
    )
    assert np.array_equal(_decoded_rgb(result.payload), _expected_orientation(decoded_source, orientation))
    with Image.open(BytesIO(result.payload)) as normalized:
        assert normalized.format == "PNG"
        assert normalized.getexif().get(EXIF_ORIENTATION_TAG) is None
    assert normalize_image(source, expected_mime_type="image/jpeg") == result


def test_image_ingestion_matrix_matches_frozen_object_and_pixel_hashes() -> None:
    manifest = json.loads(IMAGE_MATRIX_MANIFEST.read_text(encoding="utf-8"))

    for case in manifest["cases"]:
        source = (FIXTURE_ROOT / case["filename"]).read_bytes()
        assert hashlib.sha256(source).hexdigest() == case["sourceSha256"]

        result = normalize_image(source, expected_mime_type=case["declaredMimeType"])

        assert (result.width_pixels, result.height_pixels) == (
            case["normalizedWidthPixels"],
            case["normalizedHeightPixels"],
        )
        assert result.orientation_applied is case["orientationApplied"]
        assert result.content_sha256 == case["normalizedObjectSha256"]
        assert _pixel_sha256(result.payload) == case["normalizedPixelSha256"]


@pytest.mark.parametrize(
    ("image_format", "mime_type"),
    [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")],
)
def test_static_supported_formats_produce_canonical_png(
    image_format: str,
    mime_type: str,
) -> None:
    source = _base_image(mode="RGBA" if image_format != "JPEG" else "RGB")
    payload = _encode(source, image_format)

    result = normalize_image(payload, expected_mime_type=mime_type)

    with Image.open(BytesIO(result.payload)) as normalized:
        assert normalized.format == "PNG"
        assert normalized.size == source.size
        assert normalized.mode == ("RGBA" if image_format != "JPEG" else "RGB")


@pytest.mark.parametrize(
    ("image_format", "declared_mime_type"),
    [
        ("PNG", "image/jpeg"),
        ("PNG", "image/webp"),
        ("JPEG", "image/png"),
        ("JPEG", "image/webp"),
        ("WEBP", "image/png"),
        ("WEBP", "image/jpeg"),
    ],
)
def test_full_decode_rejects_cross_mime_payloads(
    image_format: str,
    declared_mime_type: str,
) -> None:
    payload = _encode(_base_image(mode="RGB"), image_format)

    with pytest.raises(IngestionError) as captured:
        normalize_image(payload, expected_mime_type=declared_mime_type)

    assert captured.value.code == "image_mime_mismatch"


@pytest.mark.parametrize(
    ("image_format", "mime_type"),
    [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")],
)
def test_corrupt_truncated_and_appended_payloads_fail_closed(
    image_format: str,
    mime_type: str,
) -> None:
    payload = _encode(_base_image(mode="RGB"), image_format)

    for invalid in (payload[:-5], payload + b"polyglot-trailer"):
        with pytest.raises(IngestionError) as captured:
            normalize_image(invalid, expected_mime_type=mime_type)
        assert captured.value.code == "image_decode_failed"


@pytest.mark.parametrize("orientation", [0, 9])
def test_invalid_exif_orientation_fails_closed(orientation: int) -> None:
    payload = _encode(_base_image(mode="RGB"), "JPEG", orientation=orientation)

    with pytest.raises(IngestionError) as captured:
        normalize_image(payload, expected_mime_type="image/jpeg")

    assert captured.value.code == "image_orientation_invalid"


def test_animated_webp_is_rejected() -> None:
    payload = _encode(
        _base_image(mode="RGB"),
        "WEBP",
        save_all=True,
        append_images=[Image.new("RGB", (12, 8), "white")],
    )

    with pytest.raises(IngestionError) as captured:
        normalize_image(payload, expected_mime_type="image/webp")

    assert captured.value.code == "image_animation_unsupported"


def test_webp_rejects_duplicate_image_bitstreams() -> None:
    source = _encode(_base_image(mode="RGB"), "WEBP")
    chunks = _webp_chunks(source)
    assert len(chunks) == 1 and chunks[0].startswith(b"VP8L")
    duplicate = _webp_from_chunks([chunks[0], chunks[0]])

    with pytest.raises(IngestionError) as captured:
        normalize_image(duplicate, expected_mime_type="image/webp")

    assert captured.value.code == "image_decode_failed"


def test_webp_rejects_duplicate_vp8x_and_illegal_static_chunk_order() -> None:
    source = _encode(_base_image(mode="RGB"), "WEBP", orientation=1)
    chunks = _webp_chunks(source)
    assert [chunk[:4] for chunk in chunks] == [b"VP8X", b"VP8L", b"EXIF"]
    invalid_payloads = (
        _webp_from_chunks([chunks[0], chunks[0], *chunks[1:]]),
        _webp_from_chunks([chunks[0], chunks[2], chunks[1]]),
    )

    for invalid in invalid_payloads:
        with pytest.raises(IngestionError) as captured:
            normalize_image(invalid, expected_mime_type="image/webp")
        assert captured.value.code == "image_decode_failed"


@pytest.mark.parametrize("mode", ["RGB", "RGBA"])
def test_webp_rejects_nonzero_vp8x_reserved_bytes(mode: str) -> None:
    source = _encode(_base_image(mode=mode), "WEBP", orientation=1)
    chunks = _webp_chunks(source)
    assert chunks[0].startswith(b"VP8X")
    vp8x_data_length = int.from_bytes(chunks[0][4:8], "little")
    vp8x_data = bytearray(chunks[0][8 : 8 + vp8x_data_length])
    vp8x_data[1] = 1
    invalid = _webp_from_chunks(
        [_replace_webp_chunk_data(chunks[0], bytes(vp8x_data)), *chunks[1:]]
    )

    with pytest.raises(IngestionError) as captured:
        normalize_image(invalid, expected_mime_type="image/webp")

    assert captured.value.code == "image_decode_failed"


@pytest.mark.parametrize(("mode", "expected_alpha"), [("RGB", False), ("RGBA", True)])
def test_webp_rejects_vp8x_alpha_flag_mismatch(mode: str, expected_alpha: bool) -> None:
    source = _encode(_base_image(mode=mode), "WEBP", orientation=1)
    chunks = _webp_chunks(source)
    assert chunks[0].startswith(b"VP8X")
    vp8x_data_length = int.from_bytes(chunks[0][4:8], "little")
    vp8x_data = bytearray(chunks[0][8 : 8 + vp8x_data_length])
    assert bool(vp8x_data[0] & 0x10) is expected_alpha
    vp8x_data[0] ^= 0x10
    invalid = _webp_from_chunks(
        [_replace_webp_chunk_data(chunks[0], bytes(vp8x_data)), *chunks[1:]]
    )

    with pytest.raises(IngestionError) as captured:
        normalize_image(invalid, expected_mime_type="image/webp")

    assert captured.value.code == "image_decode_failed"


@pytest.mark.parametrize("mode", ["RGB", "RGBA"])
def test_static_lossy_webp_rgb_and_alpha_are_accepted(mode: str) -> None:
    source = _encode_lossy_webp(_base_image(mode=mode), orientation=1)
    chunk_types = [chunk[:4] for chunk in _webp_chunks(source)]
    assert chunk_types == (
        [b"VP8X", b"VP8 ", b"EXIF"]
        if mode == "RGB"
        else [b"VP8X", b"ALPH", b"VP8 ", b"EXIF"]
    )

    result = normalize_image(source, expected_mime_type="image/webp")

    with Image.open(BytesIO(result.payload)) as normalized:
        assert normalized.mode == mode


def test_pixel_limit_is_enforced_before_decode_work() -> None:
    payload = _encode(_base_image(mode="RGB"), "PNG")

    with pytest.raises(IngestionError) as captured:
        normalize_image(payload, expected_mime_type="image/png", max_pixels=95)

    assert captured.value.code == "image_pixel_limit_exceeded"


def test_default_pixel_limit_allows_exact_boundary_and_rejects_one_row_more() -> None:
    assert MAX_IMAGE_PIXELS == 64_000_000
    exact = Image.new("1", (8_000, 8_000))
    above = Image.new("1", (8_000, 8_001))
    exact.format = "PNG"
    above.format = "PNG"
    try:
        _validate_decoded_header(exact, "image/png", MAX_IMAGE_PIXELS)
        with pytest.raises(IngestionError) as captured:
            _validate_decoded_header(above, "image/png", MAX_IMAGE_PIXELS)
        assert captured.value.code == "image_pixel_limit_exceeded"
    finally:
        exact.close()
        above.close()


def test_canonical_mode_preserves_alpha_and_converts_cmyk() -> None:
    rgba = normalize_image(
        _encode(_base_image(mode="RGBA"), "PNG"),
        expected_mime_type="image/png",
    )
    cmyk = normalize_image(
        _encode(_base_image(mode="CMYK"), "JPEG"),
        expected_mime_type="image/jpeg",
    )

    with Image.open(BytesIO(rgba.payload)) as rgba_image:
        assert rgba_image.mode == "RGBA"
    with Image.open(BytesIO(cmyk.payload)) as cmyk_image:
        assert cmyk_image.mode == "RGB"
