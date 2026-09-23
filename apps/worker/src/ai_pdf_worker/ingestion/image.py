from __future__ import annotations

import warnings
import zlib
from hashlib import sha256
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from ai_pdf_api.modalities.image_ingestion import ImageNormalizationResult
from ai_pdf_api.modalities.ingestion import IngestionError

MAX_IMAGE_PIXELS = 64_000_000
EXIF_ORIENTATION_TAG = 274
FORMAT_MIME_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def normalize_image(
    payload: bytes,
    *,
    expected_mime_type: str,
    max_pixels: int = MAX_IMAGE_PIXELS,
) -> ImageNormalizationResult:
    expected_mime_type = expected_mime_type.lower()
    if expected_mime_type not in FORMAT_MIME_TYPES.values():
        raise IngestionError("image_mime_unsupported", "Image MIME type is not supported.")

    detected_mime_type = _detect_container_mime_type(payload)
    if detected_mime_type != expected_mime_type:
        raise IngestionError(
            "image_mime_mismatch",
            "Decoded image format does not match the declared MIME type.",
        )

    try:
        _validate_exact_container(payload, detected_mime_type)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(payload)) as candidate:
                _validate_decoded_header(candidate, expected_mime_type, max_pixels)
                candidate.verify()

            with Image.open(BytesIO(payload)) as decoded:
                _validate_decoded_header(decoded, expected_mime_type, max_pixels)
                orientation = decoded.getexif().get(EXIF_ORIENTATION_TAG, 1)
                if isinstance(orientation, bool) or not isinstance(orientation, int):
                    raise IngestionError(
                        "image_orientation_invalid",
                        "Image EXIF orientation is invalid.",
                    )
                if orientation not in range(1, 9):
                    raise IngestionError(
                        "image_orientation_invalid",
                        "Image EXIF orientation must be between 1 and 8.",
                    )
                decoded.load()
                oriented = ImageOps.exif_transpose(decoded)
                output_mode = (
                    "RGBA"
                    if "A" in oriented.getbands() or "transparency" in decoded.info
                    else "RGB"
                )
                canonical = oriented.convert(output_mode)
                canonical.info.clear()
                if oriented is not decoded:
                    oriented.close()
    except IngestionError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise IngestionError(
            "image_pixel_limit_exceeded",
            f"Image exceeds the {max_pixels} pixel processing limit.",
        ) from error
    except (OSError, SyntaxError, UnidentifiedImageError, ValueError, zlib.error) as error:
        raise IngestionError("image_decode_failed", "Image payload is corrupt or truncated.") from error

    try:
        output = BytesIO()
        canonical.save(output, format="PNG", optimize=False, compress_level=9)
        normalized_payload = output.getvalue()
        return ImageNormalizationResult(
            payload=normalized_payload,
            content_sha256=sha256(normalized_payload).hexdigest(),
            width_pixels=canonical.width,
            height_pixels=canonical.height,
            orientation_applied=True,
        )
    except OSError as error:
        raise IngestionError(
            "image_encode_failed",
            "Normalized image could not be encoded.",
        ) from error
    finally:
        canonical.close()


def _validate_decoded_header(
    image: Image.Image,
    expected_mime_type: str,
    max_pixels: int,
) -> None:
    decoded_mime_type = FORMAT_MIME_TYPES.get(image.format or "")
    if decoded_mime_type != expected_mime_type:
        raise IngestionError(
            "image_mime_mismatch",
            "Decoded image format does not match the declared MIME type.",
        )
    if getattr(image, "n_frames", 1) != 1:
        raise IngestionError(
            "image_animation_unsupported",
            "Animated images are not supported.",
        )
    width, height = image.size
    if width < 1 or height < 1:
        raise IngestionError("image_geometry_invalid", "Image dimensions are invalid.")
    if width * height > max_pixels:
        raise IngestionError(
            "image_pixel_limit_exceeded",
            f"Image exceeds the {max_pixels} pixel processing limit.",
        )


def _detect_container_mime_type(payload: bytes) -> str | None:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if (
        len(payload) >= 16
        and payload[:4] == b"RIFF"
        and payload[8:12] == b"WEBP"
        and payload[12:16] in {b"VP8 ", b"VP8L", b"VP8X"}
    ):
        return "image/webp"
    return None


def _validate_exact_container(payload: bytes, mime_type: str | None) -> None:
    if mime_type == "image/png":
        _validate_png_container(payload)
    elif mime_type == "image/jpeg":
        if _jpeg_end_offset(payload) != len(payload):
            raise ValueError("JPEG contains trailing bytes")
    elif mime_type == "image/webp":
        _validate_webp_container(payload)
    else:
        raise ValueError("Unsupported image container")


def _validate_png_container(payload: bytes) -> None:
    position = 8
    chunk_index = 0
    while position < len(payload):
        if position + 12 > len(payload):
            raise ValueError("Truncated PNG chunk")
        data_length = int.from_bytes(payload[position : position + 4], "big")
        chunk_type = payload[position + 4 : position + 8]
        chunk_end = position + 12 + data_length
        if chunk_end > len(payload):
            raise ValueError("Truncated PNG chunk data")
        chunk_data = payload[position + 8 : position + 8 + data_length]
        expected_crc = int.from_bytes(payload[position + 8 + data_length : chunk_end], "big")
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError("PNG chunk CRC mismatch")
        if chunk_index == 0 and (chunk_type != b"IHDR" or data_length != 13):
            raise ValueError("PNG must start with IHDR")
        position = chunk_end
        chunk_index += 1
        if chunk_type == b"IEND":
            if data_length != 0 or position != len(payload):
                raise ValueError("PNG IEND must terminate the payload")
            return
    raise ValueError("PNG is missing IEND")


def _validate_webp_container(payload: bytes) -> None:
    if len(payload) < 20 or int.from_bytes(payload[4:8], "little") + 8 != len(payload):
        raise ValueError("WebP RIFF size mismatch")
    position = 12
    chunks: list[tuple[bytes, bytes]] = []
    while position < len(payload):
        if position + 8 > len(payload):
            raise ValueError("Truncated WebP chunk")
        chunk_type = payload[position : position + 4]
        data_length = int.from_bytes(payload[position + 4 : position + 8], "little")
        chunk_end = position + 8 + data_length + (data_length % 2)
        if chunk_end > len(payload):
            raise ValueError("Truncated WebP chunk data")
        chunks.append((chunk_type, payload[position + 8 : position + 8 + data_length]))
        position = chunk_end
    if position != len(payload) or not chunks:
        raise ValueError("Invalid WebP chunk layout")

    chunk_types = [chunk_type for chunk_type, _data in chunks]
    if chunk_types[0] in {b"VP8 ", b"VP8L"}:
        if len(chunk_types) != 1:
            raise ValueError("Simple WebP must contain exactly one image bitstream")
        return
    if chunk_types[0] != b"VP8X":
        raise ValueError("WebP image chunk is missing")
    if chunk_types.count(b"VP8X") != 1:
        raise ValueError("Extended WebP must contain exactly one VP8X chunk")
    if b"ANIM" in chunk_types or b"ANMF" in chunk_types:
        raise IngestionError("image_animation_unsupported", "Animated images are not supported.")

    vp8x_data = chunks[0][1]
    if len(vp8x_data) != 10:
        raise ValueError("Invalid VP8X chunk length")
    feature_flags = vp8x_data[0]
    if feature_flags & 0x02:
        raise IngestionError("image_animation_unsupported", "Animated images are not supported.")
    if feature_flags & 0xC1:
        raise ValueError("VP8X reserved feature bits must be zero")
    if vp8x_data[1:4] != b"\x00\x00\x00":
        raise ValueError("VP8X reserved bytes must be zero")

    allowed_types = {b"VP8X", b"ICCP", b"ALPH", b"VP8 ", b"VP8L", b"EXIF", b"XMP "}
    if any(chunk_type not in allowed_types for chunk_type in chunk_types):
        raise ValueError("Extended WebP contains an unsupported chunk")
    if any(chunk_types.count(chunk_type) > 1 for chunk_type in allowed_types):
        raise ValueError("Extended WebP contains duplicate chunks")
    image_types = [chunk_type for chunk_type in chunk_types if chunk_type in {b"VP8 ", b"VP8L"}]
    if len(image_types) != 1:
        raise ValueError("Extended WebP must contain exactly one image bitstream")
    if b"ALPH" in chunk_types and image_types[0] != b"VP8 ":
        raise ValueError("ALPH is only valid before a VP8 bitstream")

    image_chunk = next(data for chunk_type, data in chunks if chunk_type == image_types[0])
    has_alpha = b"ALPH" in chunk_types or (
        image_types[0] == b"VP8L" and _vp8l_uses_alpha(image_chunk)
    )
    if bool(feature_flags & 0x10) != has_alpha:
        raise ValueError("VP8X alpha flag does not match the image bitstream")

    order = {b"VP8X": 0, b"ICCP": 1, b"ALPH": 2, b"VP8 ": 3, b"VP8L": 3, b"EXIF": 4, b"XMP ": 5}
    if [order[chunk_type] for chunk_type in chunk_types] != sorted(
        order[chunk_type] for chunk_type in chunk_types
    ):
        raise ValueError("Extended WebP chunks are out of order")
    if bool(feature_flags & 0x20) != (b"ICCP" in chunk_types):
        raise ValueError("VP8X ICC profile flag does not match chunks")
    if bool(feature_flags & 0x08) != (b"EXIF" in chunk_types):
        raise ValueError("VP8X EXIF flag does not match chunks")
    if bool(feature_flags & 0x04) != (b"XMP " in chunk_types):
        raise ValueError("VP8X XMP flag does not match chunks")


def _vp8l_uses_alpha(payload: bytes) -> bool:
    if len(payload) < 5 or payload[0] != 0x2F:
        raise ValueError("Invalid VP8L bitstream header")
    header_bits = int.from_bytes(payload[1:5], "little")
    if header_bits >> 29:
        raise ValueError("Unsupported VP8L bitstream version")
    return bool(header_bits & (1 << 28))


def _jpeg_end_offset(payload: bytes) -> int:
    if not payload.startswith(b"\xff\xd8"):
        raise ValueError("JPEG SOI is missing")
    position = 2
    in_scan = False
    while position < len(payload):
        if in_scan:
            while position < len(payload) and payload[position] != 0xFF:
                position += 1
            if position >= len(payload):
                break
            marker_start = position
            while position < len(payload) and payload[position] == 0xFF:
                position += 1
            if position >= len(payload):
                break
            marker = payload[position]
            position += 1
            if marker == 0x00 or 0xD0 <= marker <= 0xD7:
                continue
            if marker == 0xD9:
                return position
            in_scan = False
            position = marker_start
            continue

        if payload[position] != 0xFF:
            raise ValueError("JPEG marker prefix is missing")
        while position < len(payload) and payload[position] == 0xFF:
            position += 1
        if position >= len(payload):
            break
        marker = payload[position]
        position += 1
        if marker == 0xD9:
            return position
        if marker == 0xD8:
            raise ValueError("Unexpected JPEG SOI marker")
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if position + 2 > len(payload):
            raise ValueError("Truncated JPEG segment")
        segment_length = int.from_bytes(payload[position : position + 2], "big")
        if segment_length < 2 or position + segment_length > len(payload):
            raise ValueError("Invalid JPEG segment length")
        position += segment_length
        if marker == 0xDA:
            in_scan = True
    raise ValueError("JPEG EOI is missing")
