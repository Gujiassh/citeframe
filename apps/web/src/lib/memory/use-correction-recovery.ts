"use client";
import { useEffect, useRef, useState } from "react";
import { memoryRequest, type PendingMutation } from "./client";
import { correctionOutcome, participantIds, proveSuccessor, readableCurrent, recheckSuccessor, RecoveryProofError, statementOf, type CorrectionOutcome, type Recovery } from "./correction-recovery";
import { MemoryError } from "./errors";
import { validResponse } from "./response";
import { useMemorySession } from "./session-context";
import type { UnavailableTarget } from "./use-memory-management";
import type { AvailableMemory, Memory, Statement } from "./types";

type Options = {
  workspaceId: string; unavailable: Record<string, UnavailableTarget>; outcome: CorrectionOutcome | null; completed: number; locked: boolean; selectedId: string | null; clearSelection: () => void;
  invalidate: (id: string, reason: UnavailableTarget) => void; report: (error: unknown) => void;
  mutate: (path: string, method: PendingMutation["method"], body: Record<string, unknown>) => PendingMutation | null;
};
export function useCorrectionRecovery({ workspaceId, unavailable, outcome, completed, locked, selectedId, clearSelection, invalidate, report, mutate }: Options) {
  const { epoch, actor } = useMemorySession(workspaceId);
  const [state, setState] = useState<Recovery | null>(null);
  const [seenOutcome, setSeenOutcome] = useState(outcome);
  const [seenCompleted, setSeenCompleted] = useState(completed);
  const nextGeneration = useRef(0);
  const nextCandidate = useRef(0);
  const work = useRef<AbortController | null>(null);
  const actionLock = useRef(false);
  const privateLoss = state && (state.epoch !== epoch || participantIds(state).some(id => unavailable[id]));
  if (seenCompleted !== completed) { work.current?.abort(); work.current = null; actionLock.current = false; setSeenCompleted(completed); setState(null); }
  if (privateLoss) {
    work.current?.abort(); work.current = null; actionLock.current = false;
    if (state.candidateId || (selectedId && !unavailable[selectedId])) clearSelection();
    setState(null);
  }
  if (seenOutcome !== outcome) {
    setSeenOutcome(outcome);
    if (outcome && state && !privateLoss && seenCompleted === completed) setState(correctionOutcome(state, outcome));
  }
  useEffect(() => () => { work.current?.abort(); }, []);
  const visible = privateLoss || seenCompleted !== completed ? null : state;
  const cancel = () => { work.current?.abort(); actionLock.current = false; clearSelection(); setState(null); };
  const begin = (memory: AvailableMemory) => {
    if (locked || visible || unavailable[memory.id] || memory.ownerUserId !== actor || memory.workspaceId !== workspaceId) return;
    work.current?.abort();
    const identity = { id: memory.id, version: memory.version };
    setState({ epoch, generation: ++nextGeneration.current, candidateGeneration: 0, phase: "editing", original: identity, target: identity, draft: statementOf(memory), participants: [memory.id] });
  };
  const change = (draft: Statement) => {
    if (!visible || locked || actionLock.current) return;
    const recovering = visible.phase !== "editing" && visible.phase !== "editing-adopted";
    setState({ ...visible, draft, generation: ++nextGeneration.current, phase: recovering ? "conflict" : visible.phase, proof: recovering ? undefined : visible.proof, attempted: undefined });
  };
  const submit = () => {
    if (!visible || locked || actionLock.current || !["editing", "editing-adopted"].includes(visible.phase)) return;
    const path = `memories/${visible.target.id}/corrections`;
    const operation = mutate(path, "POST", { ...visible.draft, expectedVersion: visible.target.version });
    if (operation) setState({ ...visible, phase: "submitting", lastAttempted: { ...visible.target }, attempted: { ...visible.target, method: "POST", path, requestId: operation.requestId, generation: visible.generation } });
  };
  const check = async (candidateId: string, adopting: boolean) => {
    if (!visible || locked || (adopting && actionLock.current)) return;
    if (adopting ? visible.phase !== "compare-ready" || !visible.proof : !["conflict", "checking", "compare-ready", "rechecking-adoption"].includes(visible.phase)) return;
    work.current?.abort();
    const controller = new AbortController(); work.current = controller;
    actionLock.current = true;
    const generation = visible.generation, candidateGeneration = ++nextCandidate.current;
    const matches = (current: Recovery | null): current is Recovery => !!current && current.epoch === epoch && current.generation === generation && current.candidateGeneration === candidateGeneration && !controller.signal.aborted;
    const captured = { ...visible, candidateId, candidateGeneration, phase: adopting ? "rechecking-adoption" as const : "checking" as const, proof: adopting ? visible.proof : undefined, error: undefined };
    setState(captured);
    const read = async (id: string) => {
      if (controller.signal.aborted) throw new RecoveryProofError("read");
      try {
        const payload = await memoryRequest<{ memory: Memory }>(workspaceId, `memories/${id}`, controller.signal);
        if (controller.signal.aborted) throw new RecoveryProofError("read");
        if (!actor || !validResponse("current", payload, workspaceId, actor, id)) throw new RecoveryProofError("relationship");
        return readableCurrent(payload.memory, id, actor, workspaceId, target => !!unavailable[target]);
      } catch (error) {
        if (controller.signal.aborted) throw error;
        if (error instanceof MemoryError) {
          const code = error.detail.code;
          if (["erased", "memory_not_found", "source_version_unavailable", "source_not_found"].includes(code)) throw new RecoveryProofError("relationship", id, code === "erased" ? "erased" : code === "memory_not_found" ? "not_found" : "source_unavailable");
        }
        throw error;
      }
    };
    try {
      const result = adopting ? await recheckSuccessor(visible.proof!, read) : { proof: await proveSuccessor(candidateId, visible.original.id, read), unchanged: false };
      setState(current => !matches(current) ? current : { ...current, proof: result.proof,
        participants: [...new Set([...current.participants, ...result.proof.nodes.map(node => node.id)])],
        target: adopting && result.unchanged ? { id: result.proof.candidate.id, version: result.proof.candidate.version } : current.target,
        phase: adopting && result.unchanged ? "editing-adopted" : "compare-ready", error: adopting && !result.unchanged ? "changed" : undefined });
    } catch (error) {
      if (!controller.signal.aborted && work.current === controller) {
        if (error instanceof RecoveryProofError && error.id && error.unavailable) {
          if (participantIds(captured).includes(error.id)) clearSelection();
          invalidate(error.id, error.unavailable);
        }
        else if (error instanceof MemoryError) report(error);
        setState(current => !matches(current) ? current : { ...current, phase: "conflict", proof: undefined, error: error instanceof RecoveryProofError ? error.code : "read" });
      }
    } finally { if (work.current === controller) actionLock.current = false; }
  };
  const recovering = !!visible && !["editing", "editing-adopted", "submitting", "unknown"].includes(visible.phase);
  return { state: visible, begin, change, submit, cancel, recovering,
    refresh: () => { if (visible?.candidateId && recovering) void check(visible.candidateId, false); },
    choose: (id: string) => { if (recovering) void check(id, false); },
    adopt: () => { if (visible?.candidateId) void check(visible.candidateId, true); },
  };
}
