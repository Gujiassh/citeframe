"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, FileCode2, Loader2 } from "lucide-react";

import type { EvidenceRendererProps } from "@/lib/evidence/registry";
import {
  parseHtmlNormalizedContent,
  resolveHtmlHighlight,
  splitTextByCodePointRange,
  type HtmlNormalizedContent,
} from "@/lib/evidence/html-content";
import type { HtmlAnchorLocator } from "@/lib/evidence/types";
import { useWorkspace } from "@/lib/workspace-context";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; content: HtmlNormalizedContent }
  | { status: "unavailable"; reason: string };

export function HtmlEvidenceRenderer({
  asset,
  locator,
  sourceVersions,
}: EvidenceRendererProps) {
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? "";
  const htmlLocator = locator?.kind === "html_anchor" ? locator as HtmlAnchorLocator : null;
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [highlight, setHighlight] = useState<Awaited<ReturnType<typeof resolveHtmlHighlight>>>({
    status: "none",
  });

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
        const parsed = parseHtmlNormalizedContent(await response.json());
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
      const next = await resolveHtmlHighlight({
        locator: htmlLocator,
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
  }, [htmlLocator, loadState, sourceVersions]);

  if (loadState.status === "loading") {
    return (
      <div className="flex items-center gap-2 p-4 text-sm text-zinc-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading HTML evidence
      </div>
    );
  }
  if (loadState.status !== "ready") {
    return (
      <div className="flex items-center gap-2 p-4 text-sm text-amber-700">
        <AlertTriangle className="h-4 w-4" />
        HTML evidence is unavailable
      </div>
    );
  }

  return (
    <div className="space-y-3 overflow-auto p-4" data-html-sanitized-viewer="true">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-zinc-500">
        <FileCode2 className="h-3.5 w-3.5" />
        Sanitized HTML
      </div>
      {loadState.content.blocks.map((block) => {
        const active = highlight.status === "ready" && highlight.blockId === block.blockId;
        const parts = active
          ? splitTextByCodePointRange(block.text, highlight.localStart, highlight.localEnd)
          : null;
        return (
          <p
            key={block.blockId}
            data-html-block-id={block.blockId}
            className="whitespace-pre-wrap break-words text-sm leading-6 text-zinc-800 dark:text-zinc-200"
          >
            {parts ? (
              <>
                {parts.before}
                <mark className="rounded-sm bg-amber-200/80 px-0.5 dark:bg-amber-400/30">
                  {parts.selected}
                </mark>
                {parts.after}
              </>
            ) : (
              block.text
            )}
          </p>
        );
      })}
    </div>
  );
}
