"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ModelSettingsError, modelSettingsRequest } from "./client";
import type { ModelSettingsPatch, WorkspaceModelSettings } from "./types";

export function useModelSettings(workspaceId: string, refreshWorkspace: (id: string, signal?: AbortSignal) => Promise<void>, completedReindexes: string) {
  const [settings, setSettings] = useState<WorkspaceModelSettings | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);
  const [formVersion, setFormVersion] = useState(0);
  const requestRef = useRef<AbortController | null>(null);
  const loadRef = useRef<AbortController | null>(null);
  const savingRef = useRef(false);

  useEffect(() => {
    if (savingRef.current) return;
    const controller = new AbortController(); loadRef.current = controller;
    void modelSettingsRequest(workspaceId, controller.signal).then((value) => {
      setSettings(value); setError(null);
    }).catch((error: Error) => { if (!controller.signal.aborted) setError(error); });
    return () => controller.abort();
  }, [workspaceId, reloadVersion, completedReindexes]);
  useEffect(() => () => requestRef.current?.abort(), [workspaceId]);

  const clearSaved = useCallback(() => setSaved(false), []);
  const reload = useCallback(() => {
    setSaved(false);
    setFormVersion((version) => version + 1);
    setReloadVersion((version) => version + 1);
  }, []);
  const save = useCallback(async (patch: ModelSettingsPatch) => {
    if (savingRef.current) return false;
    savingRef.current = true;
    loadRef.current?.abort();
    requestRef.current?.abort();
    const controller = new AbortController(); requestRef.current = controller;
    setBusy(true); setError(null); setSaved(false);
    try {
      const value = await modelSettingsRequest(workspaceId, controller.signal, patch);
      setSettings(value); setSaved(true);
      setReloadVersion((version) => version + 1);
      // Model settings have committed even if the separate summary refresh fails.
      void refreshWorkspace(workspaceId, controller.signal).catch(() => {
        if (!controller.signal.aborted) setError(new Error("Settings saved. Reload workspace metadata."));
      });
      return true;
    } catch (error) {
      if (!controller.signal.aborted) setError(error instanceof Error ? error : new Error("Model settings request failed."));
      return false;
    } finally {
      savingRef.current = false;
      if (!controller.signal.aborted) setBusy(false);
    }
  }, [workspaceId, refreshWorkspace]);
  return { settings, busy, saved, clearSaved, error, conflict: error instanceof ModelSettingsError && error.status === 409, reload, save, formVersion };
}
