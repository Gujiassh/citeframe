"""Office ModalityModule definitions.

These modules are owned by the office lane. S0 registers them in
``build_production_registry`` together with catalog rows.
"""

from __future__ import annotations

from ai_pdf_api.modalities.docx import (
    detect_docx_mime_type,
    validate_docx_upload_payload,
)
from ai_pdf_api.modalities.office_ooxml import DOCX_MIME, PPTX_MIME, XLSX_MIME
from ai_pdf_api.modalities.pptx import (
    detect_pptx_mime_type,
    validate_pptx_upload_payload,
)
from ai_pdf_api.modalities.registry import (
    ModalityModule,
    RetrievalChannelRegistration,
    TypeRegistration,
)
from ai_pdf_api.modalities.xlsx import (
    detect_xlsx_mime_type,
    validate_xlsx_upload_payload,
)

DOCX_MODULE = ModalityModule(
    asset_kind="docx",
    contract_version=1,
    enabled=True,
    supported_mime_types=frozenset({DOCX_MIME}),
    byte_inspector=detect_docx_mime_type,
    representation_types=(
        TypeRegistration("docx_source"),
        TypeRegistration("docx_normalized"),
    ),
    content_unit_types=(TypeRegistration("docx_text_chunk"),),
    locator_types=(TypeRegistration("docx_anchor", detail_family="record"),),
    retrieval_channels=(
        RetrievalChannelRegistration(
            kind="text",
            embedding_space="text",
            type_signatures=frozenset(
                {("docx_text_chunk", "docx_normalized", "docx_anchor")}
            ),
        ),
    ),
    metrics_namespace="docx",
    ingestion_config_snapshot=lambda: {
        "docxParserVersion": "docx-parser-v1",
        "docxNormalizationVersion": "docx-normalization-v1",
    },
    full_payload_validator=validate_docx_upload_payload,
)

XLSX_MODULE = ModalityModule(
    asset_kind="xlsx",
    contract_version=1,
    enabled=True,
    supported_mime_types=frozenset({XLSX_MIME}),
    byte_inspector=detect_xlsx_mime_type,
    representation_types=(
        TypeRegistration("xlsx_source"),
        TypeRegistration("xlsx_normalized"),
    ),
    content_unit_types=(TypeRegistration("xlsx_cell_text"),),
    locator_types=(TypeRegistration("xlsx_range", detail_family="record"),),
    retrieval_channels=(
        RetrievalChannelRegistration(
            kind="text",
            embedding_space="text",
            type_signatures=frozenset(
                {("xlsx_cell_text", "xlsx_normalized", "xlsx_range")}
            ),
        ),
    ),
    metrics_namespace="xlsx",
    ingestion_config_snapshot=lambda: {
        "xlsxParserVersion": "xlsx-parser-v1",
        "xlsxNormalizationVersion": "xlsx-normalization-v1",
    },
    full_payload_validator=validate_xlsx_upload_payload,
)

PPTX_MODULE = ModalityModule(
    asset_kind="pptx",
    contract_version=1,
    enabled=True,
    supported_mime_types=frozenset({PPTX_MIME}),
    byte_inspector=detect_pptx_mime_type,
    representation_types=(
        TypeRegistration("pptx_source"),
        TypeRegistration("pptx_normalized"),
    ),
    content_unit_types=(TypeRegistration("pptx_shape_text"),),
    locator_types=(TypeRegistration("pptx_shape", detail_family="record"),),
    retrieval_channels=(
        RetrievalChannelRegistration(
            kind="text",
            embedding_space="text",
            type_signatures=frozenset(
                {("pptx_shape_text", "pptx_normalized", "pptx_shape")}
            ),
        ),
    ),
    metrics_namespace="pptx",
    ingestion_config_snapshot=lambda: {
        "pptxParserVersion": "pptx-parser-v1",
        "pptxNormalizationVersion": "pptx-normalization-v1",
    },
    full_payload_validator=validate_pptx_upload_payload,
)
