from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ai_pdf_api.db.base import Base
from ai_pdf_api.modalities.html import (
    HTML_NORMALIZATION_VERSION,
    HTML_PARSER_VERSION,
    HTML_SANITIZER_VERSION,
    sanitize_html,
    text_sha256,
)
from ai_pdf_api.modalities.ingestion import IngestionError
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    EvidenceLocator,
    HtmlBlock,
    HtmlLocatorDetail,
    HtmlNormalizedContent,
)
from ai_pdf_worker.html_ingestion import HtmlIngestionAdapter
from ai_pdf_worker.html_parse import parse_html_document

HTML_FIXTURE = """<!DOCTYPE html>
<html>
  <head>
    <script>alert('xss')</script>
    <style>body { display: none }</style>
  </head>
  <body>
    <h1 onclick="alert(1)">Intro</h1>
    <p>Hello world paragraph.</p>
    <h2>Nested</h2>
    <ul>
      <li>first item</li>
      <li>nested item</li>
    </ul>
    <pre><code>print("hi")</code></pre>
    <blockquote>quoted text</blockquote>
    <table>
      <tr><th>Col A</th><th>Col B</th></tr>
      <tr><td>1</td><td>2</td></tr>
    </table>
    <img src="https://evil.example/track.png" alt="remote">
    <a href="javascript:alert(1)">nope</a>
  </body>
</html>
"""


class StaticEmbeddingProvider:
    provider = "test-embedding"
    model = "test-embedding-model"
    dimensions = 3
    version = "test-embedding-v1"


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


def _html_config() -> dict[str, object]:
    return {
        "htmlFormat": "html",
        "htmlParserVersion": HTML_PARSER_VERSION,
        "htmlSanitizerVersion": HTML_SANITIZER_VERSION,
        "htmlNormalizationVersion": HTML_NORMALIZATION_VERSION,
        "chunkSize": 1200,
        "embeddingProvider": StaticEmbeddingProvider.provider,
        "embeddingModel": StaticEmbeddingProvider.model,
        "embeddingDimensions": StaticEmbeddingProvider.dimensions,
        "embeddingVersion": StaticEmbeddingProvider.version,
    }


def _make_asset(db: Session, *, payload: bytes) -> Asset:
    now = datetime.now(UTC)
    asset = Asset(
        workspace_id="workspace-html",
        created_by_user_id="user-html",
        asset_kind="html",
        title="HTML note",
        source_filename="note.html",
        object_key="workspaces/workspace-html/assets/source/original.html",
        mime_type="text/html",
        byte_size=len(payload),
        source_sha256=sha256(payload).hexdigest(),
        status="parsing",
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(asset)
    db.flush()
    return asset


def test_parse_html_strips_active_content_and_builds_stable_blocks() -> None:
    payload = HTML_FIXTURE.encode("utf-8")
    first = parse_html_document(payload)
    second = parse_html_document(payload)
    assert first.normalized_text == second.normalized_text
    assert first.content_sha256 == second.content_sha256
    assert "<script" not in first.sanitized_html.lower()
    assert "javascript:" not in first.sanitized_html.lower()
    assert "onclick" not in first.sanitized_html.lower()
    kinds = {block.block_kind for block in first.blocks}
    assert "heading" in kinds
    assert "paragraph" in kinds
    assert "list_item" in kinds
    assert "code_block" in kinds
    assert "quote" in kinds
    assert "table" in kinds
    intro = next(block for block in first.blocks if block.text == "Intro")
    assert intro.block_kind == "heading" and intro.heading_level == 1
    nested = next(block for block in first.blocks if block.text == "nested item")
    assert nested.heading_path == ("Intro", "Nested")
    for block in first.blocks:
        assert first.normalized_text[block.char_start : block.char_end] == block.text


def test_parse_rejects_invalid_encoding_bytes_and_mime() -> None:
    with pytest.raises(IngestionError) as encoding:
        parse_html_document(b"\xff\xfe not utf8")
    assert encoding.value.code == "asset_encoding_unsupported"
    with pytest.raises(IngestionError) as binary:
        parse_html_document(b"%PDF-1.7 fake")
    assert binary.value.code == "asset_bytes_invalid"
    with pytest.raises(IngestionError) as mime:
        parse_html_document(b"<p>ok</p>", mime_type="text/markdown")
    assert mime.value.code == "asset_mime_mismatch"


def test_html_adapter_persists_sanitized_blocks_and_html_anchor() -> None:
    engine = _engine()
    Base.metadata.create_all(bind=engine)
    payload = HTML_FIXTURE.encode("utf-8")
    now = datetime.now(UTC)
    with Session(engine) as db:
        asset = _make_asset(db, payload=payload)
        result = HtmlIngestionAdapter().ingest(
            db,
            asset=asset,
            payload=payload,
            processing_generation=1,
            config_snapshot=_html_config(),
            created_at=now,
        )
        db.flush()
        assert len(result.generated_objects) == 2
        kinds = {
            row.representation_kind
            for row in db.scalars(
                select(AssetRepresentation).where(AssetRepresentation.asset_id == asset.id)
            )
        }
        assert kinds == {"html_source", "html_normalized", "html_sanitized"}
        normalized = db.scalar(select(HtmlNormalizedContent))
        assert normalized is not None
        assert "<script" not in normalized.sanitized_html.lower()
        assert sanitize_html(normalized.sanitized_html) == normalized.sanitized_html
        blocks = list(db.scalars(select(HtmlBlock).order_by(HtmlBlock.block_order)))
        assert blocks
        locators = list(db.scalars(select(EvidenceLocator)))
        assert locators
        assert all(item.locator_kind == "html_anchor" for item in locators)
        detail = db.get(HtmlLocatorDetail, locators[0].id)
        assert detail is not None
        assert detail.normalization_version == HTML_NORMALIZATION_VERSION
        units = list(db.scalars(select(ContentUnit)))
        assert units
        assert all(unit.unit_kind == "html_text_chunk" for unit in units)
        assert all(text_sha256(unit.text_content) for unit in units)


def test_html_adapter_rejects_config_mismatch() -> None:
    engine = _engine()
    Base.metadata.create_all(bind=engine)
    payload = HTML_FIXTURE.encode("utf-8")
    with Session(engine) as db:
        asset = _make_asset(db, payload=payload)
        snapshot = _html_config()
        snapshot["htmlSanitizerVersion"] = "html-sanitizer-v0"
        with pytest.raises(IngestionError) as error:
            HtmlIngestionAdapter().ingest(
                db,
                asset=asset,
                payload=payload,
                processing_generation=1,
                config_snapshot=snapshot,
                created_at=datetime.now(UTC),
            )
        assert error.value.code == "html_configuration_mismatch"
