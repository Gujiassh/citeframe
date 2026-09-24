"use client";
import { useLayoutEffect, useMemo, useSyncExternalStore } from "react";
import { ReindexTracker } from "./reindex-tracker";

export function useReindexTracker(userId: string | undefined) {
  const tracker = useMemo(() => ({ owner: userId, store: new ReindexTracker() }), [userId]);
  const reindexJobs = useSyncExternalStore(tracker.store.subscribe, tracker.store.getSnapshot, tracker.store.getSnapshot);
  useLayoutEffect(() => {
    if (tracker.owner) tracker.store.start();
    return () => tracker.store.stop();
  }, [tracker]);
  return { reindexJobs, reindexAsset: tracker.store.submit, refreshReindexJob: tracker.store.resume };
}
