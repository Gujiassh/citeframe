"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, FileSpreadsheet, FileText, Loader2, Presentation } from "lucide-react";

import type { EvidenceRendererProps } from "@/lib/evidence/registry";
import {
  highlightDocxBlock,
  highlightPptxShape,
  parseDocxNormalizedContent,
  parseOfficeNormalizedText,
  resolvePptxSlides,
  shapeHasGeometry,
  type DocxNormalizedContent,
  type OfficeNormalizedText,
  type PptxLayoutShape,
  type PptxLayoutSlide,
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

function PptxSlideCanvas({
  slide,
  slideWidthEmu,
  slideHeightEmu,
  activeShapeId,
  workspaceId,
  assetId,
}: {
  slide: PptxLayoutSlide;
  slideWidthEmu: number;
  slideHeightEmu: number;
  activeShapeId: string | undefined;
  workspaceId: string;
  assetId: string;
}) {
  const hasAnyGeometry = slide.shapes.some(shapeHasGeometry);
  if (!hasAnyGeometry) {
    return (
      <ul className="space-y-1.5">
        {slide.shapes.map((shape) => {
          const isActive = activeShapeId === shape.shapeId;
          return (
            <li
              key={`${slide.slideIndex}-${shape.shapeId}-${shape.text.slice(0, 24)}`}
              className={
                isActive
                  ? "rounded-md bg-amber-500/15 px-2 py-1.5 text-sm ring-1 ring-amber-500/40"
                  : "rounded-md px-2 py-1.5 text-sm"
              }
            >
              <span className="mr-2 font-mono text-[11px] text-muted-foreground">
                #{shape.shapeId}
              </span>
              <span className="leading-relaxed">{shape.text || shape.shapeKind}</span>
            </li>
          );
        })}
      </ul>
    );
  }

  const aspect = slideHeightEmu / Math.max(slideWidthEmu, 1);

  return (
    <div
      className="relative w-full overflow-hidden rounded-md border border-border/60 bg-white shadow-sm dark:bg-zinc-950"
      style={{ paddingBottom: `${aspect * 100}%` }}
    >
      <div className="absolute inset-0">
        {slide.shapes.map((shape) => (
          <PptxShapeBox
            key={`${slide.slideIndex}-${shape.shapeId}`}
            shape={shape}
            slideWidthEmu={slideWidthEmu}
            slideHeightEmu={slideHeightEmu}
            active={activeShapeId === shape.shapeId}
            workspaceId={workspaceId}
            assetId={assetId}
          />
        ))}
      </div>
    </div>
  );
}

function PptxShapeBox({
  shape,
  slideWidthEmu,
  slideHeightEmu,
  active,
  workspaceId,
  assetId,
}: {
  shape: PptxLayoutShape;
  slideWidthEmu: number;
  slideHeightEmu: number;
  active: boolean;
  workspaceId: string;
  assetId: string;
}) {
  if (!shapeHasGeometry(shape)) return null;
  const left = ((shape.xEmu as number) / slideWidthEmu) * 100;
  const top = ((shape.yEmu as number) / slideHeightEmu) * 100;
  const width = ((shape.cxEmu as number) / slideWidthEmu) * 100;
  const height = ((shape.cyEmu as number) / slideHeightEmu) * 100;
  const mediaUrl =
    shape.hasMedia && shape.mediaPart
      ? `/api/workspaces/${workspaceId}/assets/${assetId}/pptx-media?part=${encodeURIComponent(shape.mediaPart)}`
      : null;

  return (
    <div
      className={
        active
          ? "absolute overflow-hidden rounded-sm bg-amber-500/10 ring-2 ring-amber-500/70"
          : "absolute overflow-hidden rounded-sm ring-1 ring-border/40"
      }
      style={{
        left: `${left}%`,
        top: `${top}%`,
        width: `${width}%`,
        height: `${height}%`,
      }}
      title={shape.text || shape.shapeId}
    >
      {mediaUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={mediaUrl}
          alt={shape.text || "slide image"}
          className="h-full w-full object-contain"
        />
      ) : (
        <div className="flex h-full w-full items-start overflow-hidden p-1 text-[10px] leading-snug text-foreground/90 sm:text-xs">
          {shape.text}
        </div>
      )}
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
  const layout = useMemo(() => {
    if (loadState.status !== "ready-text" || loadState.content.format !== "pptx") {
      return null;
    }
    return resolvePptxSlides(loadState.content);
  }, [loadState]);
  const active =
    layout && locator?.kind === "pptx_shape"
      ? highlightPptxShape(layout.slides, locator.shapeId, locator.slideIndex)
      : null;

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Presentation className="h-4 w-4" />
        <span>PPTX · {asset.title || asset.id}</span>
        {layout?.layoutVersion ? (
          <span className="text-xs font-normal text-muted-foreground">{layout.layoutVersion}</span>
        ) : null}
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
      {layout && layout.slides.length > 0 ? (
        <div className="min-h-0 flex-1 space-y-4 overflow-auto">
          {layout.slides.map((slide) => (
            <section key={slide.slideIndex} className="space-y-2">
              <div className="text-xs font-medium text-muted-foreground">Slide {slide.slideIndex}</div>
              <PptxSlideCanvas
                slide={slide}
                slideWidthEmu={layout.slideWidthEmu}
                slideHeightEmu={layout.slideHeightEmu}
                activeShapeId={
                  active?.slideIndex === slide.slideIndex ? active.shapeId : undefined
                }
                workspaceId={workspaceId}
                assetId={asset.id}
              />
            </section>
          ))}
        </div>
      ) : loadState.status === "ready-text" ? (
        <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap rounded-md border border-border/50 bg-muted/20 p-3 font-mono text-xs leading-relaxed">
          {loadState.content.normalizedText}
        </pre>
      ) : null}
    </div>
  );
}
