export type JobStatusDto = {
  id: string;
  workspaceId: string;
  assetId: string;
  jobType: string;
  status: string;
  attemptCount: number;
  queuedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  errorCode: string | null;
  errorMessage: string | null;
};

export type AssetSummaryDto = {
  id: string;
  workspaceId: string;
  kind: string;
  title: string;
  sourceFilename: string;
  mimeType: string;
  byteSize: number;
  status: string;
  currentProcessingGeneration: number;
  currentIndexVersion: number;
  lastErrorCode: string | null;
  lastErrorMessage: string | null;
  createdAt: string;
  updatedAt: string;
};

export type AssetListResponseDto = {
  items: AssetSummaryDto[];
  nextCursor: string | null;
};

export type OcrTextBlockDto = {
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
};

export type PdfPageContentDto = {
  pageNumber: number;
  text: string;
  charCount: number;
  ocrBlocks: OcrTextBlockDto[];
};

export type PdfAssetDetailDto = {
  kind: "pdf";
  pageCount: number;
  pages: PdfPageContentDto[];
};

export type ImageAssetDetailDto = {
  kind: "image";
  widthPixels: number;
  heightPixels: number;
  orientationApplied: boolean;
};

export type DocumentHeadingSummaryDto = {
  blockId: string;
  level: number;
  text: string;
  order: number;
};

export type DocumentAssetDetailDto = {
  kind: "document";
  format: "markdown";
  parserVersion: "document-parser-v1";
  normalizationVersion: "document-normalization-v1";
  representationId: string;
  blockCount: number;
  headings: DocumentHeadingSummaryDto[];
};

export type DocumentNormalizedBlockDto = {
  blockId: string;
  blockOrder: number;
  blockKind: "heading" | "paragraph" | "list_item" | "code_block" | "quote" | "table";
  headingPath: string[];
  charStart: number;
  charEnd: number;
  textSha256: string;
  text: string;
};

export type DocumentNormalizedContentDto = {
  assetId: string;
  representationId: string;
  processingGeneration: number;
  format: "markdown";
  parserVersion: "document-parser-v1";
  normalizationVersion: "document-normalization-v1";
  contentSha256: string;
  normalizedText: string;
  blocks: DocumentNormalizedBlockDto[];
};

export type AssetDetailResponseDto = {
  asset: AssetSummaryDto;
  detail: PdfAssetDetailDto | ImageAssetDetailDto | DocumentAssetDetailDto;
};

export type UploadDescriptorDto = {
  method: string;
  objectKey: string;
  headers: Record<string, string>;
  url?: string;
};

export type CreateUploadSessionResponseDto = {
  asset: AssetSummaryDto;
  upload: UploadDescriptorDto;
};

export type FinalizeUploadResponseDto = {
  asset: AssetSummaryDto;
  job: JobStatusDto;
};
