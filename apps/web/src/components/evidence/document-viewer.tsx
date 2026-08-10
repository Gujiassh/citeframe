"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { AlertTriangle, FileText, Loader2 } from "lucide-react";

import type { EvidenceRendererProps } from "@/lib/evidence/registry";
import {
  loadDocumentViewerContent,
  resolveDocumentHighlight,
  splitTextByCodePointRange,
  type DocumentAssetDetail,
  type DocumentHighlightReason,
  type DocumentNormalizedBlock,
  type VerifiedDocumentNormalizedContent,
} from "@/lib/evidence/document-content";
import type { DocumentAnchorLocator } from "@/lib/evidence/types";
import { useTranslation, type TranslationKey } from "@/lib/i18n-context";
import { useWorkspace } from "@/lib/workspace-context";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; detail: DocumentAssetDetail | null; content: VerifiedDocumentNormalizedContent }
  | { status: "unavailable"; reason: DocumentHighlightReason };

function unavailableMessage(
  reason: DocumentHighlightReason,
  t: (key: TranslationKey) => string,
): string {
  if (reason === "source_deleted") {
    return t("viewer.sourceUnavailable");
  }
  if (reason === "unknown_locator" || reason === "unknown_version" || reason === "snapshot_mismatch") {
    return t("viewer.locatorMismatch");
  }
  if (reason === "content_unavailable") {
    return t("viewer.documentContentUnavailable");
  }
  if (reason === "missing_block") {
    return t("viewer.documentBlockUnavailable");
  }
  if (reason === "hash_mismatch" || reason === "range_mismatch" || reason === "integrity_failed") {
    return t("viewer.documentEvidenceMismatch");
  }
  return t("viewer.locatorMismatch");
}

export function renderDocumentBlockText(
  block: DocumentNormalizedBlock,
  highlight: { localStart: number; localEnd: number } | null,
) {
  if (!highlight) {
    return block.text;
  }
  const parts = splitTextByCodePointRange(block.text, highlight.localStart, highlight.localEnd);
  if (!parts) {
    return block.text;
  }
  return (
    <>
      {parts.before}
      <mark
        data-document-highlight-range="true"
        className="rounded-sm bg-amber-200/80 px-0.5 text-inherit dark:bg-amber-400/30"
      >
        {parts.selected}
      </mark>
      {parts.after}
    </>
  );
}

export function DocumentBlockView({
  block,
  active,
  highlight,
  onActivate,
}: {
  block: DocumentNormalizedBlock;
  active: boolean;
  highlight: { localStart: number; localEnd: number } | null;
  onActivate: (blockId: string) => void;
}) {
  const className = active
    ? "rounded-md border border-amber-400/70 bg-amber-50/80 px-3 py-2 text-left dark:border-amber-500/50 dark:bg-amber-500/10"
    : "rounded-md border border-transparent px-3 py-2 text-left hover:border-zinc-200 dark:hover:border-zinc-800";

  const content = renderDocumentBlockText(block, highlight);
  const sharedProps = {
    id: `document-block-${block.blockId}`,
    type: "button" as const,
    "data-document-block-id": block.blockId,
    "data-document-block-kind": block.blockKind,
    "data-document-block-active": active ? "true" : "false",
    "aria-current": active ? ("true" as const) : undefined,
    onClick: () => onActivate(block.blockId),
    onKeyDown: (event: ReactKeyboardEvent<HTMLButtonElement>) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onActivate(block.blockId);
      }
    },
    className: `${className} w-full cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40`,
  };

  if (block.blockKind === "heading") {
    const level = block.headingLevel ?? 1;
    const headingClass = level <= 1
      ? "text-base font-bold text-zinc-900 dark:text-zinc-50"
      : level === 2
        ? "text-sm font-bold text-zinc-900 dark:text-zinc-50"
        : "text-sm font-semibold text-zinc-800 dark:text-zinc-100";
    return (
      <button {...sharedProps} data-document-heading-level={level}>
        <span className={headingClass}>{content}</span>
      </button>
    );
  }
  if (block.blockKind === "code_block") {
    return (
      <button {...sharedProps}>
        <pre className="overflow-x-auto whitespace-pre-wrap break-words text-left font-mono text-[11px] leading-5 text-zinc-800 dark:text-zinc-200">
          {content}
        </pre>
      </button>
    );
  }
  if (block.blockKind === "quote") {
    return (
      <button {...sharedProps}>
        <blockquote className="border-l-2 border-indigo-400/60 pl-3 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
          {content}
        </blockquote>
      </button>
    );
  }
  if (block.blockKind === "list_item") {
    return (
      <button {...sharedProps}>
        <span className="text-sm leading-6 text-zinc-700 dark:text-zinc-300">• {content}</span>
      </button>
    );
  }
  return (
    <button {...sharedProps}>
      <span className="whitespace-pre-wrap break-words text-sm leading-6 text-zinc-700 dark:text-zinc-300">
        {content}
      </span>
    </button>
  );
}

export function DocumentEvidenceRenderer({
  asset,
  locator,
  sourceVersions,
}: EvidenceRendererProps) {
  const { currentWorkspace } = useWorkspace();
  const { t } = useTranslation();
  const workspaceId = currentWorkspace?.id ?? "";
  const documentLocator = locator?.kind === "document_anchor"
    ? locator as DocumentAnchorLocator
    : null;
  const hasFrozenEvidence = documentLocator !== null || sourceVersions !== null;
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [manualBlockId, setManualBlockId] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [highlight, setHighlight] = useState<Awaited<ReturnType<typeof resolveDocumentHighlight>>>({
    status: "none",
  });
  const scrollDoneRef = useRef<string | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (!workspaceId) {
      return;
    }
    const requestId = ++requestIdRef.current;
    let cancelled = false;

    async function load() {
      setLoadState({ status: "loading" });
      try {
        if (hasFrozenEvidence) {
          if (
            !documentLocator
            || documentLocator.version !== 1
            || documentLocator.kind !== "document_anchor"
            || !sourceVersions
            || !sourceVersions.representationId
            || sourceVersions.processingGeneration < 1
          ) {
            if (!cancelled && requestId === requestIdRef.current) {
              setLoadState({
                status: "unavailable",
                reason: !documentLocator || documentLocator.kind !== "document_anchor"
                  ? "unknown_locator"
                  : documentLocator.version !== 1
                    ? "unknown_version"
                    : "snapshot_mismatch",
              });
            }
            return;
          }

          const result = await loadDocumentViewerContent({
            mode: "frozen",
            workspaceId,
            assetId: asset.id,
            sourceVersions,
          });
          if (cancelled || requestId !== requestIdRef.current) {
            return;
          }
          setLoadState(result);
          return;
        }

        const result = await loadDocumentViewerContent({
          mode: "current",
          workspaceId,
          assetId: asset.id,
          currentProcessingGeneration: asset.currentProcessingGeneration,
        });
        if (cancelled || requestId !== requestIdRef.current) {
          return;
        }
        setLoadState(result);
      } catch {
        if (!cancelled && requestId === requestIdRef.current) {
          setLoadState({ status: "unavailable", reason: "content_unavailable" });
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [
    asset.currentProcessingGeneration,
    asset.id,
    documentLocator,
    hasFrozenEvidence,
    loadAttempt,
    sourceVersions,
    workspaceId,
  ]);

  useEffect(() => {
    let cancelled = false;
    async function resolve() {
      if (loadState.status !== "ready") {
        const next = await resolveDocumentHighlight({
          locator: documentLocator,
          sourceVersions,
          content: null,
          contentAvailable: false,
        });
        if (!cancelled) {
          setHighlight(next);
        }
        return;
      }
      const next = await resolveDocumentHighlight({
        locator: documentLocator,
        sourceVersions,
        content: loadState.content,
        contentAvailable: true,
        expectedOwnership: {
          assetId: asset.id,
          representationId: hasFrozenEvidence
            ? (sourceVersions?.representationId ?? loadState.content.representationId)
            : loadState.content.representationId,
          processingGeneration: hasFrozenEvidence
            ? (sourceVersions?.processingGeneration ?? loadState.content.processingGeneration)
            : asset.currentProcessingGeneration,
          parserVersion: loadState.content.parserVersion,
          normalizationVersion: loadState.content.normalizationVersion,
        },
      });
      if (!cancelled) {
        setHighlight(next);
      }
    }
    void resolve();
    return () => {
      cancelled = true;
    };
  }, [
    asset.currentProcessingGeneration,
    asset.id,
    documentLocator,
    hasFrozenEvidence,
    loadState,
    sourceVersions,
  ]);

  const activeBlockId = highlight.status === "ready"
    ? highlight.blockId
    : manualBlockId;

  useEffect(() => {
    if (highlight.status !== "ready") {
      return;
    }
    const key = `${highlight.blockId}:${highlight.charStart}:${highlight.charEnd}`;
    if (scrollDoneRef.current === key) {
      return;
    }
    const node = document.getElementById(`document-block-${highlight.blockId}`);
    if (!node) {
      return;
    }
    node.scrollIntoView({ block: "center", behavior: "smooth" });
    scrollDoneRef.current = key;
  }, [highlight, loadState]);

  const metaLabel = useMemo(() => {
    if (loadState.status !== "ready") {
      return "";
    }
    return t("viewer.documentMeta")
      .replace("{generation}", String(loadState.content.processingGeneration))
      .replace("{blocks}", String(loadState.content.blocks.length));
  }, [loadState, t]);

  if (!workspaceId) {
    return (
      <div
        role="alert"
        data-document-viewer-error="workspace"
        className="flex h-full items-center justify-center gap-2 px-6 text-center text-zinc-500"
      >
        <FileText className="h-5 w-5" />
        <p className="text-xs">{t("viewer.documentNoWorkspace")}</p>
      </div>
    );
  }

  if (loadState.status === "loading") {
    return (
      <div
        data-document-viewer-state="loading"
        className="flex h-full items-center justify-center gap-2 px-6 text-center text-zinc-500 dark:text-zinc-400"
      >
        <Loader2 className="h-4 w-4 animate-spin" />
        <p className="text-xs leading-5">{t("viewer.documentLoadingNormalized")}</p>
      </div>
    );
  }

  if (loadState.status === "unavailable") {
    return (
      <div
        role="alert"
        data-document-viewer-error={loadState.reason}
        className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center text-rose-600 dark:text-rose-400"
      >
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <p className="text-xs leading-5">{unavailableMessage(loadState.reason, t)}</p>
        </div>
        {loadState.reason === "content_unavailable" ? (
          <button
            type="button"
            onClick={() => setLoadAttempt((value) => value + 1)}
            className="min-h-11 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-semibold text-zinc-700 transition hover:bg-zinc-50 sm:min-h-8 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            {t("viewer.retry")}
          </button>
        ) : null}
      </div>
    );
  }

  if (highlight.status === "unavailable") {
    return (
      <div
        role="alert"
        data-document-viewer-error={highlight.reason}
        data-document-highlight-status="unavailable"
        className="flex h-full items-center justify-center gap-2 px-6 text-center text-rose-600 dark:text-rose-400"
      >
        <AlertTriangle className="h-5 w-5 shrink-0" />
        <p className="text-xs leading-5">{unavailableMessage(highlight.reason, t)}</p>
      </div>
    );
  }

  const content = loadState.content;
  const headings = loadState.detail?.headings
    ?? content.blocks
      .filter((block) => block.blockKind === "heading" && block.headingLevel !== null)
      .map((block, index) => ({
        blockId: block.blockId,
        level: block.headingLevel as number,
        text: block.text,
        order: block.blockOrder ?? index,
      }));
  const highlightTarget = highlight.status === "ready"
    ? { blockId: highlight.blockId, localStart: highlight.localStart, localEnd: highlight.localEnd }
    : null;

  return (
    <div
      data-document-viewer="true"
      data-document-format="markdown"
      data-document-highlight-status={highlight.status}
      data-document-generation={content.processingGeneration}
      className="flex h-full min-h-0 flex-col bg-zinc-50 dark:bg-zinc-950"
    >
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-zinc-200 px-3 py-2 dark:border-zinc-800">
        <FileText className="h-4 w-4 text-zinc-500" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold text-zinc-800 dark:text-zinc-100">{asset.title}</p>
          <p className="truncate text-[10px] text-zinc-500">{metaLabel}</p>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <nav
          data-document-heading-nav="true"
          aria-label={t("viewer.documentHeadings")}
          className="max-h-40 shrink-0 overflow-y-auto border-b border-zinc-200 px-2 py-2 lg:max-h-none lg:w-56 lg:border-b-0 lg:border-r dark:border-zinc-800"
        >
          {headings.length === 0 ? (
            <p className="px-2 py-1 text-[11px] text-zinc-500">{t("viewer.documentNoHeadings")}</p>
          ) : (
            headings.map((heading) => {
              const selected = activeBlockId === heading.blockId;
              return (
                <button
                  key={`${heading.blockId}:${heading.order}`}
                  type="button"
                  data-document-heading-id={heading.blockId}
                  aria-current={selected ? "true" : undefined}
                  onClick={() => {
                    setManualBlockId(heading.blockId);
                    document.getElementById(`document-block-${heading.blockId}`)
                      ?.scrollIntoView({ block: "start", behavior: "smooth" });
                  }}
                  className={`flex min-h-11 w-full items-center rounded-md px-2 py-1.5 text-left text-[11px] transition sm:min-h-8 ${
                    selected
                      ? "bg-indigo-500/10 font-semibold text-indigo-700 dark:text-indigo-300"
                      : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
                  }`}
                  style={{ paddingLeft: `${(heading.level - 1) * 10 + 8}px` }}
                >
                  <span className="truncate">{heading.text}</span>
                </button>
              );
            })
          )}
        </nav>

        <div
          data-document-content="true"
          className="min-h-0 flex-1 overflow-y-auto px-2 py-3 sm:px-4"
        >
          <div className="mx-auto flex max-w-3xl flex-col gap-1">
            {content.blocks.map((block) => {
              const isActive = activeBlockId === block.blockId
                || highlightTarget?.blockId === block.blockId;
              const range = highlightTarget && highlightTarget.blockId === block.blockId
                ? { localStart: highlightTarget.localStart, localEnd: highlightTarget.localEnd }
                : null;
              return (
                <DocumentBlockView
                  key={block.blockId}
                  block={block}
                  active={Boolean(isActive)}
                  highlight={range}
                  onActivate={setManualBlockId}
                />
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
