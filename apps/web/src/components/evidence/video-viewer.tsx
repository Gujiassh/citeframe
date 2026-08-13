"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Film, Loader2 } from "lucide-react";

import type { EvidenceRendererProps } from "@/lib/evidence/registry";
import {
  formatVideoTime,
  parseVideoNormalizedContent,
  resolveVideoHighlight,
  type VideoNormalizedContent,
} from "@/lib/evidence/video-content";
import type { VideoRangeLocator } from "@/lib/evidence/types";
import { useWorkspace } from "@/lib/workspace-context";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; content: VideoNormalizedContent }
  | { status: "unavailable"; reason: string };

export function VideoEvidenceRenderer({
  asset,
  locator,
  sourceVersions,
}: EvidenceRendererProps) {
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? "";
  const videoLocator = locator?.kind === "video_range" ? (locator as VideoRangeLocator) : null;
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [highlight, setHighlight] = useState<Awaited<ReturnType<typeof resolveVideoHighlight>>>({
    status: "none",
  });
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    const representationId = sourceVersions?.representationId;
    async function load() {
      if (!workspaceId || !representationId) {
        if (!cancelled) {
          setLoadState({ status: "unavailable", reason: "content_unavailable" });
        }
        return;
      }
      if (!cancelled) {
        setLoadState({ status: "loading" });
      }
      try {
        const response = await fetch(
          `/api/workspaces/${workspaceId}/assets/${asset.id}/representations/${representationId}/content`,
        );
        if (!response.ok) {
          throw new Error("unavailable");
        }
        const contentType = response.headers.get("content-type") ?? "";
        let parsed: VideoNormalizedContent | null = null;
        if (contentType.includes("application/json") || contentType.includes("text/")) {
          parsed = parseVideoNormalizedContent(await response.json());
        } else {
          const blob = await response.blob();
          const objectUrl = URL.createObjectURL(blob);
          parsed = {
            format: "video",
            durationMs: 0,
            transcriptText: "",
            contentSha256: "0".repeat(64),
            segments: [],
            keyframes: [],
            sourceObjectUrl: objectUrl,
          };
          if (!cancelled) {
            setLoadState({ status: "ready", content: parsed });
          }
          return;
        }
        if (!parsed) {
          throw new Error("integrity");
        }
        if (!cancelled) {
          setLoadState({ status: "ready", content: parsed });
        }
      } catch {
        if (!cancelled) {
          setLoadState({ status: "unavailable", reason: "content_unavailable" });
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [asset.id, sourceVersions?.representationId, workspaceId]);

  useEffect(() => {
    let cancelled = false;
    async function resolve() {
      const next = await resolveVideoHighlight({
        locator: videoLocator,
        sourceVersions,
        content: loadState.status === "ready" ? loadState.content : null,
      });
      if (!cancelled) {
        setHighlight(next);
      }
    }
    void resolve();
    return () => {
      cancelled = true;
    };
  }, [videoLocator, loadState, sourceVersions]);

  useEffect(() => {
    if (highlight.status !== "ready" || !videoRef.current) {
      return;
    }
    const startSeconds = highlight.startMs / 1000;
    try {
      videoRef.current.currentTime = startSeconds;
    } catch {
      // Ignore seek failures on incomplete media metadata.
    }
  }, [highlight]);

  if (loadState.status === "loading") {
    return (
      <div className="flex items-center gap-2 p-4 text-sm text-zinc-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading video evidence
      </div>
    );
  }
  if (loadState.status !== "ready") {
    return (
      <div className="flex items-center gap-2 p-4 text-sm text-amber-700">
        <AlertTriangle className="h-4 w-4" />
        Video evidence is unavailable
      </div>
    );
  }

  const mediaSrc =
    loadState.content.sourceObjectUrl ??
    (workspaceId
      ? `/api/workspaces/${workspaceId}/assets/${asset.id}/content`
      : undefined);

  return (
    <div className="space-y-3 overflow-auto p-4" data-video-viewer="true">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-zinc-500">
        <Film className="h-3.5 w-3.5" />
        Video player
      </div>
      {mediaSrc ? (
        <video
          ref={videoRef}
          controls
          preload="metadata"
          className="w-full max-h-[420px] rounded-md bg-black"
          src={mediaSrc}
        >
          <track kind="captions" />
        </video>
      ) : null}
      {highlight.status === "ready" ? (
        <div className="text-xs text-zinc-500">
          Range {formatVideoTime(highlight.startMs)} – {formatVideoTime(highlight.endMs)}
        </div>
      ) : null}
      {loadState.content.keyframes.length > 0 ? (
        <div className="flex gap-2 overflow-x-auto pb-1" data-video-keyframe-strip="true">
          {loadState.content.keyframes.map((frame, index) => (
            <button
              key={`${frame.timestampMs}-${index}`}
              type="button"
              className="shrink-0 rounded border border-zinc-200 px-2 py-1 text-xs text-zinc-600 hover:bg-zinc-50"
              onClick={() => {
                if (videoRef.current) {
                  videoRef.current.currentTime = frame.timestampMs / 1000;
                  void videoRef.current.play().catch(() => undefined);
                }
              }}
            >
              {formatVideoTime(frame.timestampMs)}
            </button>
          ))}
        </div>
      ) : null}
      <div className="space-y-2" data-video-timeline="true">
        {loadState.content.segments.map((segment) => {
          const active =
            highlight.status === "ready" && highlight.segmentId === segment.segmentId;
          return (
            <button
              key={segment.segmentId}
              type="button"
              className={
                active
                  ? "w-full rounded-md border border-amber-400 bg-amber-50 px-3 py-2 text-left text-sm text-zinc-900"
                  : "w-full rounded-md border border-transparent px-3 py-2 text-left text-sm text-zinc-700 hover:bg-zinc-50"
              }
              onClick={() => {
                if (videoRef.current) {
                  videoRef.current.currentTime = segment.startMs / 1000;
                  void videoRef.current.play().catch(() => undefined);
                }
              }}
            >
              <div className="mb-1 text-xs text-zinc-500">
                {formatVideoTime(segment.startMs)} – {formatVideoTime(segment.endMs)}
                {segment.speaker ? ` · ${segment.speaker}` : ""}
              </div>
              <div>{segment.text}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
