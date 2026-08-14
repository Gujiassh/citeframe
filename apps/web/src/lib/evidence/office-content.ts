export type DocxNormalizedBlock = {
  blockId: string;
  blockOrder: number;
  blockKind: string;
  headingLevel: number | null;
  headingPath: string[];
  charStart: number;
  charEnd: number;
  textSha256: string;
  text: string;
};

export type DocxNormalizedContent = {
  assetId: string;
  representationId: string;
  processingGeneration: number;
  format: "docx";
  contentSha256: string;
  normalizedText: string;
  blocks: DocxNormalizedBlock[];
};

export type OfficeNormalizedText = {
  assetId: string;
  representationId: string;
  processingGeneration: number;
  format: "xlsx" | "pptx";
  contentSha256: string;
  normalizedText: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function parseDocxNormalizedContent(value: unknown): DocxNormalizedContent | null {
  if (!isRecord(value) || value.format !== "docx") return null;
  if (typeof value.normalizedText !== "string" || !Array.isArray(value.blocks)) return null;
  return value as unknown as DocxNormalizedContent;
}

export function parseOfficeNormalizedText(value: unknown): OfficeNormalizedText | null {
  if (!isRecord(value)) return null;
  if (value.format !== "xlsx" && value.format !== "pptx") return null;
  if (typeof value.normalizedText !== "string") return null;
  return value as unknown as OfficeNormalizedText;
}

export function highlightDocxBlock(
  content: DocxNormalizedContent,
  blockId: string | undefined,
): { blockId: string; text: string } | null {
  if (!blockId) return null;
  const block = content.blocks.find((item) => item.blockId === blockId);
  if (!block) return null;
  return { blockId: block.blockId, text: block.text };
}
