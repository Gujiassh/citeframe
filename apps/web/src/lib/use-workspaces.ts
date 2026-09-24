"use client";

import { useCallback, useEffect, useState } from "react";
import type { MutableRefObject } from "react";

import type { AuthUser } from "@/lib/auth/types";
import { normalizeWorkspaceSummary, pickAccessibleWorkspaceId } from "@/lib/workspaces/normalize";
import type { WorkspaceSettingsResponseDto, CreateWorkspaceResponseDto, WorkspaceListResponseDto } from "@/lib/workspaces/types";
import type { Workspace, WorkspaceSettingsInput } from "./workspace-context";
import type { WorkspaceLocale } from "@/lib/workspaces/normalize";

export type WorkspaceErrorPayload = {
  detail?: string;
  error?: {
    message?: string;
  };
};

export async function readResponseJsonSafely<T>(response: Response): Promise<T | undefined> {
  try {
    return (await response.json()) as T;
  } catch {
    return undefined;
  }
}

export function getWorkspaceErrorMessage(
  payload: WorkspaceErrorPayload | undefined,
  fallback: string,
): string {
  return payload?.error?.message ?? payload?.detail ?? fallback;
}

export function getNextWorkspaceIdAfterDeletion(
  workspaces: Workspace[],
  currentWorkspaceId: string,
  deletedWorkspaceId: string,
): string {
  if (currentWorkspaceId !== deletedWorkspaceId) {
    return currentWorkspaceId;
  }
  return workspaces.find((workspace) => workspace.id !== deletedWorkspaceId)?.id ?? "";
}

export function shouldSyncWorkspaceViewState(
  previousWorkspaceId: string,
  nextWorkspaceId: string,
): boolean {
  return previousWorkspaceId !== nextWorkspaceId;
}

type UseWorkspacesOptions = {
  locale: WorkspaceLocale;
  user: AuthUser | null;
  isAuthHydrating: boolean;
  currentWorkspaceId: string;
  currentWorkspaceIdRef: MutableRefObject<string>;
  setCurrentWorkspaceId: (id: string) => void;
  onWorkspaceSelected: (id: string) => void;
  onWorkspaceCleared: () => void;
};

export function useWorkspaces({
  locale,
  user,
  isAuthHydrating,
  currentWorkspaceId,
  currentWorkspaceIdRef,
  setCurrentWorkspaceId,
  onWorkspaceSelected,
  onWorkspaceCleared,
}: UseWorkspacesOptions) {
  const [isHydrating, setIsHydrating] = useState(true);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);

  const selectWorkspace = useCallback(
    (id: string) => {
      const previousWorkspaceId = currentWorkspaceIdRef.current;
      setCurrentWorkspaceId(id);
      if (shouldSyncWorkspaceViewState(previousWorkspaceId, id)) {
        if (id) {
          onWorkspaceSelected(id);
        } else {
          onWorkspaceCleared();
        }
      }
    },
    [currentWorkspaceIdRef, onWorkspaceCleared, onWorkspaceSelected, setCurrentWorkspaceId],
  );

  useEffect(() => {
    let cancelled = false;

    async function hydrateWorkspaces() {
      if (isAuthHydrating) {
        return;
      }

      if (!user) {
        if (!cancelled) {
          setWorkspaces([]);
          selectWorkspace("");
          setIsHydrating(false);
        }
        return;
      }

      setIsHydrating(true);
      try {
        const response = await fetch("/api/workspaces", { cache: "no-store" });
        const payload = await readResponseJsonSafely<WorkspaceListResponseDto & WorkspaceErrorPayload>(response);
        if (!response.ok) {
          throw new Error(
            getWorkspaceErrorMessage(
              payload,
              locale === "en" ? "Failed to load workspaces." : "加载工作区失败。",
            ),
          );
        }

        const items = (payload?.items ?? []).map((workspace) =>
          normalizeWorkspaceSummary(workspace, locale),
        );

        if (!cancelled) {
          setWorkspaces(items);
          const previousWorkspaceId = currentWorkspaceIdRef.current;
          const nextWorkspaceId = pickAccessibleWorkspaceId(items, previousWorkspaceId);
          setCurrentWorkspaceId(nextWorkspaceId);
          if (nextWorkspaceId && nextWorkspaceId !== previousWorkspaceId) {
            onWorkspaceSelected(nextWorkspaceId);
          } else if (!nextWorkspaceId) {
            onWorkspaceCleared();
          }
        }
      } catch (error) {
        if (!cancelled) {
          console.error(error);
          setWorkspaces([]);
          selectWorkspace("");
        }
      } finally {
        if (!cancelled) {
          setIsHydrating(false);
        }
      }
    }

    void hydrateWorkspaces();

    return () => {
      cancelled = true;
    };
  }, [currentWorkspaceIdRef, isAuthHydrating, locale, onWorkspaceCleared, onWorkspaceSelected, selectWorkspace, setCurrentWorkspaceId, user]);

  const updateWorkspace = useCallback(
    (workspaceId: string, updater: (workspace: Workspace) => Workspace) => {
      setWorkspaces((previous) => previous.map((workspace) =>
        workspace.id === workspaceId ? updater(workspace) : workspace,
      ));
    },
    [],
  );

  const switchWorkspace = useCallback(
    (id: string) => {
      selectWorkspace(id);
    },
    [selectWorkspace],
  );

  const createWorkspace = useCallback(
    async (name: string, description: string | null) => {
      const response = await fetch("/api/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description }),
      });

      const payload = await readResponseJsonSafely<CreateWorkspaceResponseDto & WorkspaceErrorPayload>(response);
      if (!response.ok || !payload?.workspace) {
        throw new Error(
          getWorkspaceErrorMessage(
            payload,
            locale === "en" ? "Failed to create workspace." : "创建工作区失败。",
          ),
        );
      }

      const newWorkspace = normalizeWorkspaceSummary(payload.workspace, locale);
      setWorkspaces((previous) => [...previous, newWorkspace]);
      selectWorkspace(newWorkspace.id);
      return newWorkspace.id;
    },
    [locale, selectWorkspace],
  );

  const deleteWorkspace = useCallback(
    async (id: string): Promise<Workspace[]> => {
      const response = await fetch(`/api/workspaces/${id}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        const payload = await readResponseJsonSafely<WorkspaceErrorPayload>(response);
        throw new Error(
          getWorkspaceErrorMessage(
            payload,
            locale === "en" ? "Failed to delete workspace." : "删除工作区失败。",
          ),
        );
      }

      const nextWorkspaces = workspaces.filter((workspace) => workspace.id !== id);
      setWorkspaces(nextWorkspaces);
      if (currentWorkspaceId === id) {
        selectWorkspace(getNextWorkspaceIdAfterDeletion(nextWorkspaces, currentWorkspaceId, id));
      }
      return nextWorkspaces;
    },
    [currentWorkspaceId, locale, selectWorkspace, workspaces],
  );

  const updateWorkspaceSettings = useCallback(
    async (id: string, settings: WorkspaceSettingsInput) => {
      const response = await fetch(`/api/workspaces/${id}/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      const payload = await readResponseJsonSafely<WorkspaceSettingsResponseDto & WorkspaceErrorPayload>(response);
      if (!response.ok || !payload?.workspace) {
        throw new Error(
          getWorkspaceErrorMessage(
            payload,
            locale === "en" ? "Failed to save workspace settings." : "保存工作区配置失败。",
          ),
        );
      }

      const updatedWorkspace = normalizeWorkspaceSummary(payload.workspace, locale);
      setWorkspaces((previous) => previous.map((workspace) =>
        workspace.id === id ? updatedWorkspace : workspace,
      ));
    },
    [locale],
  );

  const refreshWorkspace = useCallback(async (id: string, signal?: AbortSignal) => {
    const response = await fetch(`/api/workspaces/${encodeURIComponent(id)}`, { cache: "no-store", signal });
    const payload = await readResponseJsonSafely<CreateWorkspaceResponseDto & WorkspaceErrorPayload>(response);
    signal?.throwIfAborted();
    if (!response.ok || !payload?.workspace) throw new Error("Failed to refresh workspace metadata.");
    const updated = normalizeWorkspaceSummary(payload.workspace, locale);
    updateWorkspace(id, () => updated);
  }, [locale, updateWorkspace]);

  const currentWorkspace = workspaces.find((workspace) => workspace.id === currentWorkspaceId) ?? null;

  return {
    isHydrating,
    workspaces,
    currentWorkspace,
    updateWorkspace,
    refreshWorkspace,
    switchWorkspace,
    createWorkspace,
    deleteWorkspace,
    updateWorkspaceSettings,
  };
}
