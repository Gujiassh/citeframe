"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Headphones, Loader2 } from "lucide-react";

import type { EvidenceRendererProps } from "@/lib/evidence/registry";
import {
  formatAudioTime,
  parseAudioNormalizedContent,
  resolveAudioHighlight,
  type AudioNormalizedContent,
} from "@/lib/evidence/audio-content";
import type { AudioRangeLocator } from "@/lib/evidence/types";
import { useWorkspace } from "@/lib/workspace-context";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; content: AudioNormalizedContent }
  | { status: "unavailable"; reason: string };

export function AudioEvidenceRenderer({
  asset,
  locator,
  sourceVersions,
}: EvidenceRendererProps) {
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? "";
  const audioLocator = locator?.kind === "audio_range" ? (locator as AudioRangeLocator) : null;
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [highlight, setHighlight] = useState<Awaited<ReturnType<typeof resolveAudioHighlight>>>({
    status: "none",
  });
  const audioRef = useRef<HTMLAudioElement | null>(null);

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
        let parsed: AudioNormalizedContent | null = null;
        if (contentType.includes("application/json") || contentType.includes("text/")) {
          parsed = parseAudioNormalizedContent(await response.json());
        } else {
          // Binary source fallback: player only, no transcript body.
          const blob = await response.blob();
          const objectUrl = URL.createObjectURL(blob);
          parsed = {
            format: "audio",
            durationMs: 0,
            transcriptText: "",
            contentSha256: "0".repeat(64),
            segments: [],
            sourceObjectUrl: objectUrl,
          };
          // Without segments the highlight path stays none; still allow playback.
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
      const next = await resolveAudioHighlight({
        locator: audioLocator,
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
  }, [audioLocator, loadState, sourceVersions]);

  useEffect(() => {
    if (highlight.status !== "ready" || !audioRef.current) {
      return;
    }
    const startSeconds = highlight.startMs / 1000;
    try {
      audioRef.current.currentTime = startSeconds;
    } catch {
      // Ignore seek failures on incomplete media metadata.
    }
  }, [highlight]);

  if (loadState.status === "loading") {
    return (
      <div className="flex items-center gap-2 p-4 text-sm text-zinc-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading audio evidence
      </div>
    );
  }
  if (loadState.status !== "ready") {
    return (
      <div className="flex items-center gap-2 p-4 text-sm text-amber-700">
        <AlertTriangle className="h-4 w-4" />
        Audio evidence is unavailable
      </div>
    );
  }

  const mediaSrc =
    loadState.content.sourceObjectUrl ??
    (workspaceId && sourceVersions?.representationId
      ? `/api/workspaces/${workspaceId}/assets/${asset.id}/content`
      : undefined);

  return (
    <div className="space-y-3 overflow-auto p-4" data-audio-viewer="true">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-zinc-500">
        <Headphones className="h-3.5 w-3.5" />
        Audio transcript
      </div>
      {mediaSrc ? (
        <audio
          ref={audioRef}
          controls
          preload="metadata"
          className="w-full"
          src={mediaSrc}
        >
          <track kind="captions" />
        </audio>
      ) : null}
      {highlight.status === "ready" ? (
        <div className="text-xs text-zinc-500">
          Range {formatAudioTime(highlight.startMs)} – {formatAudioTime(highlight.endMs)}
        </div>
      ) : null}
      <div className="space-y-2">
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
                if (audioRef.current) {
                  audioRef.current.currentTime = segment.startMs / 1000;
                  void audioRef.current.play().catch(() => undefined);
                }
              }}
            >
              <div className="mb-1 text-xs text-zinc-500">
                {formatAudioTime(segment.startMs)} – {formatAudioTime(segment.endMs)}
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
