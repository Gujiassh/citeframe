"use client";

import { useCallback, useLayoutEffect, useMemo, useSyncExternalStore } from "react";
import type { AssetSummaryDto } from "./types";
import { UploadQueue } from "./upload-queue";
import { createAssetUploadTask } from "./upload-task";

type Options = {
  userId: string | undefined;
  workspaceId: string;
  locale: "zh" | "en";
  onAsset: (asset: AssetSummaryDto, created: boolean) => void;
};

export function useUploadQueue({ userId, workspaceId, locale, onAsset }: Options) {
  // Each authenticated owner has a separate in-memory queue and abort lifetime.
  const queue = useMemo(() => ({ owner: userId, store: new UploadQueue() }), [userId]);
  const items = useSyncExternalStore(queue.store.subscribe, queue.store.getSnapshot, queue.store.getSnapshot);
  useLayoutEffect(() => {
    if (queue.owner) queue.store.start();
    return () => queue.store.stop();
  }, [queue]);
  const enqueueUploads = useCallback((files: readonly File[]) => {
    queue.store.enqueue(workspaceId, files, (file) => createAssetUploadTask({ file, workspaceId, locale, onAsset }));
  }, [queue, workspaceId, locale, onAsset]);
  const removeUploadsWorkspace = useCallback((id: string) => queue.store.removeWorkspace(id), [queue]);
  return { uploadQueue: items, enqueueUploads, retryUpload: queue.store.retry, removeUploadsWorkspace };
}
