import type { VideoRangeLocator, SourceVersions } from "./types";

export type VideoTranscriptSegment = {
  segmentId: string;
  segmentOrder: number;
  startMs: number;
  endMs: number;
  speaker: string | null;
  text: string;
  textSha256: string;
};

export type VideoKeyframe = {
  index?: number;
  timestampMs: number;
  frameIndex?: number | null;
  objectKey?: string | null;
  contentSha256?: string | null;
};

export type VideoNormalizedContent = {
  format: "video";
  durationMs: number;
  transcriptText: string;
  contentSha256: string;
  segments: VideoTranscriptSegment[];
  keyframes: VideoKeyframe[];
  sourceObjectUrl?: string | null;
};

export type VideoHighlight =
  | { status: "none" }
  | { status: "ready"; segmentId: string; startMs: number; endMs: number }
  | { status: "unavailable"; reason: string };

function isHexSha256(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length === 64 &&
    [...value].every((ch) => "0123456789abcdef".includes(ch))
  );
}

export function parseVideoNormalizedContent(raw: unknown): VideoNormalizedContent | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const body = raw as Record<string, unknown>;
  if (body.format !== "video") {
    return null;
  }
  if (typeof body.durationMs !== "number" || body.durationMs < 0) {
    return null;
  }
  if (typeof body.transcriptText !== "string") {
    return null;
  }
  if (!isHexSha256(body.contentSha256)) {
    return null;
  }
  if (!Array.isArray(body.segments)) {
    return null;
  }
  const segments: VideoTranscriptSegment[] = [];
  for (const item of body.segments) {
    if (!item || typeof item !== "object") {
      return null;
    }
    const row = item as Record<string, unknown>;
    if (
      typeof row.segmentId !== "string" ||
      typeof row.segmentOrder !== "number" ||
      typeof row.startMs !== "number" ||
      typeof row.endMs !== "number" ||
      typeof row.text !== "string" ||
      !isHexSha256(row.textSha256)
    ) {
      return null;
    }
    if (row.endMs <= row.startMs || !row.text.trim()) {
      return null;
    }
    segments.push({
      segmentId: row.segmentId,
      segmentOrder: row.segmentOrder,
      startMs: row.startMs,
      endMs: row.endMs,
      speaker: typeof row.speaker === "string" ? row.speaker : null,
      text: row.text,
      textSha256: row.textSha256,
    });
  }
  if (segments.length === 0) {
    return null;
  }
  const keyframes: VideoKeyframe[] = [];
  if (Array.isArray(body.keyframes)) {
    for (const item of body.keyframes) {
      if (!item || typeof item !== "object") {
        continue;
      }
      const row = item as Record<string, unknown>;
      if (typeof row.timestampMs !== "number" || row.timestampMs < 0) {
        continue;
      }
      keyframes.push({
        index: typeof row.index === "number" ? row.index : undefined,
        timestampMs: row.timestampMs,
        frameIndex: typeof row.frameIndex === "number" ? row.frameIndex : null,
        objectKey: typeof row.objectKey === "string" ? row.objectKey : null,
        contentSha256: typeof row.contentSha256 === "string" ? row.contentSha256 : null,
      });
    }
  }
  return {
    format: "video",
    durationMs: body.durationMs,
    transcriptText: body.transcriptText,
    contentSha256: body.contentSha256,
    segments,
    keyframes,
    sourceObjectUrl: typeof body.sourceObjectUrl === "string" ? body.sourceObjectUrl : null,
  };
}

export async function resolveVideoHighlight(input: {
  locator: VideoRangeLocator | null;
  sourceVersions: SourceVersions | null;
  content: VideoNormalizedContent | null;
}): Promise<VideoHighlight> {
  const { locator, content } = input;
  if (!locator || !content) {
    return { status: "none" };
  }
  if (locator.endMs <= locator.startMs) {
    return { status: "unavailable", reason: "invalid_range" };
  }
  const segment = content.segments.find((item) => item.segmentId === locator.segmentId);
  if (!segment) {
    return { status: "unavailable", reason: "segment_missing" };
  }
  if (locator.startMs < segment.startMs || locator.endMs > segment.endMs) {
    return { status: "unavailable", reason: "range_out_of_bounds" };
  }
  if (locator.textSha256 !== segment.textSha256) {
    return { status: "unavailable", reason: "text_integrity" };
  }
  return {
    status: "ready",
    segmentId: segment.segmentId,
    startMs: locator.startMs,
    endMs: locator.endMs,
  };
}

export function formatVideoTime(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}
