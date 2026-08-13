from datetime import UTC, datetime
from hashlib import sha256

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ai_pdf_api.db.base import Base
from ai_pdf_api.modalities.docx import (
    DOCX_NORMALIZATION_VERSION,
    DOCX_PARSER_VERSION,
    build_minimal_docx_bytes,
)
from ai_pdf_api.modalities.ingestion import IngestionError
from ai_pdf_api.modalities.office_ooxml import DOCX_MIME, PPTX_MIME, XLSX_MIME
from ai_pdf_api.modalities.pptx import PPTX_PARSER_VERSION, build_minimal_pptx_bytes
from ai_pdf_api.modalities.xlsx import XLSX_PARSER_VERSION, build_minimal_xlsx_bytes
from ai_pdf_api.models import (
    Asset,
    ContentUnit,
    DocxBlock,
    DocxLocatorDetail,
    EvidenceLocator,
    PptxLocatorDetail,
    XlsxLocatorDetail,
)
from ai_pdf_worker.docx_ingestion import DocxIngestionAdapter
from ai_pdf_worker.pptx_ingestion import PptxIngestionAdapter
from ai_pdf_worker.xlsx_ingestion import XlsxIngestionAdapter
import ai_pdf_worker.main as worker_main


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


def _make_asset(
    db: Session,
    *,
    payload: bytes,
    mime_type: str,
    asset_kind: str,
    filename: str,
) -> Asset:
    now = datetime.now(UTC)
    asset = Asset(
        workspace_id="workspace-office",
        created_by_user_id="user-office",
        asset_kind=asset_kind,
        title=filename,
        source_filename=filename,
        object_key=f"workspaces/workspace-office/assets/source/{filename}",
        mime_type=mime_type,
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


def test_docx_ingest_writes_blocks_locators_and_retrieval_units() -> None:
    payload = build_minimal_docx_bytes(
        paragraphs=[("Heading1", "Intro"), ("Normal", "Hello world paragraph.")]
    )
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        asset = _make_asset(
            db, payload=payload, mime_type=DOCX_MIME, asset_kind="docx", filename="note.docx"
        )
        result = DocxIngestionAdapter().ingest(
            db,
            asset=asset,
            payload=payload,
            processing_generation=1,
            config_snapshot={
                "docxParserVersion": DOCX_PARSER_VERSION,
                "docxNormalizationVersion": DOCX_NORMALIZATION_VERSION,
                "chunkSize": 1200,
            },
            created_at=datetime.now(UTC),
        )
        db.commit()
        blocks = list(db.scalars(select(DocxBlock).order_by(DocxBlock.block_order)))
        units = list(db.scalars(select(ContentUnit).order_by(ContentUnit.unit_order)))
        locators = list(db.scalars(select(EvidenceLocator)))
        details = list(db.scalars(select(DocxLocatorDetail)))
        assert [block.block_kind for block in blocks] == ["heading", "paragraph"]
        assert units
        assert all(unit.unit_kind == "docx_text_chunk" for unit in units)
        assert {locator.locator_kind for locator in locators} == {"docx_anchor"}
        assert details
        assert all(detail.normalization_version == DOCX_NORMALIZATION_VERSION for detail in details)
        assert result.generated_objects[0].content_sha256


def test_docx_ingest_rejects_macros() -> None:
    payload = build_minimal_docx_bytes(include_macro=True)
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        asset = _make_asset(
            db, payload=payload, mime_type=DOCX_MIME, asset_kind="docx", filename="macro.docx"
        )
        with pytest.raises(IngestionError) as error:
            DocxIngestionAdapter().ingest(
                db,
                asset=asset,
                payload=payload,
                processing_generation=1,
                config_snapshot={
                    "docxParserVersion": DOCX_PARSER_VERSION,
                    "docxNormalizationVersion": DOCX_NORMALIZATION_VERSION,
                    "chunkSize": 1200,
                },
                created_at=datetime.now(UTC),
            )
        assert error.value.code == "office_macros_unsupported"


def test_xlsx_and_pptx_ingest_typed_locators() -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        xlsx_payload = build_minimal_xlsx_bytes()
        xlsx_asset = _make_asset(
            db,
            payload=xlsx_payload,
            mime_type=XLSX_MIME,
            asset_kind="xlsx",
            filename="book.xlsx",
        )
        XlsxIngestionAdapter().ingest(
            db,
            asset=xlsx_asset,
            payload=xlsx_payload,
            processing_generation=1,
            config_snapshot={"xlsxParserVersion": XLSX_PARSER_VERSION},
            created_at=datetime.now(UTC),
        )
        pptx_payload = build_minimal_pptx_bytes()
        pptx_asset = _make_asset(
            db,
            payload=pptx_payload,
            mime_type=PPTX_MIME,
            asset_kind="pptx",
            filename="deck.pptx",
        )
        PptxIngestionAdapter().ingest(
            db,
            asset=pptx_asset,
            payload=pptx_payload,
            processing_generation=1,
            config_snapshot={"pptxParserVersion": PPTX_PARSER_VERSION},
            created_at=datetime.now(UTC),
        )
        db.commit()
        xlsx_details = list(db.scalars(select(XlsxLocatorDetail)))
        pptx_details = list(db.scalars(select(PptxLocatorDetail)))
        assert {row.start_cell for row in xlsx_details} == {"A1", "B1"}
        assert pptx_details[0].slide_index == 1
        assert pptx_details[0].displayed_text == "Quarterly review"


def test_worker_registers_separate_office_adapters_without_vague_kind() -> None:
    kinds = worker_main.INGESTION_ADAPTERS.asset_kinds
    assert "office" not in kinds
    assert {"docx", "xlsx", "pptx"}.issubset(kinds)
