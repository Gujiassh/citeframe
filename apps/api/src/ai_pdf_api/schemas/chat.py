from math import isclose, isfinite
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ThreadSummary(BaseModel):
    id: str
    workspaceId: str
    title: str | None
    lastMessageAt: str
    createdAt: str


class ThreadListResponse(BaseModel):
    items: list[ThreadSummary]
    nextCursor: str | None


class CreateThreadRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class CreateThreadResponse(BaseModel):
    thread: ThreadSummary


class SpatialRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> "SpatialRegion":
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Evidence region must remain inside its normalized surface")
        return self


class PageGeometry(BaseModel):
    cropBoxPoints: list[float] = Field(min_length=4, max_length=4)
    rotationDegrees: Literal[0, 90, 180, 270]
    displayWidthPoints: float = Field(gt=0)
    displayHeightPoints: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_geometry(self) -> "PageGeometry":
        x0, y0, x1, y1 = self.cropBoxPoints
        values = (*self.cropBoxPoints, self.displayWidthPoints, self.displayHeightPoints)
        if not all(isfinite(value) for value in values):
            raise ValueError("PDF page geometry values must be finite")
        if x1 <= x0 or y1 <= y0:
            raise ValueError("PDF CropBox must have positive width and height")
        crop_width = x1 - x0
        crop_height = y1 - y0
        expected_width, expected_height = (
            (crop_height, crop_width)
            if self.rotationDegrees in {90, 270}
            else (crop_width, crop_height)
        )
        if not isclose(self.displayWidthPoints, expected_width, abs_tol=0.01):
            raise ValueError("PDF display width does not match the rotated CropBox")
        if not isclose(self.displayHeightPoints, expected_height, abs_tol=0.01):
            raise ValueError("PDF display height does not match the rotated CropBox")
        return self


class PdfPageLocator(BaseModel):
    kind: Literal["pdf_page"]
    version: Literal[1]
    pageNumber: int = Field(ge=1)


class PdfRegionLocator(BaseModel):
    kind: Literal["pdf_region"]
    version: Literal[1]
    pageNumber: int = Field(ge=1)
    coordinateSpace: Literal["pdf_crop_box_normalized_top_left_v1"]
    pageGeometry: PageGeometry
    regions: list[SpatialRegion] = Field(min_length=1)




class DocumentAnchorLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["document_anchor"]
    version: Literal[1]
    blockId: str = Field(min_length=1, max_length=64)
    blockKind: Literal["heading", "paragraph", "list_item", "code_block", "quote", "table"]
    headingPath: list[str] = Field(default_factory=list)
    charStart: int = Field(ge=0)
    charEnd: int = Field(gt=0)
    textSha256: str = Field(min_length=64, max_length=64)
    normalizationVersion: Literal["document-normalization-v1"]

    @model_validator(mode="after")
    def validate_range_and_path(self) -> "DocumentAnchorLocator":
        if self.charEnd <= self.charStart:
            raise ValueError("Document anchor charEnd must be greater than charStart")
        if any(not isinstance(part, str) or not part for part in self.headingPath):
            raise ValueError("Document headingPath must be an ordered array of non-empty strings")
        if len(self.textSha256) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.textSha256
        ):
            raise ValueError("Document textSha256 must be a lowercase hex SHA-256 digest")
        return self


class DocxAnchorLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["docx_anchor"]
    version: Literal[1]
    blockId: str = Field(min_length=1, max_length=64)
    blockKind: Literal["heading", "paragraph", "list_item", "table"]
    headingPath: list[str] = Field(default_factory=list)
    charStart: int = Field(ge=0)
    charEnd: int = Field(gt=0)
    textSha256: str = Field(min_length=64, max_length=64)
    normalizationVersion: Literal["docx-normalization-v1"]

    @model_validator(mode="after")
    def validate_range_and_path(self) -> "DocxAnchorLocator":
        if self.charEnd <= self.charStart:
            raise ValueError("DOCX anchor charEnd must be greater than charStart")
        if any(not isinstance(part, str) or not part for part in self.headingPath):
            raise ValueError("DOCX headingPath must be an ordered array of non-empty strings")
        if len(self.textSha256) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.textSha256
        ):
            raise ValueError("DOCX textSha256 must be a lowercase hex SHA-256 digest")
        return self


class XlsxRangeLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["xlsx_range"]
    version: Literal[1]
    sheetName: str = Field(min_length=1, max_length=255)
    startCell: str = Field(min_length=1, max_length=32)
    endCell: str = Field(min_length=1, max_length=32)
    textSha256: str = Field(min_length=64, max_length=64)
    displayedText: str = Field(min_length=1)
    normalizationVersion: Literal["xlsx-normalization-v1"]


class PptxShapeLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["pptx_shape"]
    version: Literal[1]
    slideIndex: int = Field(ge=1)
    shapeId: str = Field(min_length=1, max_length=64)
    textSha256: str = Field(min_length=64, max_length=64)
    displayedText: str = Field(min_length=1)
    normalizationVersion: Literal["pptx-normalization-v1"]




class HtmlAnchorLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["html_anchor"]
    version: Literal[1]
    blockId: str = Field(min_length=1, max_length=64)
    blockKind: Literal["heading", "paragraph", "list_item", "code_block", "quote", "table"]
    headingPath: list[str] = Field(default_factory=list)
    charStart: int = Field(ge=0)
    charEnd: int = Field(gt=0)
    textSha256: str = Field(min_length=64, max_length=64)
    normalizationVersion: Literal["html-normalization-v1"]
    cssPathHint: str | None = None

    @model_validator(mode="after")
    def validate_range_and_path(self) -> "HtmlAnchorLocator":
        if self.charEnd <= self.charStart:
            raise ValueError("HTML anchor charEnd must be greater than charStart")
        if any(not isinstance(part, str) or not part for part in self.headingPath):
            raise ValueError("HTML headingPath must be an ordered array of non-empty strings")
        if len(self.textSha256) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.textSha256
        ):
            raise ValueError("HTML textSha256 must be a lowercase hex SHA-256 digest")
        if self.cssPathHint is not None and (
            not self.cssPathHint or len(self.cssPathHint) > 512 or any(
                ch in self.cssPathHint for ch in ("\x00", "<", ">")
            )
        ):
            raise ValueError("HTML cssPathHint is not a safe renderer hint")
        return self

class ImageRegionLocator(BaseModel):
    kind: Literal["image_region"]
    version: Literal[1]
    coordinateSpace: Literal["image_normalized_top_left_v1"]
    widthPixels: int = Field(gt=0)
    heightPixels: int = Field(gt=0)
    orientationApplied: Literal[True]
    regions: list[SpatialRegion] = Field(min_length=1)


EvidenceLocatorDto = Annotated[
    PdfPageLocator
    | PdfRegionLocator
    | ImageRegionLocator
    | DocumentAnchorLocator
    | HtmlAnchorLocator
    | DocxAnchorLocator
    | XlsxRangeLocator
    | PptxShapeLocator,
    Field(discriminator="kind"),
]


class SourceVersions(BaseModel):
    parserVersion: str
    processingGeneration: int
    representationId: str
    indexVersion: int


class Citation(BaseModel):
    id: str
    messageId: str
    citationIndex: int
    assetId: str
    assetKind: str
    assetTitle: str
    sourceAvailable: bool
    excerpt: str
    locator: EvidenceLocatorDto
    sourceVersions: SourceVersions


class InputEvidence(BaseModel):
    id: str
    messageId: str
    targetOrder: int
    assetId: str
    assetKind: str
    assetTitle: str
    sourceAvailable: bool
    excerpt: str
    locator: EvidenceLocatorDto
    sourceVersions: SourceVersions


class Message(BaseModel):
    id: str
    workspaceId: str
    threadId: str
    parentMessageId: str | None
    role: str
    content: str
    status: str
    modelProvider: str | None
    modelName: str | None
    createdAt: str
    citations: list[Citation]
    inputEvidence: list[InputEvidence] = Field(default_factory=list)


class ThreadMessagesResponse(BaseModel):
    thread: ThreadSummary
    messages: list[Message]


class AllReadyAssetScope(BaseModel):
    mode: Literal["all_ready"]


class SelectedAssetScope(BaseModel):
    mode: Literal["selected"]
    assetIds: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_asset_ids(self) -> "SelectedAssetScope":
        if len(self.assetIds) != len(set(self.assetIds)):
            raise ValueError("assetIds must not contain duplicates")
        return self


AssetScope = Annotated[AllReadyAssetScope | SelectedAssetScope, Field(discriminator="mode")]


class ImageRegionEvidenceTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["image_region"]
    assetId: str
    processingGeneration: int = Field(ge=1)
    coordinateSpace: Literal["image_normalized_top_left_v1"]
    regions: list[SpatialRegion] = Field(min_length=1, max_length=8)


EvidenceTargetRequest = ImageRegionEvidenceTarget


class ChatStreamRequest(BaseModel):
    threadId: str
    question: str = Field(min_length=1, max_length=12000)
    assetScope: AssetScope
    selectionText: str | None = Field(default=None, max_length=12000)
    evidenceTargets: list[EvidenceTargetRequest] = Field(default_factory=list, max_length=8)
    parentMessageId: str | None = None
    editMessageId: str | None = None
