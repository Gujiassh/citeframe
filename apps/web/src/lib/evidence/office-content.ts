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

export type PptxShapeKind = "text" | "picture" | "shape";

export type PptxLayoutShape = {
  shapeId: string;
  shapeKind: PptxShapeKind;
  text: string;
  textSha256?: string | null;
  xEmu: number | null;
  yEmu: number | null;
  cxEmu: number | null;
  cyEmu: number | null;
  mediaPart: string | null;
  mediaContentType: string | null;
  hasMedia: boolean;
};

export type PptxLayoutSlide = {
  slideIndex: number;
  shapes: PptxLayoutShape[];
};

export type OfficeNormalizedText = {
  assetId: string;
  representationId: string;
  processingGeneration: number;
  format: "xlsx" | "pptx";
  contentSha256: string;
  normalizedText: string;
  layoutVersion?: string | null;
  slideWidthEmu?: number | null;
  slideHeightEmu?: number | null;
  slides?: PptxLayoutSlide[] | null;
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

const DEFAULT_SLIDE_W_EMU = 12_192_000;
const DEFAULT_SLIDE_H_EMU = 6_858_000;

/** Prefer structured layout slides from API; fall back to plain-text line parse. */
export function resolvePptxSlides(content: OfficeNormalizedText): {
  slideWidthEmu: number;
  slideHeightEmu: number;
  layoutVersion: string | null;
  slides: PptxLayoutSlide[];
} {
  if (content.slides && content.slides.length > 0) {
    return {
      slideWidthEmu: content.slideWidthEmu ?? DEFAULT_SLIDE_W_EMU,
      slideHeightEmu: content.slideHeightEmu ?? DEFAULT_SLIDE_H_EMU,
      layoutVersion: content.layoutVersion ?? null,
      slides: content.slides.map((slide) => ({
        slideIndex: slide.slideIndex,
        shapes: slide.shapes.map((shape) => ({
          shapeId: shape.shapeId,
          shapeKind: shape.shapeKind ?? "text",
          text: shape.text ?? "",
          textSha256: shape.textSha256,
          xEmu: shape.xEmu ?? null,
          yEmu: shape.yEmu ?? null,
          cxEmu: shape.cxEmu ?? null,
          cyEmu: shape.cyEmu ?? null,
          mediaPart: shape.mediaPart ?? null,
          mediaContentType: shape.mediaContentType ?? null,
          hasMedia: Boolean(shape.hasMedia || shape.mediaPart),
        })),
      })),
    };
  }
  const legacy = parsePptxNormalizedSlides(content.normalizedText);
  return {
    slideWidthEmu: content.slideWidthEmu ?? DEFAULT_SLIDE_W_EMU,
    slideHeightEmu: content.slideHeightEmu ?? DEFAULT_SLIDE_H_EMU,
    layoutVersion: content.layoutVersion ?? "pptx-layout-legacy-text",
    slides: legacy.map((slide) => ({
      slideIndex: slide.slideIndex,
      shapes: slide.shapes.map((shape) => ({
        shapeId: shape.shapeId,
        shapeKind: "text" as const,
        text: shape.text,
        textSha256: null,
        xEmu: null,
        yEmu: null,
        cxEmu: null,
        cyEmu: null,
        mediaPart: null,
        mediaContentType: null,
        hasMedia: false,
      })),
    })),
  };
}

export function highlightPptxShape(
  slides: Array<{ slideIndex: number; shapes: Array<{ shapeId: string; text: string }> }>,
  shapeId: string | undefined,
  slideIndex: number | undefined,
): { slideIndex: number; shapeId: string; text: string } | null {
  if (!shapeId) return null;
  for (const slide of slides) {
    if (slideIndex !== undefined && slide.slideIndex !== slideIndex) continue;
    const shape = slide.shapes.find((item) => item.shapeId === shapeId);
    if (shape) {
      return { slideIndex: slide.slideIndex, shapeId: shape.shapeId, text: shape.text };
    }
  }
  return null;
}

export function shapeHasGeometry(shape: {
  xEmu: number | null;
  yEmu: number | null;
  cxEmu: number | null;
  cyEmu: number | null;
}): boolean {
  return (
    shape.xEmu != null &&
    shape.yEmu != null &&
    shape.cxEmu != null &&
    shape.cyEmu != null &&
    shape.cxEmu > 0 &&
    shape.cyEmu > 0
  );
}
