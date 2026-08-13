from ai_pdf_api.modalities.html import (
    detect_html_mime_type,
    sanitize_html,
    validate_html_upload_payload,
)
from ai_pdf_api.modalities.registry import (
    HTML_MODULE,
    build_html_ready_registry,
    build_production_registry,
)


def test_sanitizer_strips_script_style_and_event_handlers() -> None:
    dirty = (
        "<h1 onclick=\"alert(1)\">Title</h1>"
        "<p>Hello <script>alert(1)</script>world</p>"
        "<style>body{display:none}</style>"
        "<a href=\"javascript:alert(1)\">bad</a>"
        "<a href=\"https://example.com\">ok</a>"
        "<img src=\"https://evil.example/x.png\" alt=\"remote\">"
        "<img src=\"data:image/png;base64,AAAA\" alt=\"local\">"
        "<p onmouseover=\"steal()\">safe text</p>"
    )
    cleaned = sanitize_html(dirty)
    lowered = cleaned.lower()
    assert "<script" not in lowered
    assert "javascript:" not in lowered
    assert "onclick" not in lowered
    assert "onmouseover" not in lowered
    assert "<style" not in lowered
    assert "https://evil.example" not in cleaned
    assert "https://example.com" in cleaned
    assert "data:image/png;base64,AAAA" in cleaned
    assert "Title" in cleaned
    assert "Hello" in cleaned
    assert "world" in cleaned


def test_sanitizer_strips_od_b5_forbidden_tags_and_nested_children() -> None:
    dirty = (
        "<p>before</p>"
        "<iframe src=\"https://evil.example/frame\">nested text</iframe>"
        "<object data=\"x.swf\"><p>object child</p></object>"
        "<embed src=\"x.swf\">"
        "<svg onload=\"alert(1)\"><text>svg text</text></svg>"
        "<math><mi>x</mi></math>"
        "<form action=\"/steal\"><input name=\"q\" value=\"1\"><p>form child</p></form>"
        "<p>after</p>"
    )
    cleaned = sanitize_html(dirty)
    lowered = cleaned.lower()
    for token in ("iframe", "object", "embed", "svg", "math", "form", "input", "onload"):
        assert token not in lowered
    assert "nested text" not in cleaned
    assert "object child" not in cleaned
    assert "svg text" not in cleaned
    assert "form child" not in cleaned
    assert "before" in cleaned
    assert "after" in cleaned


def test_sanitizer_rejects_protocol_relative_and_unsafe_href_img() -> None:
    dirty = (
        "<a href=\"//evil.example/path\">proto-rel</a>"
        "<a href=\"vbscript:msgbox(1)\">vbs</a>"
        "<a href=\"data:text/html,hi\">data-href</a>"
        "<a href=\"https://ok.example\">ok</a>"
        "<img src=\"//evil.example/x.png\" alt=\"proto-img\">"
        "<img src=\"data:image/svg+xml;base64,PHN2Zz4=\" alt=\"svg-data\">"
        "<img srcset=\"https://evil.example/a.png 1x\" src=\"relative.png\" alt=\"srcset\">"
        "<p style=\"color:red\" srcdoc=\"<script>1</script>\">styled</p>"
    )
    cleaned = sanitize_html(dirty)
    lowered = cleaned.lower()
    assert "//evil.example" not in cleaned
    assert "vbscript:" not in lowered
    assert "data:text/html" not in lowered
    assert "data:image/svg+xml" not in lowered
    assert "srcset=" not in lowered
    assert "style=" not in lowered
    assert "srcdoc=" not in lowered
    assert "https://ok.example" in cleaned
    assert 'src="relative.png"' in cleaned
    assert "proto-rel" in cleaned
    assert "styled" in cleaned


def test_upload_probe_accepts_html_and_rejects_binary() -> None:
    assert detect_html_mime_type(b"<!DOCTYPE html><p>Hi</p>") == "text/html"
    assert detect_html_mime_type(b"%PDF-1.7") is None
    validate_html_upload_payload(b"<p>ok</p>")
    try:
        validate_html_upload_payload(b"")
        raise AssertionError("empty payload must fail")
    except ValueError:
        pass
    try:
        validate_html_upload_payload(b"\x00not-html")
        raise AssertionError("NUL payload must fail")
    except ValueError:
        pass


def test_production_registry_enables_html_after_s0() -> None:
    production = build_production_registry()
    assert "html" in production.asset_kinds
    assert "html" in production.enabled_asset_kinds
    inspected = production.inspect_upload("text/html", b"<html><p>Hi</p></html>")
    assert inspected.asset_kind == "html"
    ready = build_html_ready_registry()
    assert ready.get("html") is HTML_MODULE
