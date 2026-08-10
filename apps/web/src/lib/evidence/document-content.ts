import type { DocumentAnchorLocator, SourceVersions } from "./types";

export const DOCUMENT_NORMALIZATION_VERSION = "document-normalization-v1" as const;
export const DOCUMENT_PARSER_VERSION = "document-parser-v1" as const;

export const DOCUMENT_BLOCK_KINDS = [
  "heading",
  "paragraph",
  "list_item",
  "code_block",
  "quote",
  "table",
] as const;

export type DocumentBlockKind = (typeof DOCUMENT_BLOCK_KINDS)[number];

export type DocumentHeadingSummary = {
  blockId: string;
  level: number;
  text: string;
  order: number;
};

export type DocumentAssetDetail = {
  kind: "document";
  format: "markdown";
  parserVersion: typeof DOCUMENT_PARSER_VERSION;
  normalizationVersion: typeof DOCUMENT_NORMALIZATION_VERSION;
  representationId: string;
  blockCount: number;
  headings: DocumentHeadingSummary[];
};

export type DocumentNormalizedBlock = {
  blockId: string;
  blockOrder: number;
  blockKind: DocumentBlockKind;
  headingLevel: number | null;
  headingPath: string[];
  charStart: number;
  charEnd: number;
  textSha256: string;
  text: string;
};

export type DocumentNormalizedContent = {
  assetId: string;
  representationId: string;
  processingGeneration: number;
  format: "markdown";
  parserVersion: typeof DOCUMENT_PARSER_VERSION;
  normalizationVersion: typeof DOCUMENT_NORMALIZATION_VERSION;
  contentSha256: string;
  normalizedText: string;
  blocks: DocumentNormalizedBlock[];
};

/** Content that passed cryptographic + structural integrity verification. */
export type VerifiedDocumentNormalizedContent = DocumentNormalizedContent & {
  readonly __verified: true;
};

export type DocumentHighlightReason =
  | "unknown_locator"
  | "unknown_version"
  | "missing_block"
  | "hash_mismatch"
  | "range_mismatch"
  | "snapshot_mismatch"
  | "integrity_failed"
  | "content_unavailable"
  | "source_deleted";

export type DocumentHighlightResolution =
  | { status: "none" }
  | {
    status: "ready";
    blockId: string;
    blockKind: DocumentBlockKind;
    headingPath: string[];
    charStart: number;
    charEnd: number;
    localStart: number;
    localEnd: number;
    selectedText: string;
    selectedTextSha256: string;
  }
  | { status: "unavailable"; reason: DocumentHighlightReason };

export type DocumentOwnershipBinding = {
  assetId: string;
  representationId: string;
  processingGeneration: number;
  parserVersion?: string;
  normalizationVersion?: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && Number.isInteger(value);
}

function isSha256Hex(value: unknown): value is string {
  return isString(value)
    && value.length === 64
    && /^[0-9a-f]{64}$/.test(value);
}

function isDocumentBlockKind(value: unknown): value is DocumentBlockKind {
  return isString(value) && (DOCUMENT_BLOCK_KINDS as readonly string[]).includes(value);
}

function isHeadingPath(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((part) => isString(part) && part.length > 0);
}

/** Heading blocks require 1..6; non-heading blocks must be null. */
export function isValidDocumentHeadingLevel(
  blockKind: DocumentBlockKind,
  headingLevel: unknown,
): headingLevel is number | null {
  if (blockKind === "heading") {
    return isInteger(headingLevel) && headingLevel >= 1 && headingLevel <= 6;
  }
  return headingLevel === null;
}

/** Python-str equivalent: Unicode code-point sequence (not UTF-16 code units). */
export function toCodePoints(text: string): string[] {
  return Array.from(text);
}

export function codePointLength(text: string): number {
  return Array.from(text).length;
}

export function sliceByCodePoints(text: string, start: number, end: number): string {
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start) {
    return "";
  }
  return Array.from(text).slice(start, end).join("");
}

export async function sha256HexUtf8(text: string): Promise<string> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) {
    throw new Error("Web Crypto subtle digest is unavailable.");
  }
  const bytes = new TextEncoder().encode(text);
  const digest = await subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function isDocumentAnchorLocator(value: unknown): value is DocumentAnchorLocator {
  if (!isRecord(value) || value.kind !== "document_anchor" || value.version !== 1) {
    return false;
  }
  return isString(value.blockId)
    && value.blockId.length > 0
    && isDocumentBlockKind(value.blockKind)
    && isHeadingPath(value.headingPath)
    && isInteger(value.charStart)
    && value.charStart >= 0
    && isInteger(value.charEnd)
    && value.charEnd > value.charStart
    && isSha256Hex(value.textSha256)
    && value.normalizationVersion === DOCUMENT_NORMALIZATION_VERSION;
}

export function parseDocumentAssetDetail(value: unknown): DocumentAssetDetail | null {
  if (!isRecord(value) || value.kind !== "document") {
    return null;
  }
  if (
    value.format !== "markdown"
    || value.parserVersion !== DOCUMENT_PARSER_VERSION
    || value.normalizationVersion !== DOCUMENT_NORMALIZATION_VERSION
    || !isString(value.representationId)
    || value.representationId.length === 0
    || !isInteger(value.blockCount)
    || value.blockCount < 0
    || !Array.isArray(value.headings)
  ) {
    return null;
  }
  const headings: DocumentHeadingSummary[] = [];
  for (const heading of value.headings) {
    if (
      !isRecord(heading)
      || !isString(heading.blockId)
      || heading.blockId.length === 0
      || !isInteger(heading.level)
      || heading.level < 1
      || heading.level > 6
      || !isString(heading.text)
      || !isInteger(heading.order)
      || heading.order < 0
    ) {
      return null;
    }
    headings.push({
      blockId: heading.blockId,
      level: heading.level,
      text: heading.text,
      order: heading.order,
    });
  }
  return {
    kind: "document",
    format: "markdown",
    parserVersion: DOCUMENT_PARSER_VERSION,
    normalizationVersion: DOCUMENT_NORMALIZATION_VERSION,
    representationId: value.representationId,
    blockCount: value.blockCount,
    headings,
  };
}

export function parseDocumentNormalizedContent(value: unknown): DocumentNormalizedContent | null {
  if (!isRecord(value)) {
    return null;
  }
  if (
    !isString(value.assetId)
    || value.assetId.length === 0
    || !isString(value.representationId)
    || value.representationId.length === 0
    || !isInteger(value.processingGeneration)
    || value.processingGeneration < 1
    || value.format !== "markdown"
    || value.parserVersion !== DOCUMENT_PARSER_VERSION
    || value.normalizationVersion !== DOCUMENT_NORMALIZATION_VERSION
    || !isSha256Hex(value.contentSha256)
    || !isString(value.normalizedText)
    || !Array.isArray(value.blocks)
  ) {
    return null;
  }

  const blocks: DocumentNormalizedBlock[] = [];
  for (const block of value.blocks) {
    if (
      !isRecord(block)
      || !isString(block.blockId)
      || block.blockId.length === 0
      || !isInteger(block.blockOrder)
      || block.blockOrder < 0
      || !isDocumentBlockKind(block.blockKind)
      || !isValidDocumentHeadingLevel(block.blockKind, block.headingLevel)
      || !isHeadingPath(block.headingPath)
      || !isInteger(block.charStart)
      || block.charStart < 0
      || !isInteger(block.charEnd)
      || block.charEnd <= block.charStart
      || !isSha256Hex(block.textSha256)
      || !isString(block.text)
      || block.text.length === 0
    ) {
      return null;
    }
    blocks.push({
      blockId: block.blockId,
      blockOrder: block.blockOrder,
      blockKind: block.blockKind,
      headingLevel: block.headingLevel,
      headingPath: [...block.headingPath],
      charStart: block.charStart,
      charEnd: block.charEnd,
      textSha256: block.textSha256,
      text: block.text,
    });
  }

  return {
    assetId: value.assetId,
    representationId: value.representationId,
    processingGeneration: value.processingGeneration,
    format: "markdown",
    parserVersion: DOCUMENT_PARSER_VERSION,
    normalizationVersion: DOCUMENT_NORMALIZATION_VERSION,
    contentSha256: value.contentSha256,
    normalizedText: value.normalizedText,
    blocks,
  };
}

export function buildDocumentContentUrl(
  workspaceId: string,
  assetId: string,
  representationId: string,
): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/assets/${encodeURIComponent(assetId)}/representations/${encodeURIComponent(representationId)}/content`;
}

export function buildDocumentContentApiUrl(
  apiBaseUrl: string,
  workspaceId: string,
  assetId: string,
  representationId: string,
): URL {
  return new URL(
    `${apiBaseUrl}/v1/workspaces/${encodeURIComponent(workspaceId)}/assets/${encodeURIComponent(assetId)}/representations/${encodeURIComponent(representationId)}/content`,
  );
}

export function bindDocumentOwnership(
  content: DocumentNormalizedContent,
  expected: DocumentOwnershipBinding,
): boolean {
  if (
    content.assetId !== expected.assetId
    || content.representationId !== expected.representationId
    || content.processingGeneration !== expected.processingGeneration
  ) {
    return false;
  }
  if (
    expected.parserVersion
    && content.parserVersion !== expected.parserVersion
  ) {
    return false;
  }
  if (
    expected.normalizationVersion
    && content.normalizationVersion !== expected.normalizationVersion
  ) {
    return false;
  }
  return true;
}

/**
 * Cryptographically verify normalized body and every block before render.
 * Rejects mutually consistent fake hashes that do not match actual UTF-8 digests.
 */
export async function verifyDocumentNormalizedContent(
  content: DocumentNormalizedContent,
  expected?: DocumentOwnershipBinding,
): Promise<
  | { ok: true; content: VerifiedDocumentNormalizedContent }
  | { ok: false; reason: "integrity_failed" | "snapshot_mismatch" }
> {
  if (expected && !bindDocumentOwnership(content, expected)) {
    return { ok: false, reason: "snapshot_mismatch" };
  }

  const contentDigest = await sha256HexUtf8(content.normalizedText);
  if (contentDigest !== content.contentSha256) {
    return { ok: false, reason: "integrity_failed" };
  }

  const documentLength = codePointLength(content.normalizedText);
  const seenOrders = new Set<number>();
  const seenIds = new Set<string>();

  for (const block of content.blocks) {
    if (seenOrders.has(block.blockOrder) || seenIds.has(block.blockId)) {
      return { ok: false, reason: "integrity_failed" };
    }
    seenOrders.add(block.blockOrder);
    seenIds.add(block.blockId);

    if (!isValidDocumentHeadingLevel(block.blockKind, block.headingLevel)) {
      return { ok: false, reason: "integrity_failed" };
    }

    if (
      block.charStart < 0
      || block.charEnd <= block.charStart
      || block.charEnd > documentLength
    ) {
      return { ok: false, reason: "integrity_failed" };
    }

    const expectedText = sliceByCodePoints(
      content.normalizedText,
      block.charStart,
      block.charEnd,
    );
    if (expectedText !== block.text || expectedText.length === 0) {
      return { ok: false, reason: "integrity_failed" };
    }
    if (codePointLength(block.text) !== block.charEnd - block.charStart) {
      return { ok: false, reason: "integrity_failed" };
    }

    const blockDigest = await sha256HexUtf8(block.text);
    if (blockDigest !== block.textSha256) {
      return { ok: false, reason: "integrity_failed" };
    }
  }

  return {
    ok: true,
    content: Object.freeze({ ...content, blocks: content.blocks.map((block) => ({ ...block })), __verified: true as const }),
  };
}

export async function resolveDocumentHighlight({
  locator,
  sourceVersions,
  content,
  contentAvailable,
  sourceDeleted,
  expectedOwnership,
}: {
  locator: DocumentAnchorLocator | null;
  sourceVersions: SourceVersions | null;
  content: VerifiedDocumentNormalizedContent | DocumentNormalizedContent | null;
  contentAvailable: boolean;
  sourceDeleted?: boolean;
  expectedOwnership?: DocumentOwnershipBinding;
}): Promise<DocumentHighlightResolution> {
  if (sourceDeleted) {
    return { status: "unavailable", reason: "source_deleted" };
  }
  if (!locator && !sourceVersions) {
    return { status: "none" };
  }
  if (!locator || locator.kind !== "document_anchor") {
    return { status: "unavailable", reason: "unknown_locator" };
  }
  if (locator.version !== 1 || locator.normalizationVersion !== DOCUMENT_NORMALIZATION_VERSION) {
    return { status: "unavailable", reason: "unknown_version" };
  }
  if (
    !sourceVersions
    || !isString(sourceVersions.representationId)
    || sourceVersions.representationId.length === 0
    || !Number.isInteger(sourceVersions.processingGeneration)
    || sourceVersions.processingGeneration < 1
  ) {
    return { status: "unavailable", reason: "snapshot_mismatch" };
  }
  if (!contentAvailable || !content) {
    return { status: "unavailable", reason: "content_unavailable" };
  }

  const ownership: DocumentOwnershipBinding = expectedOwnership ?? {
    assetId: content.assetId,
    representationId: sourceVersions.representationId,
    processingGeneration: sourceVersions.processingGeneration,
    parserVersion: sourceVersions.parserVersion || undefined,
    normalizationVersion: locator.normalizationVersion,
  };

  if (
    content.representationId !== sourceVersions.representationId
    || content.processingGeneration !== sourceVersions.processingGeneration
    || content.normalizationVersion !== locator.normalizationVersion
    || content.parserVersion !== DOCUMENT_PARSER_VERSION
  ) {
    return { status: "unavailable", reason: "snapshot_mismatch" };
  }

  const verified = "__verified" in content && content.__verified
    ? { ok: true as const, content: content as VerifiedDocumentNormalizedContent }
    : await verifyDocumentNormalizedContent(content, ownership);
  if (!verified.ok) {
    return {
      status: "unavailable",
      reason: verified.reason === "snapshot_mismatch" ? "snapshot_mismatch" : "integrity_failed",
    };
  }

  const verifiedContent = verified.content;
  if (!bindDocumentOwnership(verifiedContent, {
    assetId: ownership.assetId,
    representationId: sourceVersions.representationId,
    processingGeneration: sourceVersions.processingGeneration,
    parserVersion: DOCUMENT_PARSER_VERSION,
    normalizationVersion: DOCUMENT_NORMALIZATION_VERSION,
  })) {
    return { status: "unavailable", reason: "snapshot_mismatch" };
  }

  const block = verifiedContent.blocks.find((entry) => entry.blockId === locator.blockId);
  if (!block) {
    return { status: "unavailable", reason: "missing_block" };
  }
  if (block.blockKind !== locator.blockKind) {
    return { status: "unavailable", reason: "snapshot_mismatch" };
  }
  if (
    block.headingPath.length !== locator.headingPath.length
    || block.headingPath.some((part, index) => part !== locator.headingPath[index])
  ) {
    return { status: "unavailable", reason: "snapshot_mismatch" };
  }
  if (
    locator.charStart < block.charStart
    || locator.charEnd > block.charEnd
    || locator.charEnd <= locator.charStart
  ) {
    return { status: "unavailable", reason: "range_mismatch" };
  }

  const selectedText = sliceByCodePoints(
    verifiedContent.normalizedText,
    locator.charStart,
    locator.charEnd,
  );
  if (!selectedText) {
    return { status: "unavailable", reason: "range_mismatch" };
  }
  const selectedDigest = await sha256HexUtf8(selectedText);
  if (selectedDigest !== locator.textSha256) {
    return { status: "unavailable", reason: "hash_mismatch" };
  }
  if (
    locator.charStart === block.charStart
    && locator.charEnd === block.charEnd
    && selectedDigest !== block.textSha256
  ) {
    return { status: "unavailable", reason: "hash_mismatch" };
  }

  const localStart = locator.charStart - block.charStart;
  const localEnd = locator.charEnd - block.charStart;
  const localSelected = sliceByCodePoints(block.text, localStart, localEnd);
  if (localSelected !== selectedText) {
    return { status: "unavailable", reason: "range_mismatch" };
  }

  return {
    status: "ready",
    blockId: block.blockId,
    blockKind: block.blockKind,
    headingPath: [...block.headingPath],
    charStart: locator.charStart,
    charEnd: locator.charEnd,
    localStart,
    localEnd,
    selectedText,
    selectedTextSha256: selectedDigest,
  };
}

export function splitTextByCodePointRange(
  text: string,
  localStart: number,
  localEnd: number,
): { before: string; selected: string; after: string } | null {
  const points = toCodePoints(text);
  if (
    !Number.isInteger(localStart)
    || !Number.isInteger(localEnd)
    || localStart < 0
    || localEnd > points.length
    || localEnd <= localStart
  ) {
    return null;
  }
  return {
    before: points.slice(0, localStart).join(""),
    selected: points.slice(localStart, localEnd).join(""),
    after: points.slice(localEnd).join(""),
  };
}

export type DocumentViewerFetchResult =
  | { status: "ready"; detail: DocumentAssetDetail | null; content: VerifiedDocumentNormalizedContent }
  | { status: "unavailable"; reason: DocumentHighlightReason };

export async function loadDocumentViewerContent(args: {
  mode: "current" | "frozen";
  workspaceId: string;
  assetId: string;
  currentProcessingGeneration?: number;
  sourceVersions?: SourceVersions | null;
  fetchImpl?: typeof fetch;
}): Promise<DocumentViewerFetchResult> {
  const fetchImpl = args.fetchImpl ?? fetch;

  if (args.mode === "frozen") {
    const sourceVersions = args.sourceVersions;
    if (
      !sourceVersions
      || !sourceVersions.representationId
      || !Number.isInteger(sourceVersions.processingGeneration)
      || sourceVersions.processingGeneration < 1
    ) {
      return { status: "unavailable", reason: "snapshot_mismatch" };
    }
    const response = await fetchImpl(
      buildDocumentContentUrl(args.workspaceId, args.assetId, sourceVersions.representationId),
      { cache: "no-store" },
    );
    if (!response.ok) {
      return { status: "unavailable", reason: "content_unavailable" };
    }
    const parsed = parseDocumentNormalizedContent(await response.json());
    if (!parsed) {
      return { status: "unavailable", reason: "content_unavailable" };
    }
    const verified = await verifyDocumentNormalizedContent(parsed, {
      assetId: args.assetId,
      representationId: sourceVersions.representationId,
      processingGeneration: sourceVersions.processingGeneration,
      parserVersion: sourceVersions.parserVersion || DOCUMENT_PARSER_VERSION,
      normalizationVersion: DOCUMENT_NORMALIZATION_VERSION,
    });
    if (!verified.ok) {
      return {
        status: "unavailable",
        reason: verified.reason === "snapshot_mismatch" ? "snapshot_mismatch" : "integrity_failed",
      };
    }
    return { status: "ready", detail: null, content: verified.content };
  }

  if (
    !Number.isInteger(args.currentProcessingGeneration)
    || (args.currentProcessingGeneration ?? 0) < 1
  ) {
    return { status: "unavailable", reason: "content_unavailable" };
  }
  const expectedGeneration = args.currentProcessingGeneration as number;

  const detailResponse = await fetchImpl(
    `/api/workspaces/${encodeURIComponent(args.workspaceId)}/assets/${encodeURIComponent(args.assetId)}`,
    { cache: "no-store" },
  );
  if (!detailResponse.ok) {
    return { status: "unavailable", reason: "content_unavailable" };
  }
  const detailPayload = await detailResponse.json() as {
    asset?: { id?: string; kind?: string; currentProcessingGeneration?: number };
    detail?: unknown;
  };
  if (
    detailPayload.asset?.id !== args.assetId
    || detailPayload.asset?.kind !== "document"
    || detailPayload.asset.currentProcessingGeneration !== expectedGeneration
  ) {
    return { status: "unavailable", reason: "snapshot_mismatch" };
  }
  const detail = parseDocumentAssetDetail(detailPayload.detail);
  if (!detail) {
    return { status: "unavailable", reason: "content_unavailable" };
  }

  const contentResponse = await fetchImpl(
    buildDocumentContentUrl(args.workspaceId, args.assetId, detail.representationId),
    { cache: "no-store" },
  );
  if (!contentResponse.ok) {
    return { status: "unavailable", reason: "content_unavailable" };
  }
  const parsed = parseDocumentNormalizedContent(await contentResponse.json());
  if (!parsed) {
    return { status: "unavailable", reason: "content_unavailable" };
  }
  const verified = await verifyDocumentNormalizedContent(parsed, {
    assetId: args.assetId,
    representationId: detail.representationId,
    processingGeneration: expectedGeneration,
    parserVersion: detail.parserVersion,
    normalizationVersion: detail.normalizationVersion,
  });
  if (!verified.ok) {
    return {
      status: "unavailable",
      reason: verified.reason === "snapshot_mismatch" ? "snapshot_mismatch" : "integrity_failed",
    };
  }
  return { status: "ready", detail, content: verified.content };
}
