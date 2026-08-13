import type { HtmlAnchorLocator, SourceVersions } from "./types";
import {
  sha256HexUtf8,
  splitTextByCodePointRange,
} from "./document-content";

export const HTML_NORMALIZATION_VERSION = "html-normalization-v1" as const;
export const HTML_PARSER_VERSION = "html-parser-v1" as const;
export const HTML_SANITIZER_VERSION = "html-sanitizer-v1" as const;

export type HtmlNormalizedBlock = {
  blockId: string;
  blockOrder: number;
  blockKind: HtmlAnchorLocator["blockKind"];
  headingPath: string[];
  charStart: number;
  charEnd: number;
  textSha256: string;
  text: string;
  cssPathHint: string | null;
};

export type HtmlNormalizedContent = {
  assetId: string;
  representationId: string;
  processingGeneration: number;
  format: "html";
  parserVersion: typeof HTML_PARSER_VERSION;
  sanitizerVersion: typeof HTML_SANITIZER_VERSION;
  normalizationVersion: typeof HTML_NORMALIZATION_VERSION;
  contentSha256: string;
  normalizedText: string;
  sanitizedHtml: string;
  blocks: HtmlNormalizedBlock[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function isSha256Hex(value: unknown): value is string {
  return isString(value) && value.length === 64 && /^[0-9a-f]+$/.test(value);
}

export function isHtmlAnchorLocator(value: unknown): value is HtmlAnchorLocator {
  if (!isRecord(value) || value.kind !== "html_anchor" || value.version !== 1) {
    return false;
  }
  return isString(value.blockId)
    && value.blockId.length > 0
    && isInteger(value.charStart)
    && isInteger(value.charEnd)
    && value.charEnd > value.charStart
    && isSha256Hex(value.textSha256)
    && value.normalizationVersion === HTML_NORMALIZATION_VERSION;
}

export function parseHtmlNormalizedContent(value: unknown): HtmlNormalizedContent | null {
  if (!isRecord(value) || value.format !== "html") {
    return null;
  }
  if (
    value.parserVersion !== HTML_PARSER_VERSION
    || value.sanitizerVersion !== HTML_SANITIZER_VERSION
    || value.normalizationVersion !== HTML_NORMALIZATION_VERSION
    || !isString(value.assetId)
    || !isString(value.representationId)
    || !isInteger(value.processingGeneration)
    || !isSha256Hex(value.contentSha256)
    || !isString(value.normalizedText)
    || !isString(value.sanitizedHtml)
    || !Array.isArray(value.blocks)
  ) {
    return null;
  }
  if (/<script|javascript:|\son[a-z]+=/i.test(value.sanitizedHtml)) {
    return null;
  }
  const blocks: HtmlNormalizedBlock[] = [];
  for (const block of value.blocks) {
    if (
      !isRecord(block)
      || !isString(block.blockId)
      || !isInteger(block.blockOrder)
      || !isInteger(block.charStart)
      || !isInteger(block.charEnd)
      || !isSha256Hex(block.textSha256)
      || !isString(block.text)
    ) {
      return null;
    }
    blocks.push({
      blockId: block.blockId,
      blockOrder: block.blockOrder,
      blockKind: block.blockKind as HtmlNormalizedBlock["blockKind"],
      headingPath: Array.isArray(block.headingPath) ? block.headingPath.filter(isString) : [],
      charStart: block.charStart,
      charEnd: block.charEnd,
      textSha256: block.textSha256,
      text: block.text,
      cssPathHint: isString(block.cssPathHint) ? block.cssPathHint : null,
    });
  }
  return {
    assetId: value.assetId,
    representationId: value.representationId,
    processingGeneration: value.processingGeneration,
    format: "html",
    parserVersion: HTML_PARSER_VERSION,
    sanitizerVersion: HTML_SANITIZER_VERSION,
    normalizationVersion: HTML_NORMALIZATION_VERSION,
    contentSha256: value.contentSha256,
    normalizedText: value.normalizedText,
    sanitizedHtml: value.sanitizedHtml,
    blocks,
  };
}

export async function resolveHtmlHighlight(input: {
  locator: HtmlAnchorLocator | null;
  sourceVersions: SourceVersions | null;
  content: HtmlNormalizedContent | null;
}): Promise<
  | { status: "none" }
  | {
    status: "ready";
    blockId: string;
    localStart: number;
    localEnd: number;
    selectedText: string;
  }
  | { status: "unavailable"; reason: string }
> {
  if (!input.locator) {
    return { status: "none" };
  }
  if (!isHtmlAnchorLocator(input.locator) || !input.content) {
    return { status: "unavailable", reason: "unknown_locator" };
  }
  const block = input.content.blocks.find((item) => item.blockId === input.locator?.blockId);
  if (!block) {
    return { status: "unavailable", reason: "missing_block" };
  }
  if (input.locator.charStart < block.charStart || input.locator.charEnd > block.charEnd) {
    return { status: "unavailable", reason: "range_mismatch" };
  }
  const selected = input.content.normalizedText.slice(input.locator.charStart, input.locator.charEnd);
  const digest = await sha256HexUtf8(selected);
  if (digest !== input.locator.textSha256) {
    return { status: "unavailable", reason: "hash_mismatch" };
  }
  return {
    status: "ready",
    blockId: block.blockId,
    localStart: input.locator.charStart - block.charStart,
    localEnd: input.locator.charEnd - block.charStart,
    selectedText: selected,
  };
}

export { splitTextByCodePointRange };
