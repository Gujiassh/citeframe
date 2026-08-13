export type SpatialRegion = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type PageGeometry = {
  cropBoxPoints: [number, number, number, number];
  rotationDegrees: number;
  displayWidthPoints: number;
  displayHeightPoints: number;
};

export type PdfPageLocator = {
  kind: "pdf_page";
  version: number;
  pageNumber: number;
};

export type PdfRegionLocator = {
  kind: "pdf_region";
  version: number;
  pageNumber: number;
  coordinateSpace: "pdf_crop_box_normalized_top_left_v1";
  pageGeometry: PageGeometry;
  regions: SpatialRegion[];
};

export type ImageRegionLocator = {
  kind: "image_region";
  version: number;
  coordinateSpace: "image_normalized_top_left_v1";
  widthPixels: number;
  heightPixels: number;
  orientationApplied: boolean;
  regions: SpatialRegion[];
};

export type DocumentBlockKind =
  | "heading"
  | "paragraph"
  | "list_item"
  | "code_block"
  | "quote"
  | "table";

export type DocumentAnchorLocator = {
  kind: "document_anchor";
  version: number;
  blockId: string;
  blockKind: DocumentBlockKind;
  headingPath: string[];
  charStart: number;
  charEnd: number;
  textSha256: string;
  normalizationVersion: "document-normalization-v1";
};


export type DocxAnchorLocator = {
  kind: "docx_anchor";
  version: number;
  blockId: string;
  blockKind: DocumentBlockKind | "table";
  headingPath: string[];
  charStart: number;
  charEnd: number;
  textSha256: string;
  normalizationVersion: "docx-normalization-v1";
};

export type XlsxRangeLocator = {
  kind: "xlsx_range";
  version: number;
  sheetName: string;
  startCell: string;
  endCell: string;
  textSha256: string;
  displayedText: string;
  normalizationVersion: "xlsx-normalization-v1";
};

export type PptxShapeLocator = {
  kind: "pptx_shape";
  version: number;
  slideIndex: number;
  shapeId: string;
  textSha256: string;
  displayedText: string;
  normalizationVersion: "pptx-normalization-v1";
};

export type HtmlAnchorLocator = {
  kind: "html_anchor";
  version: number;
  blockId: string;
  blockKind: DocumentBlockKind;
  headingPath: string[];
  charStart: number;
  charEnd: number;
  textSha256: string;
  normalizationVersion: "html-normalization-v1";
  cssPathHint?: string | null;
};

export type AudioRangeLocator = {
  kind: "audio_range";
  version: number;
  startMs: number;
  endMs: number;
  textSha256: string;
  segmentId: string;
  normalizationVersion: "audio-normalization-v1";
};

export type VideoRangeLocator = {
  kind: "video_range";
  version: number;
  startMs: number;
  endMs: number;
  textSha256: string;
  segmentId: string;
  normalizationVersion: "video-normalization-v1";
};

export type VideoFrameLocator = {
  kind: "video_frame";
  version: number;
  timestampMs?: number | null;
  frameIndex?: number | null;
  keyframeObjectKey?: string | null;
  normalizationVersion: "video-normalization-v1";
};

export type EvidenceLocator =
  | PdfPageLocator
  | PdfRegionLocator
  | ImageRegionLocator
  | DocumentAnchorLocator
  | DocxAnchorLocator
  | XlsxRangeLocator
  | PptxShapeLocator
  | HtmlAnchorLocator
  | AudioRangeLocator
  | VideoRangeLocator
  | VideoFrameLocator;

export type SourceVersions = {
  parserVersion: string;
  processingGeneration: number;
  representationId: string;
  indexVersion: number;
};

export type EvidenceTarget = {
  assetId: string;
  assetKind: string;
  assetTitle: string;
  sourceAvailable: boolean;
  locator: EvidenceLocator;
  sourceVersions: SourceVersions;
};

export type ImageRegionEvidenceTargetRequest = {
  kind: "image_region";
  assetId: string;
  processingGeneration: number;
  coordinateSpace: "image_normalized_top_left_v1";
  regions: SpatialRegion[];
};

export type EvidenceTargetRequest = ImageRegionEvidenceTargetRequest;

export function getPdfLocatorPage(locator: EvidenceLocator): number | null {
  return locator.kind === "pdf_page" || locator.kind === "pdf_region"
    ? locator.pageNumber
    : null;
}

export function getLocatorSummary(locator: EvidenceLocator): string {
  if (locator.kind === "pdf_page") {
    return `PDF p.${locator.pageNumber}`;
  }
  if (locator.kind === "pdf_region") {
    return `PDF p.${locator.pageNumber} · ${locator.regions.length > 1 ? `${locator.regions.length} regions` : "region"}`;
  }
  if (locator.kind === "document_anchor") {
    const heading = locator.headingPath.length > 0
      ? locator.headingPath[locator.headingPath.length - 1]
      : locator.blockKind;
    return `Document · ${heading}`;
  }
  if (locator.kind === "html_anchor") {
    const heading = locator.headingPath.length > 0
      ? locator.headingPath[locator.headingPath.length - 1]
      : locator.blockKind;
    return `HTML · ${heading}`;
  }
  if (locator.kind === "audio_range") {
    const start = Math.floor(locator.startMs / 1000);
    const end = Math.floor(locator.endMs / 1000);
    return `Audio · ${start}s–${end}s`;
  }
  if (locator.kind === "video_range") {
    const start = Math.floor(locator.startMs / 1000);
    const end = Math.floor(locator.endMs / 1000);
    return `Video · ${start}s–${end}s`;
  }
  if (locator.kind === "video_frame") {
    if (typeof locator.timestampMs === "number") {
      return `Video frame · ${Math.floor(locator.timestampMs / 1000)}s`;
    }
    if (typeof locator.frameIndex === "number") {
      return `Video frame · #${locator.frameIndex}`;
    }
    return "Video frame";
  }
  return `Image · ${locator.regions.length > 1 ? `${locator.regions.length} regions` : "region"}`;
}
