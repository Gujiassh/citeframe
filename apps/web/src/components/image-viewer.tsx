"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  AlertTriangle,
  Expand,
  Hand,
  Loader2,
  ScanSearch,
  SquareDashedMousePointer,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

import type { EvidenceRendererProps } from "@/lib/evidence/registry";
import type { SpatialRegion } from "@/lib/evidence/types";
import { useTranslation } from "@/lib/i18n-context";
import { useWorkspace } from "@/lib/workspace-context";
import type { AssetDetailResponseDto } from "@/lib/assets/types";

import {
  calculatePinchZoom,
  clampImageZoom,
  createImageRegion,
  isImageNaturalSizeCompatible,
  moveNormalizedImagePoint,
  normalizeImagePoint,
  readCurrentImageGeometry,
  resolveImageViewerSource,
  type CurrentImageGeometry,
  type SurfacePoint,
} from "./image-region-geometry";
import { ImageRegionActions } from "./image-region-actions";

const MIN_ZOOM = 10;
const MAX_ZOOM = 400;
const ZOOM_STEP = 25;

type PanStart = {
  pointerX: number;
  pointerY: number;
  scrollLeft: number;
  scrollTop: number;
};

type PinchStart = {
  distance: number;
  zoomPercent: number;
};

type ImageLoadState = {
  key: string;
  status: "ready" | "error" | "mismatch";
};

function regionStyle(region: SpatialRegion) {
  return {
    left: `${region.x * 100}%`,
    top: `${region.y * 100}%`,
    width: `${region.width * 100}%`,
    height: `${region.height * 100}%`,
  };
}

export function ImageEvidenceRenderer({
  asset,
  locator,
  sourceVersions,
}: EvidenceRendererProps) {
  const {
    activeThread,
    createEvidenceNote,
    currentWorkspace,
    submitEvidenceQuestion,
  } = useWorkspace();
  const { t } = useTranslation();
  const viewportRef = useRef<HTMLDivElement>(null);
  const surfaceRef = useRef<HTMLDivElement>(null);
  const selectionStartRef = useRef<SurfacePoint | null>(null);
  const panStartRef = useRef<PanStart | null>(null);
  const touchPointsRef = useRef(new Map<number, { x: number; y: number }>());
  const pinchStartRef = useRef<PinchStart | null>(null);
  const [viewportSize, setViewportSize] = useState({ width: 760, height: 600 });
  const [zoomPercent, setZoomPercent] = useState<number | null>(null);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selection, setSelection] = useState<SpatialRegion | null>(null);
  const [selectionPreview, setSelectionPreview] = useState<SpatialRegion | null>(null);
  const [keyboardSelectionAnchor, setKeyboardSelectionAnchor] = useState<SurfacePoint | null>(null);
  const [keyboardCursor, setKeyboardCursor] = useState<SurfacePoint>({ x: 0.5, y: 0.5 });
  const [surfaceFocused, setSurfaceFocused] = useState(false);
  const [imageLoadState, setImageLoadState] = useState<ImageLoadState | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [currentGeometry, setCurrentGeometry] = useState<CurrentImageGeometry | null>(null);

  const imageLocator = locator?.kind === "image_region" ? locator : null;
  const hasFrozenEvidence = imageLocator !== null || sourceVersions !== null;
  const workspaceId = currentWorkspace?.id ?? "";

  useEffect(() => {
    if (hasFrozenEvidence || !workspaceId) {
      return;
    }
    let cancelled = false;
    fetch(`/api/workspaces/${workspaceId}/assets/${asset.id}`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("Image asset detail request failed.");
        }
        return response.json() as Promise<AssetDetailResponseDto>;
      })
      .then((payload) => {
        if (cancelled) {
          return;
        }
        const geometry = readCurrentImageGeometry(payload, workspaceId, asset.id);
        if (!geometry) {
          setImageLoadState({
            key: `detail:${workspaceId}:${asset.id}:${loadAttempt}`,
            status: "error",
          });
          return;
        }
        setCurrentGeometry(geometry);
      })
      .catch(() => {
        if (!cancelled) {
          setImageLoadState({
            key: `detail:${workspaceId}:${asset.id}:${loadAttempt}`,
            status: "error",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    asset.id,
    hasFrozenEvidence,
    loadAttempt,
    workspaceId,
  ]);

  const viewerSource = useMemo(() => {
    if (!workspaceId) {
      return { status: "loading" } as const;
    }
    return resolveImageViewerSource({
      workspaceId,
      assetId: asset.id,
      locator: imageLocator,
      sourceVersions,
      currentGeometry,
    });
  }, [
    asset.id,
    currentGeometry,
    imageLocator,
    sourceVersions,
    workspaceId,
  ]);
  const displayGeometry = viewerSource.status === "ready" ? viewerSource.geometry : null;
  const imageUrl = viewerSource.status === "ready" ? viewerSource.url : null;
  const imageLoadKey = imageUrl
    ? `${imageUrl}:${loadAttempt}`
    : `detail:${workspaceId}:${asset.id}:${loadAttempt}`;
  const imageState = imageLoadState?.key === imageLoadKey
    ? imageLoadState.status
    : "loading";
  const selectionTarget = selection && viewerSource.status === "ready" && viewerSource.mode === "current"
    ? {
        kind: "image_region" as const,
        assetId: asset.id,
        processingGeneration: currentGeometry?.processingGeneration ?? 0,
        coordinateSpace: "image_normalized_top_left_v1" as const,
        regions: [selection],
      }
    : null;

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) {
      return;
    }
    const observer = new ResizeObserver(([entry]) => {
      setViewportSize({
        width: Math.max(1, entry.contentRect.width),
        height: Math.max(1, entry.contentRect.height),
      });
    });
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [viewerSource.status]);

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || (!selectionMode && !selection)) {
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      setSelectionMode(false);
      setSelection(null);
      setSelectionPreview(null);
      setKeyboardSelectionAnchor(null);
      selectionStartRef.current = null;
    };
    window.addEventListener("keydown", handleEscape, { capture: true });
    return () => window.removeEventListener("keydown", handleEscape, { capture: true });
  }, [selection, selectionMode]);

  if (viewerSource.status === "invalid") {
    return (
      <div data-image-viewer-error="snapshot" className="flex h-full items-center justify-center gap-2 px-6 text-center text-rose-600 dark:text-rose-400">
        <AlertTriangle className="h-5 w-5 shrink-0" />
        <p className="text-xs leading-5">{t("viewer.imageLocatorMismatch")}</p>
      </div>
    );
  }

  const retryImage = () => {
    if (viewerSource.status !== "ready" || viewerSource.mode === "current") {
      setCurrentGeometry(null);
    }
    setLoadAttempt((value) => value + 1);
  };

  if (imageState === "error" && !displayGeometry) {
    return (
      <div role="alert" data-image-viewer-error="error" className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center text-rose-600 dark:text-rose-400">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <p className="text-xs leading-5">{t("viewer.imageLoadFailed")}</p>
        </div>
        <button
          type="button"
          onClick={retryImage}
          className="min-h-11 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-semibold text-zinc-700 transition hover:bg-zinc-50 sm:min-h-8 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
        >
          {t("viewer.retry")}
        </button>
      </div>
    );
  }

  if (!displayGeometry || !imageUrl) {
    return (
      <div className="flex h-full items-center justify-center gap-2 px-6 text-center text-zinc-500 dark:text-zinc-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        <p className="text-xs leading-5">{t("viewer.imageLoading")}</p>
      </div>
    );
  }

  const availableWidth = Math.max(1, viewportSize.width - 48);
  const availableHeight = Math.max(1, viewportSize.height - 48);
  const fitScale = Math.min(
    1,
    availableWidth / displayGeometry.widthPixels,
    availableHeight / displayGeometry.heightPixels,
  );
  const effectiveZoomPercent = zoomPercent ?? fitScale * 100;
  const renderedWidth = Math.max(1, Math.round(displayGeometry.widthPixels * effectiveZoomPercent / 100));
  const renderedHeight = Math.max(1, Math.round(displayGeometry.heightPixels * effectiveZoomPercent / 100));
  const scrollCanvasWidth = Math.max(viewportSize.width, renderedWidth + 48);
  const scrollCanvasHeight = Math.max(viewportSize.height, renderedHeight + 48);

  const changeZoom = (delta: number) => {
    setZoomPercent(clampImageZoom(effectiveZoomPercent + delta, MIN_ZOOM, MAX_ZOOM));
  };

  const keyboardSelectionPreview = keyboardSelectionAnchor
    ? createImageRegion(
      keyboardSelectionAnchor,
      keyboardCursor,
      { width: renderedWidth, height: renderedHeight },
      0,
    )
    : null;

  const getSelectionPointer = (event: ReactPointerEvent<HTMLDivElement>) => {
    const bounds = surfaceRef.current?.getBoundingClientRect();
    if (!bounds) {
      return null;
    }
    return {
      point: normalizeImagePoint(event.clientX, event.clientY, bounds),
      surface: { width: bounds.width, height: bounds.height },
    };
  };

  const getTouchDistance = () => {
    const points = [...touchPointsRef.current.values()];
    if (points.length < 2) {
      return 0;
    }
    return Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || imageState !== "ready") {
      return;
    }
    if (event.pointerType === "touch") {
      touchPointsRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
      event.currentTarget.setPointerCapture(event.pointerId);
      if (!selectionMode && touchPointsRef.current.size === 2) {
        event.preventDefault();
        pinchStartRef.current = {
          distance: getTouchDistance(),
          zoomPercent: effectiveZoomPercent,
        };
        panStartRef.current = null;
        return;
      }
    }
    if (selectionMode) {
      const pointer = getSelectionPointer(event);
      if (!pointer) {
        return;
      }
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      selectionStartRef.current = pointer.point;
      setSelection(null);
      setSelectionPreview(null);
      return;
    }
    const viewport = viewportRef.current;
    if (!viewport) {
      return;
    }
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    panStartRef.current = {
      pointerX: event.clientX,
      pointerY: event.clientY,
      scrollLeft: viewport.scrollLeft,
      scrollTop: viewport.scrollTop,
    };
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "touch" && touchPointsRef.current.has(event.pointerId)) {
      touchPointsRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
      const pinchStart = pinchStartRef.current;
      if (pinchStart && touchPointsRef.current.size >= 2) {
        event.preventDefault();
        setZoomPercent(calculatePinchZoom(
          pinchStart.zoomPercent,
          pinchStart.distance,
          getTouchDistance(),
          MIN_ZOOM,
          MAX_ZOOM,
        ));
        return;
      }
    }
    const selectionStart = selectionStartRef.current;
    if (selectionStart) {
      const pointer = getSelectionPointer(event);
      if (pointer) {
        setSelectionPreview(createImageRegion(selectionStart, pointer.point, pointer.surface, 0));
      }
      return;
    }
    const panStart = panStartRef.current;
    const viewport = viewportRef.current;
    if (panStart && viewport) {
      viewport.scrollLeft = panStart.scrollLeft - (event.clientX - panStart.pointerX);
      viewport.scrollTop = panStart.scrollTop - (event.clientY - panStart.pointerY);
    }
  };

  const releasePointer = (event: ReactPointerEvent<HTMLDivElement>, commitSelection: boolean) => {
    const wasPinching = pinchStartRef.current !== null;
    if (event.pointerType === "touch") {
      touchPointsRef.current.delete(event.pointerId);
      if (touchPointsRef.current.size < 2) {
        pinchStartRef.current = null;
      }
    }
    const selectionStart = selectionStartRef.current;
    const pointer = selectionStart && commitSelection && !wasPinching
      ? getSelectionPointer(event)
      : null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    selectionStartRef.current = null;
    panStartRef.current = null;
    setSelectionPreview(null);
    if (selectionStart && pointer) {
      const region = createImageRegion(selectionStart, pointer.point, pointer.surface);
      setSelection(region);
      if (region) {
        setSelectionMode(false);
      }
    }
  };

  const toggleSelectionMode = () => {
    setSelectionMode((current) => {
      const next = !current;
      setSelection(null);
      setSelectionPreview(null);
      setKeyboardSelectionAnchor(null);
      selectionStartRef.current = null;
      panStartRef.current = null;
      touchPointsRef.current.clear();
      pinchStartRef.current = null;
      return next;
    });
  };

  const handleSurfaceKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const direction = {
      ArrowLeft: { x: -1, y: 0 },
      ArrowRight: { x: 1, y: 0 },
      ArrowUp: { x: 0, y: -1 },
      ArrowDown: { x: 0, y: 1 },
    }[event.key];
    if (direction) {
      event.preventDefault();
      if (selectionMode) {
        const step = event.shiftKey ? 0.05 : 0.01;
        setKeyboardCursor((point) => moveNormalizedImagePoint(
          point,
          direction.x * step,
          direction.y * step,
        ));
        return;
      }
      const viewport = viewportRef.current;
      if (viewport) {
        const step = event.shiftKey ? 120 : 40;
        viewport.scrollBy({ left: direction.x * step, top: direction.y * step });
      }
      return;
    }
    if ((event.key === "Enter" || event.key === " ") && selectionMode) {
      event.preventDefault();
      if (!keyboardSelectionAnchor) {
        setSelection(null);
        setKeyboardSelectionAnchor(keyboardCursor);
        return;
      }
      const region = createImageRegion(
        keyboardSelectionAnchor,
        keyboardCursor,
        { width: renderedWidth, height: renderedHeight },
      );
      setKeyboardSelectionAnchor(null);
      setSelection(region);
      if (region) {
        setSelectionMode(false);
      }
      return;
    }
    if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      changeZoom(ZOOM_STEP);
    } else if (event.key === "-") {
      event.preventDefault();
      changeZoom(-ZOOM_STEP);
    }
  };

  return (
    <div data-image-viewer className="flex h-full min-h-0 flex-col overflow-hidden bg-zinc-100 text-zinc-700 dark:bg-zinc-950 dark:text-zinc-300">
      <div className="flex h-14 shrink-0 items-center border-b border-zinc-200 bg-white px-2 sm:h-12 sm:justify-between sm:gap-3 sm:px-3 dark:border-zinc-800 dark:bg-zinc-950">
        <span className="hidden min-w-0 truncate text-xs font-semibold text-zinc-800 sm:block dark:text-zinc-200">{asset.title}</span>
        <div data-image-toolbar className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto sm:flex-initial sm:shrink-0 sm:overflow-visible">
          <button
            type="button"
            data-image-pan
            aria-pressed={!selectionMode}
            onClick={() => setSelectionMode(false)}
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-md border transition sm:h-8 sm:w-8 ${!selectionMode ? "border-emerald-600 bg-emerald-600 text-white" : "border-zinc-200 text-zinc-500 hover:bg-zinc-100 dark:border-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-900"}`}
            title={t("viewer.imagePan")}
            aria-label={t("viewer.imagePan")}
          >
            <Hand className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            data-image-region-select
            aria-pressed={selectionMode}
            onClick={toggleSelectionMode}
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-md border transition sm:h-8 sm:w-8 ${selectionMode ? "border-cyan-600 bg-cyan-600 text-white" : "border-zinc-200 text-zinc-500 hover:bg-zinc-100 dark:border-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-900"}`}
            title={t("viewer.regionSelect")}
            aria-label={t("viewer.regionSelect")}
          >
            <SquareDashedMousePointer className="h-3.5 w-3.5" />
          </button>
          {selection ? (
            <button
              type="button"
              data-image-region-clear
              onClick={() => {
                setSelection(null);
                setKeyboardSelectionAnchor(null);
              }}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-950 sm:h-8 sm:w-8 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-white"
              title={t("viewer.regionClear")}
              aria-label={t("viewer.regionClear")}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          ) : null}
          <span className="mx-1 h-5 w-px bg-zinc-200 dark:bg-zinc-800" />
          <button
            type="button"
            onClick={() => changeZoom(-ZOOM_STEP)}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-950 sm:h-8 sm:w-8 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-white"
            title={t("viewer.zoomOut")}
            aria-label={t("viewer.zoomOut")}
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </button>
          <span data-image-zoom className="w-11 shrink-0 text-center text-[10px] font-bold text-zinc-500 dark:text-zinc-400">
            {Math.round(effectiveZoomPercent)}%
          </span>
          <button
            type="button"
            onClick={() => changeZoom(ZOOM_STEP)}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-950 sm:h-8 sm:w-8 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-white"
            title={t("viewer.zoomIn")}
            aria-label={t("viewer.zoomIn")}
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            data-image-fit
            onClick={() => setZoomPercent(null)}
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-md transition sm:h-8 sm:w-8 ${zoomPercent === null ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-950" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-950 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-white"}`}
            title={t("viewer.imageFit")}
            aria-label={t("viewer.imageFit")}
          >
            <Expand className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            data-image-actual-size
            onClick={() => setZoomPercent(100)}
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-md transition sm:h-8 sm:w-8 ${zoomPercent === 100 ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-950" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-950 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-white"}`}
            title={t("viewer.imageActual")}
            aria-label={t("viewer.imageActual")}
          >
            <ScanSearch className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div
        ref={viewportRef}
        data-image-viewport
        className="relative min-h-0 flex-1 overflow-auto overscroll-contain"
      >
        <div
          data-image-scroll-canvas
          className="flex shrink-0 items-center justify-center p-6"
          style={{ width: scrollCanvasWidth, height: scrollCanvasHeight }}
        >
          <div
            ref={surfaceRef}
            data-image-surface
            role="application"
            tabIndex={imageState === "ready" ? 0 : -1}
            aria-label={`${asset.title}. ${selectionMode ? t("viewer.regionSelect") : t("viewer.imagePan")}`}
            className={`relative shrink-0 touch-none select-none bg-white shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 dark:bg-zinc-900 ${selectionMode ? "cursor-crosshair" : "cursor-grab active:cursor-grabbing"}`}
            style={{ width: renderedWidth, height: renderedHeight }}
            onFocus={() => setSurfaceFocused(true)}
            onBlur={() => setSurfaceFocused(false)}
            onKeyDown={handleSurfaceKeyDown}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={(event) => releasePointer(event, true)}
            onPointerCancel={(event) => releasePointer(event, false)}
          >
            {/* The protected BFF route resolves display bytes from the frozen Evidence generation. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              key={imageLoadKey}
              src={imageUrl}
              alt={asset.title}
              draggable={false}
              className={`block h-full w-full object-fill ${imageState === "ready" ? "opacity-100" : "opacity-0"}`}
              onLoad={(event) => {
                const image = event.currentTarget;
                setImageLoadState({
                  key: imageLoadKey,
                  status: isImageNaturalSizeCompatible(
                    displayGeometry,
                    image.naturalWidth,
                    image.naturalHeight,
                  ) ? "ready" : "mismatch",
                });
              }}
              onError={() => setImageLoadState({ key: imageLoadKey, status: "error" })}
            />

            {imageState === "ready" ? (imageLocator?.regions ?? []).map((region, index) => (
              <span
                key={`evidence-${index}`}
                data-image-evidence-region={index}
                className="pointer-events-none absolute z-10 border-2 border-amber-500 bg-amber-300/20 shadow-[0_0_0_1px_rgba(255,255,255,0.85)]"
                style={regionStyle(region)}
              />
            )) : null}
            {imageState === "ready" && (selectionPreview || keyboardSelectionPreview || selection) ? (
              <span
                data-image-selected-region
                className="pointer-events-none absolute z-20 border-2 border-cyan-500 bg-cyan-300/20 shadow-[0_0_0_1px_rgba(255,255,255,0.85)]"
                style={regionStyle(selectionPreview ?? keyboardSelectionPreview ?? selection!)}
              />
            ) : null}
            {imageState === "ready" && selectionMode && surfaceFocused ? (
              <span
                data-image-keyboard-cursor
                className="pointer-events-none absolute z-30 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-cyan-600 shadow"
                style={{ left: `${keyboardCursor.x * 100}%`, top: `${keyboardCursor.y * 100}%` }}
              />
            ) : null}
          </div>
        </div>

        {imageState === "loading" ? (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center gap-2 bg-zinc-100/80 text-xs text-zinc-500 dark:bg-zinc-950/80 dark:text-zinc-400">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>{t("viewer.imageLoading")}</span>
          </div>
        ) : null}
        {imageState === "error" || imageState === "mismatch" ? (
          <div role="alert" data-image-viewer-error="error" className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-zinc-100 px-6 text-center text-rose-600 dark:bg-zinc-950 dark:text-rose-400">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 shrink-0" />
              <p className="text-xs leading-5">
                {imageState === "mismatch" ? t("viewer.imageLocatorMismatch") : t("viewer.imageLoadFailed")}
              </p>
            </div>
            <button
              type="button"
              onClick={retryImage}
              className="min-h-11 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-semibold text-zinc-700 transition hover:bg-zinc-50 sm:min-h-8 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
            >
              {t("viewer.retry")}
            </button>
          </div>
        ) : null}
        {imageState === "ready" && selectionTarget && selectionTarget.processingGeneration > 0 ? (
          <ImageRegionActions
            target={selectionTarget}
            assetTitle={asset.title}
            canAsk={activeThread !== null}
            askQuestion={submitEvidenceQuestion}
            createNote={createEvidenceNote}
            t={t}
          />
        ) : null}
      </div>
    </div>
  );
}
