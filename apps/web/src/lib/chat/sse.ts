import type {
  ChatStreamCitationsDto,
  ChatStreamDeltaDto,
  ChatStreamDoneDto,
  ChatStreamErrorDto,
  ChatStreamMetaDto,
  CitationDto,
} from "./types";

export type ParsedSseEvent = {
  name: string;
  data: unknown;
};

export type ChatStreamHandlers = {
  onMeta?: (payload: ChatStreamMetaDto) => void;
  onDelta?: (payload: ChatStreamDeltaDto) => void;
  onCitations?: (payload: ChatStreamCitationsDto) => void;
  onDone?: (payload: ChatStreamDoneDto) => void;
  onError?: (payload: ChatStreamErrorDto) => void;
};

export class ChatStreamContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ChatStreamContractError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isInteger(value: unknown): value is number {
  return isFiniteNumber(value) && Number.isInteger(value);
}

function isSpatialRegion(value: unknown): boolean {
  if (!isRecord(value)
    || !isFiniteNumber(value.x)
    || !isFiniteNumber(value.y)
    || !isFiniteNumber(value.width)
    || !isFiniteNumber(value.height)) {
    return false;
  }
  return value.x >= 0
    && value.y >= 0
    && value.width > 0
    && value.height > 0
    && value.x + value.width <= 1
    && value.y + value.height <= 1;
}

function isPageGeometry(value: unknown): boolean {
  if (!isRecord(value)
    || !Array.isArray(value.cropBoxPoints)
    || value.cropBoxPoints.length !== 4
    || !value.cropBoxPoints.every(isFiniteNumber)
    || !isInteger(value.rotationDegrees)
    || ![0, 90, 180, 270].includes(value.rotationDegrees)
    || !isFiniteNumber(value.displayWidthPoints)
    || value.displayWidthPoints <= 0
    || !isFiniteNumber(value.displayHeightPoints)
    || value.displayHeightPoints <= 0) {
    return false;
  }
  const [x0, y0, x1, y1] = value.cropBoxPoints as number[];
  if (x1 <= x0 || y1 <= y0) {
    return false;
  }
  const cropWidth = x1 - x0;
  const cropHeight = y1 - y0;
  const rotated = value.rotationDegrees === 90 || value.rotationDegrees === 270;
  const expectedWidth = rotated ? cropHeight : cropWidth;
  const expectedHeight = rotated ? cropWidth : cropHeight;
  return Math.abs(value.displayWidthPoints - expectedWidth) <= 0.01
    && Math.abs(value.displayHeightPoints - expectedHeight) <= 0.01;
}

export function isEvidenceLocator(value: unknown): boolean {
  if (!isRecord(value) || !isString(value.kind) || value.version !== 1) {
    return false;
  }
  if (value.kind === "pdf_page") {
    return isInteger(value.pageNumber) && value.pageNumber >= 1;
  }
  if (value.kind === "pdf_region") {
    return isInteger(value.pageNumber)
      && value.pageNumber >= 1
      && value.coordinateSpace === "pdf_crop_box_normalized_top_left_v1"
      && isPageGeometry(value.pageGeometry)
      && Array.isArray(value.regions)
      && value.regions.length > 0
      && value.regions.every(isSpatialRegion);
  }
  if (value.kind === "image_region") {
    return value.coordinateSpace === "image_normalized_top_left_v1"
      && isInteger(value.widthPixels)
      && value.widthPixels > 0
      && isInteger(value.heightPixels)
      && value.heightPixels > 0
      && value.orientationApplied === true
      && Array.isArray(value.regions)
      && value.regions.length > 0
      && value.regions.every(isSpatialRegion);
  }
  if (value.kind === "document_anchor") {
    return isString(value.blockId)
      && value.blockId.length > 0
      && isString(value.blockKind)
      && ["heading", "paragraph", "list_item", "code_block", "quote", "table"].includes(value.blockKind)
      && Array.isArray(value.headingPath)
      && value.headingPath.every((part) => isString(part) && part.length > 0)
      && isInteger(value.charStart)
      && value.charStart >= 0
      && isInteger(value.charEnd)
      && value.charEnd > value.charStart
      && isString(value.textSha256)
      && value.textSha256.length === 64
      && /^[0-9a-f]{64}$/.test(value.textSha256)
      && value.normalizationVersion === "document-normalization-v1";
  }
  if (value.kind === "html_anchor") {
    return isString(value.blockId)
      && value.blockId.length > 0
      && isString(value.blockKind)
      && ["heading", "paragraph", "list_item", "code_block", "quote", "table"].includes(value.blockKind)
      && Array.isArray(value.headingPath)
      && value.headingPath.every((part) => isString(part) && part.length > 0)
      && isInteger(value.charStart)
      && value.charStart >= 0
      && isInteger(value.charEnd)
      && value.charEnd > value.charStart
      && isString(value.textSha256)
      && value.textSha256.length === 64
      && /^[0-9a-f]{64}$/.test(value.textSha256)
      && value.normalizationVersion === "html-normalization-v1";
  }
  if (value.kind === "docx_anchor") {
    return isString(value.blockId)
      && value.blockId.length > 0
      && isString(value.blockKind)
      && ["heading", "paragraph", "list_item", "table"].includes(value.blockKind)
      && Array.isArray(value.headingPath)
      && value.headingPath.every((part) => isString(part) && part.length > 0)
      && isInteger(value.charStart)
      && value.charStart >= 0
      && isInteger(value.charEnd)
      && value.charEnd > value.charStart
      && isString(value.textSha256)
      && /^[0-9a-f]{64}$/.test(value.textSha256)
      && value.normalizationVersion === "docx-normalization-v1";
  }
  if (value.kind === "xlsx_range") {
    return isString(value.sheetName)
      && value.sheetName.length > 0
      && isString(value.startCell)
      && value.startCell.length > 0
      && isString(value.endCell)
      && value.endCell.length > 0
      && isString(value.displayedText)
      && value.displayedText.length > 0
      && isString(value.textSha256)
      && /^[0-9a-f]{64}$/.test(value.textSha256)
      && value.normalizationVersion === "xlsx-normalization-v1";
  }
  if (value.kind === "pptx_shape") {
    return isInteger(value.slideIndex)
      && value.slideIndex >= 1
      && isString(value.shapeId)
      && value.shapeId.length > 0
      && isString(value.displayedText)
      && value.displayedText.length > 0
      && isString(value.textSha256)
      && /^[0-9a-f]{64}$/.test(value.textSha256)
      && value.normalizationVersion === "pptx-normalization-v1";
  }
  if (value.kind === "audio_range") {
    return isInteger(value.startMs)
      && value.startMs >= 0
      && isInteger(value.endMs)
      && value.endMs > value.startMs
      && isString(value.segmentId)
      && value.segmentId.length > 0
      && isString(value.textSha256)
      && /^[0-9a-f]{64}$/.test(value.textSha256)
      && value.normalizationVersion === "audio-normalization-v1";
  }
  if (value.kind === "video_range") {
    return isInteger(value.startMs)
      && value.startMs >= 0
      && isInteger(value.endMs)
      && value.endMs > value.startMs
      && isString(value.segmentId)
      && value.segmentId.length > 0
      && isString(value.textSha256)
      && /^[0-9a-f]{64}$/.test(value.textSha256)
      && value.normalizationVersion === "video-normalization-v1";
  }
  if (value.kind === "video_frame") {
    const hasTimestamp = isInteger(value.timestampMs) && value.timestampMs >= 0;
    const hasFrame = isInteger(value.frameIndex) && value.frameIndex >= 0;
    const hasKey = value.keyframeObjectKey == null
      || (isString(value.keyframeObjectKey) && value.keyframeObjectKey.length > 0);
    return value.normalizationVersion === "video-normalization-v1"
      && hasKey
      && (hasTimestamp || hasFrame);
  }
  return false;
}

export function isEvidenceSourceVersions(value: unknown): boolean {
  return isRecord(value)
    && isString(value.parserVersion)
    && isInteger(value.processingGeneration)
    && isString(value.representationId)
    && isInteger(value.indexVersion);
}

function isCitation(value: unknown): value is CitationDto {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.messageId) &&
    isInteger(value.citationIndex) &&
    isString(value.assetId) &&
    isString(value.assetKind) &&
    isString(value.assetTitle) &&
    typeof value.sourceAvailable === "boolean" &&
    isString(value.excerpt) &&
    isEvidenceLocator(value.locator) &&
    isEvidenceSourceVersions(value.sourceVersions)
  );
}

function parseEventBlock(block: string): ParsedSseEvent | null {
  let name = "message";
  const dataLines: string[] = [];

  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) {
      continue;
    }

    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }

    if (field === "event") {
      name = value;
    } else if (field === "data") {
      dataLines.push(value);
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  const rawData = dataLines.join("\n");
  try {
    return { name, data: JSON.parse(rawData) as unknown };
  } catch {
    return { name, data: rawData };
  }
}

export function parseSseEvents(input: string): {
  events: ParsedSseEvent[];
  remainder: string;
} {
  const events: ParsedSseEvent[] = [];
  let remainder = input;

  while (true) {
    const separator = /\r?\n\r?\n/.exec(remainder);
    if (!separator || separator.index === undefined) {
      break;
    }

    const block = remainder.slice(0, separator.index);
    remainder = remainder.slice(separator.index + separator[0].length);
    const event = parseEventBlock(block);
    if (event) {
      events.push(event);
    }
  }

  return { events, remainder };
}

function dispatchEvent(
  event: ParsedSseEvent,
  handlers: ChatStreamHandlers,
): "done" | "error" | null {
  if (event.name === "meta" && isRecord(event.data)) {
    if (isString(event.data.threadId) && isString(event.data.userMessageId) && isString(event.data.assistantMessageId)) {
      handlers.onMeta?.(event.data as unknown as ChatStreamMetaDto);
    }
    return null;
  }

  if (event.name === "delta" && isRecord(event.data) && isString(event.data.text)) {
    handlers.onDelta?.(event.data as unknown as ChatStreamDeltaDto);
    return null;
  }

  if (event.name === "citations") {
    if (!isRecord(event.data)
      || !Array.isArray(event.data.items)
      || !event.data.items.every(isCitation)) {
      throw new ChatStreamContractError(
        "Chat citations event contains an invalid evidence envelope.",
      );
    }
    handlers.onCitations?.({ items: event.data.items });
    return null;
  }

  if (event.name === "done") {
    if (!isRecord(event.data)
      || !isString(event.data.threadId)
      || !isString(event.data.assistantMessageId)) {
      throw new ChatStreamContractError("Chat done event contains an invalid payload.");
    }
    handlers.onDone?.(event.data as unknown as ChatStreamDoneDto);
    return "done";
  }

  if (event.name === "error") {
    if (!isRecord(event.data)
      || !isString(event.data.code)
      || !isString(event.data.message)) {
      throw new ChatStreamContractError("Chat error event contains an invalid payload.");
    }
    handlers.onError?.(event.data as unknown as ChatStreamErrorDto);
    return "error";
  }

  return null;
}

export async function consumeChatStream(
  response: Response,
  handlers: ChatStreamHandlers,
): Promise<void> {
  if (!response.body) {
    throw new Error("Chat stream did not return a response body.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawDone = false;
  let sawError = false;

  const dispatch = (event: ParsedSseEvent) => {
    const terminalEvent = dispatchEvent(event, handlers);
    sawDone ||= terminalEvent === "done";
    sawError ||= terminalEvent === "error";
  };

  while (true) {
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: !done });
    } else if (done) {
      buffer += decoder.decode();
    }

    const parsed = parseSseEvents(buffer);
    buffer = parsed.remainder;
    for (const event of parsed.events) {
      dispatch(event);
    }

    if (done) {
      break;
    }
  }

  if (buffer.trim()) {
    const final = parseSseEvents(`${buffer}\n\n`);
    for (const event of final.events) {
      dispatch(event);
    }
  }

  if (!sawDone && !sawError) {
    throw new Error("Chat stream ended before completion.");
  }
}
