"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  approveResearchPlan,
  cancelResearchPlan,
  cancelResearchRun,
  createResearchRun,
  getResearchArtifact,
  getResearchArtifactContent,
  getResearchRun,
  listResearchArtifacts,
  listResearchRuns,
  openResearchEventStream,
  resolveResearchConflict,
  retryResearchStep,
  reviseResearchPlan,
} from "@/lib/research/client";
import { canManageResearchRun, latestResearchRun, sortResearchRunsLatest } from "@/lib/research/presentation";
import { runResearchStreamLoop } from "@/lib/research/sse";
import type {
  ResearchArtifactDetail,
  ResearchArtifactSummary,
  ResearchRunDetail,
  ResearchRunSummary,
  ResearchStep,
} from "@/lib/research/types";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

export type ResearchStreamState = "idle" | "connecting" | "live" | "reconnecting" | "history_unavailable" | "contract_error";

type ResearchSnapshot = {
  workspaceId: string;
  run: ResearchRunDetail;
  artifacts: ResearchArtifactSummary[];
  artifactContent: string;
  artifactDetail: ResearchArtifactDetail | null;
  conflictArtifactContent: string;
  conflictArtifactDetail: ResearchArtifactDetail | null;
};

function failureMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

export function useResearch(workspaceId: string, selectedAssetIds: string[], currentUserId: string | null) {
  const workspaceIdRef = useRef(workspaceId);
  const snapshotRef = useRef<ResearchSnapshot | null>(null);
  const [snapshot, setSnapshot] = useState<ResearchSnapshot | null>(null);
  const [runList, setRunList] = useState<{ workspaceId: string; items: ResearchRunSummary[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [streamStatus, setStreamStatus] = useState<{
    workspaceId: string;
    runId: string;
    state: ResearchStreamState;
  } | null>(null);
  const [streamContinuity, setStreamContinuity] = useState<{
    workspaceId: string;
    runId: string;
    historyUnavailable: boolean;
  } | null>(null);
  const [failure, setFailure] = useState<{ workspaceId: string; message: string } | null>(null);
  const currentSnapshot = snapshot?.workspaceId === workspaceId ? snapshot : null;
  const runs = runList?.workspaceId === workspaceId ? runList.items : [];
  const run = currentSnapshot?.run ?? null;
  const artifacts = currentSnapshot?.artifacts ?? [];
  const artifactContent = currentSnapshot?.artifactContent ?? "";
  const artifactDetail = currentSnapshot?.artifactDetail ?? null;
  const conflictArtifactContent = currentSnapshot?.conflictArtifactContent ?? "";
  const conflictArtifactDetail = currentSnapshot?.conflictArtifactDetail ?? null;
  const canManage = canManageResearchRun(run, currentUserId);
  const error = failure?.workspaceId === workspaceId ? failure.message : null;
  const streamState = run && !TERMINAL.has(run.status)
    ? streamContinuity?.workspaceId === workspaceId
        && streamContinuity.runId === run.id
        && streamContinuity.historyUnavailable
      ? "history_unavailable"
      : streamStatus?.workspaceId === workspaceId && streamStatus.runId === run.id
        ? streamStatus.state
        : "connecting"
    : "idle";

  useEffect(() => {
    workspaceIdRef.current = workspaceId;
  }, [workspaceId]);

  useEffect(() => {
    snapshotRef.current = currentSnapshot;
  }, [currentSnapshot]);

  const refreshList = useCallback(async () => {
    if (!workspaceId) return [];
    const payload = await listResearchRuns(workspaceId);
    const items = sortResearchRunsLatest(payload.items);
    if (workspaceIdRef.current === workspaceId) setRunList({ workspaceId, items });
    return items;
  }, [workspaceId]);

  const refresh = useCallback(async (runId: string) => {
    const [runPayload, artifactPayload] = await Promise.all([
      getResearchRun(workspaceId, runId),
      listResearchArtifacts(workspaceId, runId),
    ]);
    const final = artifactPayload.items.find((item) => item.kind === "final_report");
    const conflictDecision = runPayload.run.pendingDecisions.find((item) => item.type === "conflict_resolution");
    const conflict = conflictDecision
      ? artifactPayload.items.find((item) => item.id === conflictDecision.inputArtifactId && item.kind === "conflict_report")
      : undefined;
    if (conflictDecision && !conflict) {
      throw new Error("The pending conflict decision is not bound to an available conflict report.");
    }
    const loadArtifact = async (artifact: ResearchArtifactSummary | undefined) => artifact
      ? Promise.all([
          getResearchArtifactContent(workspaceId, runId, artifact.id),
          getResearchArtifact(workspaceId, runId, artifact.id),
        ])
      : ["", null] as const;
    const [[content, detail], [conflictContent, conflictDetail]] = await Promise.all([
      loadArtifact(final),
      loadArtifact(conflict),
    ]);
    if (conflictDecision && (
      conflictDetail?.artifact.id !== conflictDecision.inputArtifactId
      || conflictDetail.artifact.kind !== "conflict_report"
      || conflictDetail.artifact.sha256 !== conflictDecision.inputArtifactSha256
    )) {
      throw new Error("The conflict report does not match the pending decision.");
    }
    if (workspaceIdRef.current === workspaceId) {
      setSnapshot({
        workspaceId,
        run: runPayload.run,
        artifacts: artifactPayload.items,
        artifactContent: content,
        artifactDetail: detail?.artifact ?? null,
        conflictArtifactContent: conflictContent,
        conflictArtifactDetail: conflictDetail?.artifact ?? null,
      });
      setRunList((current) => {
        if (current?.workspaceId !== workspaceId) return current;
        return {
          ...current,
          items: sortResearchRunsLatest(
            current.items.map((item) => item.id === runPayload.run.id ? runPayload.run : item),
          ),
        };
      });
    }
    return runPayload.run;
  }, [workspaceId]);

  useEffect(() => {
    let cancelled = false;
    if (!workspaceId) return;
    void refreshList()
      .then(async (items) => {
        const latest = latestResearchRun(items);
        if (!cancelled && latest) await refresh(latest.id);
      })
      .catch((reason) => {
        if (!cancelled) setFailure({ workspaceId, message: failureMessage(reason, "Failed to load research runs.") });
      });
    return () => { cancelled = true; };
  }, [refresh, refreshList, workspaceId]);

  const runId = run?.id;
  const runStatus = run?.status;
  useEffect(() => {
    if (!runId || !runStatus || TERMINAL.has(runStatus)) return;
    const controller = new AbortController();
    void runResearchStreamLoop({
      runId,
      afterSeq: snapshotRef.current?.run.id === runId ? snapshotRef.current.run.currentEventSeq : 0,
      signal: controller.signal,
      open: (afterSeq, signal) => {
        setStreamStatus({ workspaceId, runId, state: afterSeq ? "reconnecting" : "connecting" });
        return openResearchEventStream(workspaceId, runId, afterSeq, signal);
      },
      onEvent: () => {
        setStreamStatus({ workspaceId, runId, state: "live" });
        void refresh(runId);
      },
      onReconnect: () => setStreamStatus({ workspaceId, runId, state: "reconnecting" }),
      onHistoryUnavailable: async () => {
        const current = await refresh(runId);
        setStreamContinuity({ workspaceId, runId, historyUnavailable: true });
        return current.currentEventSeq;
      },
      onCursorConflict: async () => (await refresh(runId)).currentEventSeq,
    }).catch((reason) => {
      if (controller.signal.aborted) return;
      setStreamStatus({ workspaceId, runId, state: "contract_error" });
      setFailure({ workspaceId, message: failureMessage(reason, "Research stream contract failed.") });
      void refresh(runId);
    });
    return () => controller.abort();
  }, [refresh, runId, runStatus, workspaceId]);

  const mutate = useCallback(async (action: () => Promise<{ run: ResearchRunDetail }>) => {
    setLoading(true);
    setFailure(null);
    try {
      const payload = await action();
      await Promise.all([refresh(payload.run.id), refreshList()]);
    } catch (reason) {
      setFailure({ workspaceId, message: failureMessage(reason, "Research action failed.") });
    } finally {
      setLoading(false);
    }
  }, [refresh, refreshList, workspaceId]);

  return {
    run,
    runs,
    artifacts,
    artifactContent,
    artifactDetail,
    conflictArtifactContent,
    conflictArtifactDetail,
    canManage,
    loading,
    streamState,
    error,
    start: (question: string) => mutate(() => createResearchRun(workspaceId, question, selectedAssetIds)),
    selectRun: (nextRunId: string) => refresh(nextRunId),
    approve: () => run && canManage ? mutate(() => approveResearchPlan(workspaceId, run)) : Promise.resolve(),
    revisePlan: (question: string, comment: string) => run && canManage
      ? mutate(() => reviseResearchPlan(workspaceId, run, question, comment))
      : Promise.resolve(),
    cancelPlan: () => run && canManage ? mutate(() => cancelResearchPlan(workspaceId, run)) : Promise.resolve(),
    resolveConflict: (action: "exclude_conflicted_claims" | "keep_as_unresolved" | "cancel_run") => run && canManage
      ? mutate(() => resolveResearchConflict(workspaceId, run, action))
      : Promise.resolve(),
    retryStep: (step: ResearchStep) => run && canManage
      ? mutate(() => retryResearchStep(workspaceId, run, step))
      : Promise.resolve(),
    cancel: () => run && canManage ? mutate(() => cancelResearchRun(workspaceId, run)) : Promise.resolve(),
    refresh: () => run ? refresh(run.id) : Promise.resolve(null),
  };
}
