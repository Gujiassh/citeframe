"use client";

import { useCallback, useEffect, useState } from "react";
import type { Dispatch, MutableRefObject, SetStateAction } from "react";

import type { AuthUser } from "@/lib/auth/types";
import type {
  CreateUploadSessionResponseDto,
  AssetListResponseDto,
  AssetSummaryDto,
  FinalizeUploadResponseDto,
} from "@/lib/assets/types";
import { applyAssetTags } from "@/lib/notes/normalize";
import type { TagDto } from "@/lib/notes/types";
import type { WorkspaceLocale } from "@/lib/workspaces/normalize";
import { getProductionUploadDescriptor } from "@/lib/assets/production-upload";
import type { Asset } from "./workspace-context";
import { getWorkspaceErrorMessage, readResponseJsonSafely } from "./use-workspaces";

export type AssetErrorPayload = {
  detail?: string;
  error?: {
    message?: string;
  };
};

export function formatAssetSize(byteSize: number): string {
  if (byteSize >= 1024 * 1024) {
    return `${(byteSize / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${Math.max(1, Math.round(byteSize / 1024))} KB`;
}

export function normalizeAssetStatus(status: string): Asset["status"] {
  if (["pending_upload", "uploaded", "parsing", "chunking", "chunked", "embedding", "ready", "failed", "deleting", "deleted"].includes(status)) {
    return status as Asset["status"];
  }
  return "failed";
}

export function getAssetProgress(status: Asset["status"]): number {
  switch (status) {
    case "pending_upload":
      return 10;
    case "uploaded":
      return 25;
    case "parsing":
      return 50;
    case "chunking":
      return 75;
    case "chunked":
      return 100;
    case "embedding":
      return 90;
    case "ready":
      return 100;
    case "failed":
      return 100;
    case "deleting":
      return 100;
    case "deleted":
      return 100;
  }
}

export function toUiAsset(asset: AssetSummaryDto): Asset {
  const status = normalizeAssetStatus(asset.status);
  return {
    id: asset.id,
    workspaceId: asset.workspaceId,
    kind: asset.kind,
    title: asset.title,
    sourceFilename: asset.sourceFilename,
    mimeType: asset.mimeType,
    size: formatAssetSize(asset.byteSize),
    status,
    currentProcessingGeneration: asset.currentProcessingGeneration,
    progress: getAssetProgress(status),
    errorMsg: asset.lastErrorMessage ?? undefined,
    tags: [],
    createdAt: asset.createdAt,
  };
}

function sameStringArray(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function sameAssetSnapshot(left: Asset, right: Asset): boolean {
  return (
    left.id === right.id
    && left.workspaceId === right.workspaceId
    && left.kind === right.kind
    && left.title === right.title
    && left.sourceFilename === right.sourceFilename
    && left.mimeType === right.mimeType
    && left.size === right.size
    && left.status === right.status
    && left.currentProcessingGeneration === right.currentProcessingGeneration
    && left.progress === right.progress
    && left.errorMsg === right.errorMsg
    && left.createdAt === right.createdAt
    && sameStringArray(left.tags, right.tags)
  );
}

export function replaceAssetsForWorkspace(
  workspaceId: string,
  workspaceAssets: Asset[],
  baseAssets: Asset[],
): Asset[] {
  const previousById = new Map(
    baseAssets
      .filter((asset) => asset.workspaceId === workspaceId)
      .map((asset) => [asset.id, asset]),
  );
  const stableWorkspaceAssets = workspaceAssets.map((asset) => {
    const previous = previousById.get(asset.id);
    return previous && sameAssetSnapshot(previous, asset) ? previous : asset;
  });
  const nextAssets = [
    ...baseAssets.filter((asset) => asset.workspaceId !== workspaceId),
    ...stableWorkspaceAssets,
  ];

  return nextAssets.length === baseAssets.length
    && nextAssets.every((asset, index) => asset === baseAssets[index])
    ? baseAssets
    : nextAssets;
}

export function applyTagRelationsToAssets(
  workspaceId: string,
  assets: Asset[],
  tagRelations: TagDto[],
): Asset[] {
  const workspaceAssets = assets.filter((asset) => asset.workspaceId === workspaceId);
  return replaceAssetsForWorkspace(
    workspaceId,
    applyAssetTags(workspaceAssets, tagRelations),
    assets,
  );
}

type UseAssetsOptions = {
  locale: WorkspaceLocale;
  user: AuthUser | null;
  isAuthHydrating: boolean;
  currentWorkspaceId: string;
  tagRelationsRef: MutableRefObject<TagDto[]>;
  assetsRef: MutableRefObject<Asset[]>;
  syncAssetViewState: (workspaceId: string, assets: Asset[]) => void;
  closeAsset: (id: string) => void;
  updateWorkspace: (workspaceId: string, updater: (workspace: import("./workspace-context").Workspace) => import("./workspace-context").Workspace) => void;
};

export function useAssets({
  locale,
  user,
  isAuthHydrating,
  currentWorkspaceId,
  tagRelationsRef,
  assetsRef,
  syncAssetViewState,
  closeAsset,
  updateWorkspace,
}: UseAssetsOptions) {
  const [assets, setAssetsState] = useState<Asset[]>([]);

  const setAssets: Dispatch<SetStateAction<Asset[]>> = useCallback(
    (update) => {
      setAssetsState((previous) => {
        const nextAssets = typeof update === "function" ? update(previous) : update;
        assetsRef.current = nextAssets;
        return nextAssets;
      });
    },
    [assetsRef],
  );

  useEffect(() => {
    assetsRef.current = assets;
  }, [assets, assetsRef]);

  useEffect(() => {
    let cancelled = false;

    async function hydrateAssets() {
      if (isAuthHydrating) {
        return;
      }
      if (!user) {
        setAssets([]);
        tagRelationsRef.current = [];
        return;
      }
      if (!currentWorkspaceId) {
        return;
      }

      const workspaceId = currentWorkspaceId;
      try {
        const response = await fetch(`/api/workspaces/${workspaceId}/assets`, { cache: "no-store" });
        const payload = await readResponseJsonSafely<AssetListResponseDto & AssetErrorPayload>(response);
        if (!response.ok) {
          throw new Error(
            getWorkspaceErrorMessage(
              payload,
              locale === "en" ? "Failed to load assets." : "加载文档列表失败。",
            ),
          );
        }

        const workspaceAssets = applyAssetTags(
          (payload?.items ?? []).map(toUiAsset),
          tagRelationsRef.current,
        );
        if (!cancelled) {
          const nextAssets = replaceAssetsForWorkspace(workspaceId, workspaceAssets, assetsRef.current);
          setAssets(nextAssets);
          updateWorkspace(workspaceId, (workspace) => workspace.assetCount === workspaceAssets.length
            ? workspace
            : { ...workspace, assetCount: workspaceAssets.length });
          syncAssetViewState(workspaceId, nextAssets);
        }
      } catch (error) {
        if (!cancelled) {
          console.error(error);
        }
      }
    }

    void hydrateAssets();

    return () => {
      cancelled = true;
    };
  }, [currentWorkspaceId, isAuthHydrating, locale, setAssets, syncAssetViewState, tagRelationsRef, updateWorkspace, user, assetsRef]);

  useEffect(() => {
    if (isAuthHydrating || !user || !currentWorkspaceId) {
      return;
    }

    const hasProcessingAsset = assets.some(
      (asset) => asset.workspaceId === currentWorkspaceId && !["chunked", "ready", "failed", "deleted"].includes(asset.status),
    );
    if (!hasProcessingAsset) {
      return;
    }

    const refreshAssets = async () => {
      try {
        const response = await fetch(`/api/workspaces/${currentWorkspaceId}/assets`, { cache: "no-store" });
        const payload = await readResponseJsonSafely<AssetListResponseDto & AssetErrorPayload>(response);
        if (!response.ok || !payload) {
          return;
        }
        const workspaceAssets = applyAssetTags(
          payload.items.map(toUiAsset),
          tagRelationsRef.current,
        );
        const nextAssets = replaceAssetsForWorkspace(currentWorkspaceId, workspaceAssets, assetsRef.current);
        setAssets(nextAssets);
        updateWorkspace(currentWorkspaceId, (workspace) => workspace.assetCount === workspaceAssets.length
          ? workspace
          : { ...workspace, assetCount: workspaceAssets.length });
      } catch (error) {
        console.error(error);
      }
    };

    const timer = window.setInterval(() => {
      void refreshAssets();
    }, 1_500);

    return () => {
      window.clearInterval(timer);
    };
  }, [currentWorkspaceId, assets, assetsRef, isAuthHydrating, setAssets, tagRelationsRef, updateWorkspace, user]);

  const uploadAsset = useCallback(
    async (file: File) => {
      const workspaceId = currentWorkspaceId;
      if (!workspaceId) {
        return;
      }
      const uploadDescriptor = getProductionUploadDescriptor(file);
      if (!uploadDescriptor) {
        throw new Error(
          locale === "en"
            ? "Choose a PDF, PNG, JPEG, WebP, or Markdown file."
            : "请选择 PDF、PNG、JPEG、WebP 或 Markdown 文件。",
        );
      }

      const uploadSessionResponse = await fetch(`/api/workspaces/${workspaceId}/assets/upload-session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sourceFilename: file.name,
          mimeType: uploadDescriptor.mimeType,
          byteSize: file.size,
        }),
      });

      const uploadSessionPayload = await readResponseJsonSafely<CreateUploadSessionResponseDto & AssetErrorPayload>(uploadSessionResponse);
      if (!uploadSessionResponse.ok || !uploadSessionPayload?.asset || !uploadSessionPayload?.upload.url) {
        throw new Error(
          getWorkspaceErrorMessage(
            uploadSessionPayload,
            locale === "en" ? "Failed to create upload session." : "创建上传会话失败。",
          ),
        );
      }

      const pendingAsset = toUiAsset(uploadSessionPayload.asset);
      setAssets((previous) => [
        pendingAsset,
        ...previous.filter((asset) => asset.id !== pendingAsset.id),
      ]);
      updateWorkspace(workspaceId, (workspace) => ({
        ...workspace,
        assetCount: workspace.assetCount + 1,
      }));

      const uploadResponse = await fetch(uploadSessionPayload.upload.url, {
        method: uploadSessionPayload.upload.method,
        headers: uploadSessionPayload.upload.headers,
        body: file,
      });
      if (!uploadResponse.ok) {
        const uploadPayload = await readResponseJsonSafely<AssetErrorPayload>(uploadResponse);
        throw new Error(
          getWorkspaceErrorMessage(
            uploadPayload,
            locale === "en" ? "Failed to upload file." : "上传文件失败。",
          ),
        );
      }

      const finalizeResponse = await fetch(`/api/workspaces/${workspaceId}/assets/${pendingAsset.id}/finalize-upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ objectKey: uploadSessionPayload.upload.objectKey }),
      });
      const finalizePayload = await readResponseJsonSafely<FinalizeUploadResponseDto & AssetErrorPayload>(finalizeResponse);
      if (!finalizeResponse.ok || !finalizePayload?.asset) {
        throw new Error(
          getWorkspaceErrorMessage(
            finalizePayload,
            locale === "en" ? "Failed to finalize upload." : "确认上传失败。",
          ),
        );
      }

      const uploadedAsset = toUiAsset(finalizePayload.asset);
      setAssets((previous) => [
        uploadedAsset,
        ...previous.filter((asset) => asset.id !== uploadedAsset.id),
      ]);
    },
    [currentWorkspaceId, locale, setAssets, updateWorkspace],
  );

  const deleteAsset = useCallback(
    async (id: string) => {
      const workspaceId = currentWorkspaceId;
      if (!workspaceId) {
        return;
      }

      const response = await fetch(`/api/workspaces/${workspaceId}/assets/${id}`, {
        method: "DELETE",
      });
      const payload = await readResponseJsonSafely<FinalizeUploadResponseDto & AssetErrorPayload>(response);
      if (!response.ok || !payload?.asset) {
        throw new Error(
          getWorkspaceErrorMessage(
            payload,
            locale === "en" ? "Failed to delete asset." : "删除文档失败。",
          ),
        );
      }

      const previousAsset = assetsRef.current.find((asset) => asset.id === id);
      const deletingAsset = toUiAsset(payload.asset);
      setAssets((previous) => previous.map((asset) =>
        asset.id === id
          ? { ...deletingAsset, tags: previousAsset?.tags ?? asset.tags }
          : asset,
      ));
      closeAsset(id);
    },
    [closeAsset, currentWorkspaceId, assetsRef, locale, setAssets],
  );

  const retryAsset = useCallback(
    async (id: string) => {
      const workspaceId = currentWorkspaceId;
      if (!workspaceId) {
        return;
      }

      const response = await fetch(`/api/workspaces/${workspaceId}/assets/${id}/retry`, {
        method: "POST",
      });
      const payload = await readResponseJsonSafely<FinalizeUploadResponseDto & AssetErrorPayload>(response);
      if (!response.ok || !payload?.asset) {
        throw new Error(
          getWorkspaceErrorMessage(
            payload,
            locale === "en" ? "Failed to retry asset ingestion." : "重新入库失败。",
          ),
        );
      }

      const previousAsset = assetsRef.current.find((asset) => asset.id === id);
      const retriedAsset = toUiAsset(payload.asset);
      setAssets((previous) => previous.map((asset) =>
        asset.id === id
          ? { ...retriedAsset, tags: previousAsset?.tags ?? asset.tags }
          : asset,
      ));
    },
    [currentWorkspaceId, assetsRef, locale, setAssets],
  );

  const retryDeleteAsset = useCallback(
    async (id: string) => {
      const workspaceId = currentWorkspaceId;
      if (!workspaceId) {
        return;
      }

      const response = await fetch(`/api/workspaces/${workspaceId}/assets/${id}/delete-retry`, {
        method: "POST",
      });
      const payload = await readResponseJsonSafely<FinalizeUploadResponseDto & AssetErrorPayload>(response);
      if (!response.ok || !payload?.asset) {
        throw new Error(
          getWorkspaceErrorMessage(
            payload,
            locale === "en" ? "Failed to retry asset deletion." : "重试删除失败。",
          ),
        );
      }

      const previousAsset = assetsRef.current.find((asset) => asset.id === id);
      const deletingAsset = toUiAsset(payload.asset);
      setAssets((previous) => previous.map((asset) =>
        asset.id === id
          ? { ...deletingAsset, tags: previousAsset?.tags ?? asset.tags }
          : asset,
      ));
    },
    [currentWorkspaceId, assetsRef, locale, setAssets],
  );

  const removeWorkspace = useCallback(
    (workspaceId: string) => {
      setAssets(assetsRef.current.filter((asset) => asset.workspaceId !== workspaceId));
    },
    [assetsRef, setAssets],
  );

  const applyTagRelations = useCallback(
    (workspaceId: string, tagRelations: TagDto[]) => {
      setAssets((previous) => applyTagRelationsToAssets(workspaceId, previous, tagRelations));
    },
    [setAssets],
  );

  const updateAssetTags = useCallback(
    (assetId: string, tagNames: string[]) => {
      setAssets((previous) => previous.map((asset) =>
        asset.id === assetId ? { ...asset, tags: tagNames } : asset,
      ));
    },
    [setAssets],
  );

  const removeTagName = useCallback(
    (workspaceId: string, tagName: string) => {
      setAssets((previous) => previous.map((asset) => ({
        ...asset,
        tags: asset.workspaceId === workspaceId
          ? asset.tags.filter((name) => name !== tagName)
          : asset.tags,
      })));
    },
    [setAssets],
  );

  return {
    assets,
    assetsRef,
    uploadAsset,
    deleteAsset,
    retryAsset,
    retryDeleteAsset,
    removeWorkspace,
    applyTagRelations,
    updateAssetTags,
    removeTagName,
  };
}
