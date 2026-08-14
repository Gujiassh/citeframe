"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, FileSpreadsheet, FileText, Loader2, Presentation } from "lucide-react";

import type { EvidenceRendererProps } from "@/lib/evidence/registry";
import {
  highlightDocxBlock,
  parseDocxNormalizedContent,
  parseOfficeNormalizedText,
  type DocxNormalizedContent,
  type OfficeNormalizedText,
} from "@/lib/evidence/office-content";
import { useWorkspace } from "@/lib/workspace-context";

type LoadState =
  | { status: "loading" }
  | { status: "ready-docx"; content: DocxNormalizedContent }
  | { status: "ready-text"; content: OfficeNormalizedText }
  | { status: "unavailable"; reason: string };

function chip(text: string) {
  return (
    <span className="inline-flex rounded-md border border-border/60 bg-muted/40 px-2 py-0.5 text-xs text-foreground">
      {text}
    </span>
  );
}

function useOfficeContent(
  assetId: string,
  representationId: string | undefined,
  workspaceId: string,
) {
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
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
          `/api/workspaces/${workspaceId}/assets/${assetId}/representations/${representationId}/content`,
        );
        if (!response.ok) {
          throw new Error("unavailable");
        }
        const body: unknown = await response.json();
        const docx = parseDocxNormalizedContent(body);
        if (docx) {
          if (!cancelled) setLoadState({ status: "ready-docx", content: docx });
          return;
        }
        const text = parseOfficeNormalizedText(body);
        if (text) {
          if (!cancelled) setLoadState({ status: "ready-text", content: text });
          return;
        }
        throw new Error("integrity");
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
  }, [assetId, representationId, workspaceId]);

  return loadState;
}

export function DocxEvidenceRenderer({
  asset,
  locator,
  sourceVersions,
}: EvidenceRendererProps) {
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? "";
  const loadState = useOfficeContent(asset.id, sourceVersions?.representationId, workspaceId);
  const blockId = locator?.kind === "docx_anchor" ? locator.blockId : undefined;
  const highlight =
    loadState.status === "ready-docx" ? highlightDocxBlock(loadState.content, blockId) : null;

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <div className="flex items-center gap-2 text-sm font-medium">
        <FileText className="h-4 w-4" />
        <span>DOCX · {asset.title || asset.id}</span>
      </div>
      {locator?.kind === "docx_anchor" ? (
        <div className="flex flex-wrap gap-2">
          {chip(`block ${locator.blockId}`)}
          {locator.headingPath.length ? chip(locator.headingPath.join(" / ")) : null}
        </div>
      ) : null}
      {loadState.status === "loading" ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </div>
      ) : null}
      {loadState.status === "unavailable" ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <AlertTriangle className="h-4 w-4" /> Content unavailable
        </div>
      ) : null}
      {loadState.status === "ready-docx" ? (
        <div className="min-h-0 flex-1 space-y-2 overflow-auto text-sm leading-relaxed">
          {loadState.content.blocks.map((block) => {
            const active = highlight?.blockId === block.blockId;
            return (
              <p
                key={block.blockId}
                className={
                  active
                    ? "rounded-md bg-amber-500/15 px-2 py-1 ring-1 ring-amber-500/40"
                    : "px-2 py-1"
                }
              >
                {block.text}
              </p>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export function XlsxEvidenceRenderer({
  asset,
  locator,
  sourceVersions,
}: EvidenceRendererProps) {
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? "";
  const loadState = useOfficeContent(asset.id, sourceVersions?.representationId, workspaceId);
  const displayNeedle = locator?.kind === "xlsx_range" ? locator.displayedText : "";

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <div className="flex items-center gap-2 text-sm font-medium">
        <FileSpreadsheet className="h-4 w-4" />
        <span>XLSX · {asset.title || asset.id}</span>
      </div>
      {locator?.kind === "xlsx_range" ? (
        <div className="flex flex-wrap gap-2">
          {chip(locator.sheetName)}
          {chip(`${locator.startCell}:${locator.endCell}`)}
          {chip(locator.displayedText)}
        </div>
      ) : null}
      {loadState.status === "loading" ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </div>
      ) : null}
      {loadState.status === "unavailable" ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <AlertTriangle className="h-4 w-4" /> Content unavailable
        </div>
      ) : null}
      {loadState.status === "ready-text" ? (
        <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap rounded-md border border-border/50 bg-muted/20 p-3 font-mono text-xs leading-relaxed">
          {displayNeedle && loadState.content.normalizedText.includes(displayNeedle)
            ? loadState.content.normalizedText.split(displayNeedle).map((part, index, all) => (
                <span key={index}>
                  {part}
                  {index < all.length - 1 ? (
                    <mark className="rounded bg-amber-500/25 px-0.5">{displayNeedle}</mark>
                  ) : null}
                </span>
              ))
            : loadState.content.normalizedText}
        </pre>
      ) : null}
    </div>
  );
}

export function PptxEvidenceRenderer({
  asset,
  locator,
  sourceVersions,
}: EvidenceRendererProps) {
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? "";
  const loadState = useOfficeContent(asset.id, sourceVersions?.representationId, workspaceId);
  const displayNeedle = locator?.kind === "pptx_shape" ? locator.displayedText : "";

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Presentation className="h-4 w-4" />
        <span>PPTX · {asset.title || asset.id}</span>
      </div>
      {locator?.kind === "pptx_shape" ? (
        <div className="flex flex-wrap gap-2">
          {chip(`slide ${locator.slideIndex}`)}
          {chip(`shape ${locator.shapeId}`)}
          {chip(locator.displayedText)}
        </div>
      ) : null}
      {loadState.status === "loading" ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </div>
      ) : null}
      {loadState.status === "unavailable" ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <AlertTriangle className="h-4 w-4" /> Content unavailable
        </div>
      ) : null}
      {loadState.status === "ready-text" ? (
        <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap rounded-md border border-border/50 bg-muted/20 p-3 font-mono text-xs leading-relaxed">
          {displayNeedle && loadState.content.normalizedText.includes(displayNeedle)
            ? loadState.content.normalizedText.split(displayNeedle).map((part, index, all) => (
                <span key={index}>
                  {part}
                  {index < all.length - 1 ? (
                    <mark className="rounded bg-amber-500/25 px-0.5">{displayNeedle}</mark>
                  ) : null}
                </span>
              ))
            : loadState.content.normalizedText}
        </pre>
      ) : null}
    </div>
  );
}
