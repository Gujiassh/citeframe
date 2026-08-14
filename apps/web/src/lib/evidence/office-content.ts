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


export type PptxShapeLine = {
  slideIndex: number;
  shapeId: string;
  text: string;
};

export type PptxSlideGroup = {
  slideIndex: number;
  shapes: PptxShapeLine[];
};

/** Parse pptx-normalization-v1 lines: `slideN#shapeId=text`. */
export function parsePptxNormalizedSlides(normalizedText: string): PptxSlideGroup[] {
  const bySlide = new Map<number, PptxShapeLine[]>();
  for (const rawLine of normalizedText.split("\n")) {
    const line = rawLine.trimEnd();
    if (!line) continue;
    const match = /^slide(\d+)#([^=]+)=(.*)$/.exec(line);
    if (!match) continue;
    const slideIndex = Number(match[1]);
    if (!Number.isInteger(slideIndex) || slideIndex < 1) continue;
    const shapeId = match[2];
    const text = match[3] ?? "";
    const entry: PptxShapeLine = { slideIndex, shapeId, text };
    const list = bySlide.get(slideIndex) ?? [];
    list.push(entry);
    bySlide.set(slideIndex, list);
  }
  return [...bySlide.entries()]
    .sort(([a], [b]) => a - b)
    .map(([slideIndex, shapes]) => ({ slideIndex, shapes }));
}

export function highlightPptxShape(
  slides: PptxSlideGroup[],
  shapeId: string | undefined,
  slideIndex: number | undefined,
): { slideIndex: number; shapeId: string; text: string } | null {
  if (!shapeId) return null;
  for (const slide of slides) {
    if (slideIndex !== undefined && slide.slideIndex !== slideIndex) continue;
    const shape = slide.shapes.find((item) => item.shapeId === shapeId);
    if (shape) {
      return { slideIndex: shape.slideIndex, shapeId: shape.shapeId, text: shape.text };
    }
  }
  return null;
}

