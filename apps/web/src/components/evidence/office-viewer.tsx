"use client";

import { FileSpreadsheet, FileText, Presentation } from "lucide-react";

import type { EvidenceRendererProps } from "@/lib/evidence/registry";

function chip(text: string) {
  return (
    <span className="inline-flex rounded-md border border-border/60 bg-muted/40 px-2 py-0.5 text-xs text-foreground">
      {text}
    </span>
  );
}

export function DocxEvidenceRenderer({ locator, asset }: EvidenceRendererProps) {
  const detail = locator?.kind === "docx_anchor" ? locator : null;
  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <div className="flex items-center gap-2 text-sm font-medium">
        <FileText className="h-4 w-4" />
        <span>DOCX · {asset.title || asset.id}</span>
      </div>
      {detail ? (
        <div className="flex flex-wrap gap-2">
          {chip(`block ${detail.blockId}`)}
          {detail.headingPath.length ? chip(detail.headingPath.join(" / ")) : null}
          {chip(`${detail.charStart}–${detail.charEnd}`)}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No anchor selected.</p>
      )}
    </div>
  );
}

export function XlsxEvidenceRenderer({ locator, asset }: EvidenceRendererProps) {
  const detail = locator?.kind === "xlsx_range" ? locator : null;
  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <div className="flex items-center gap-2 text-sm font-medium">
        <FileSpreadsheet className="h-4 w-4" />
        <span>XLSX · {asset.title || asset.id}</span>
      </div>
      {detail ? (
        <div className="flex flex-wrap gap-2">
          {chip(detail.sheetName)}
          {chip(`${detail.startCell}:${detail.endCell}`)}
          {chip(detail.displayedText)}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No range selected.</p>
      )}
    </div>
  );
}

export function PptxEvidenceRenderer({ locator, asset }: EvidenceRendererProps) {
  const detail = locator?.kind === "pptx_shape" ? locator : null;
  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Presentation className="h-4 w-4" />
        <span>PPTX · {asset.title || asset.id}</span>
      </div>
      {detail ? (
        <div className="flex flex-wrap gap-2">
          {chip(`slide ${detail.slideIndex}`)}
          {chip(`shape ${detail.shapeId}`)}
          {chip(detail.displayedText)}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No shape selected.</p>
      )}
    </div>
  );
}
