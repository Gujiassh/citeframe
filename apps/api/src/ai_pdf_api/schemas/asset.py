from typing import Literal

from pydantic import BaseModel, Field

from ai_pdf_api.schemas.job import JobStatus


class AssetSummary(BaseModel):
    id: str
    workspaceId: str
    kind: str
    title: str
    sourceFilename: str
    mimeType: str
    byteSize: int
    status: str
    currentProcessingGeneration: int
    currentIndexVersion: int
    lastErrorCode: str | None
    lastErrorMessage: str | None
    createdAt: str
    updatedAt: str


class AssetListResponse(BaseModel):
    items: list[AssetSummary]
    nextCursor: str | None


class PdfPageOcrBlock(BaseModel):
    text: str
    x: float
    y: float
    width: float
    height: float


class PdfPageContent(BaseModel):
    pageNumber: int
    text: str
    charCount: int
    ocrBlocks: list[PdfPageOcrBlock] = Field(default_factory=list)


class PdfAssetDetail(BaseModel):
    kind: Literal["pdf"] = "pdf"
    pageCount: int
    pages: list[PdfPageContent]


class ImageAssetDetail(BaseModel):
    kind: Literal["image"] = "image"
    widthPixels: int
    heightPixels: int
    orientationApplied: bool




class DocumentHeadingSummary(BaseModel):
    blockId: str
    level: int = Field(ge=1, le=6)
    text: str
    order: int = Field(ge=0)


class DocumentAssetDetail(BaseModel):
    kind: Literal["document"] = "document"
    format: Literal["markdown"]
    parserVersion: Literal["document-parser-v1"]
    normalizationVersion: Literal["document-normalization-v1"]
    representationId: str
    blockCount: int = Field(ge=0)
    headings: list[DocumentHeadingSummary] = Field(default_factory=list)


class DocumentNormalizedBlock(BaseModel):
    blockId: str
    blockOrder: int = Field(ge=0)
    blockKind: Literal["heading", "paragraph", "list_item", "code_block", "quote", "table"]
    headingLevel: int | None = Field(default=None, ge=1, le=6)
    headingPath: list[str]
    charStart: int = Field(ge=0)
    charEnd: int = Field(gt=0)
    textSha256: str
    text: str


class DocumentNormalizedContentResponse(BaseModel):
    assetId: str
    representationId: str
    processingGeneration: int = Field(ge=1)
    format: Literal["markdown"]
    parserVersion: Literal["document-parser-v1"]
    normalizationVersion: Literal["document-normalization-v1"]
    contentSha256: str
    normalizedText: str
    blocks: list[DocumentNormalizedBlock]


class HtmlHeadingSummary(BaseModel):
    blockId: str
    level: int = Field(ge=1, le=6)
    text: str
    order: int = Field(ge=0)


class HtmlAssetDetail(BaseModel):
    kind: Literal["html"] = "html"
    format: Literal["html"]
    parserVersion: Literal["html-parser-v1"]
    sanitizerVersion: Literal["html-sanitizer-v1"]
    normalizationVersion: Literal["html-normalization-v1"]
    representationId: str
    blockCount: int = Field(ge=0)
    headings: list[HtmlHeadingSummary] = Field(default_factory=list)


class HtmlNormalizedBlock(BaseModel):
    blockId: str
    blockOrder: int = Field(ge=0)
    blockKind: Literal["heading", "paragraph", "list_item", "code_block", "quote", "table"]
    headingLevel: int | None = Field(default=None, ge=1, le=6)
    headingPath: list[str]
    charStart: int = Field(ge=0)
    charEnd: int = Field(gt=0)
    textSha256: str
    text: str
    cssPathHint: str | None = None


class HtmlNormalizedContentResponse(BaseModel):
    assetId: str
    representationId: str
    processingGeneration: int = Field(ge=1)
    format: Literal["html"]
    parserVersion: Literal["html-parser-v1"]
    sanitizerVersion: Literal["html-sanitizer-v1"]
    normalizationVersion: Literal["html-normalization-v1"]
    contentSha256: str
    normalizedText: str
    sanitizedHtml: str
    blocks: list[HtmlNormalizedBlock]


class DocxNormalizedBlock(BaseModel):
    blockId: str
    blockOrder: int = Field(ge=0)
    blockKind: Literal["heading", "paragraph", "list_item", "table"]
    headingLevel: int | None = Field(default=None, ge=1, le=6)
    headingPath: list[str]
    charStart: int = Field(ge=0)
    charEnd: int = Field(gt=0)
    textSha256: str
    text: str


class DocxNormalizedContentResponse(BaseModel):
    assetId: str
    representationId: str
    processingGeneration: int = Field(ge=1)
    format: Literal["docx"]
    parserVersion: Literal["docx-parser-v1"]
    normalizationVersion: Literal["docx-normalization-v1"]
    contentSha256: str
    normalizedText: str
    blocks: list[DocxNormalizedBlock]


class OfficeNormalizedTextResponse(BaseModel):
    """Normalized text body for xlsx/pptx (no block table in v1)."""

    assetId: str
    representationId: str
    processingGeneration: int = Field(ge=1)
    format: Literal["xlsx", "pptx"]
    contentSha256: str
    normalizedText: str


class AssetDetailResponse(BaseModel):
    asset: AssetSummary
    detail: PdfAssetDetail | ImageAssetDetail | DocumentAssetDetail | HtmlAssetDetail = Field(
        discriminator="kind"
    )


class UploadDescriptor(BaseModel):
    method: str
    objectKey: str
    headers: dict[str, str]


class CreateUploadSessionRequest(BaseModel):
    sourceFilename: str = Field(min_length=1, max_length=512)
    mimeType: str = Field(min_length=1, max_length=255)
    byteSize: int = Field(gt=0)
    title: str | None = Field(default=None, max_length=255)


class CreateUploadSessionResponse(BaseModel):
    asset: AssetSummary
    upload: UploadDescriptor


class FinalizeUploadRequest(BaseModel):
    objectKey: str = Field(min_length=1, max_length=1024)


class FinalizeUploadResponse(BaseModel):
    asset: AssetSummary
    job: JobStatus
