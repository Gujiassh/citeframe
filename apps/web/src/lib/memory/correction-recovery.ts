import type { AvailableMemory, Memory, Statement } from "./types";
import type { PendingMutation } from "./client";

export type Identity = { id: string; version: number };
export type ChainNode = Identity & Pick<AvailableMemory, "supersedesId" | "intent" | "validity" | "displayStatus">;
export type SuccessorProof = { nodes: ChainNode[]; original: AvailableMemory; candidate: AvailableMemory };
export type CorrectionOutcome = { epoch: number; requestId: string; method: PendingMutation["method"]; path: string; kind: "success" | "unknown" | "failure"; code?: string };
export type RecoveryPhase = "editing" | "submitting" | "unknown" | "conflict" | "checking" | "compare-ready" | "rechecking-adoption" | "editing-adopted";
export type Recovery = {
  epoch: number; generation: number; candidateGeneration: number; phase: RecoveryPhase;
  original: Identity; target: Identity; lastAttempted?: Identity; draft: Statement; candidateId?: string; proof?: SuccessorProof;
  participants: string[]; error?: "relationship" | "limit" | "read" | "changed";
  attempted?: Identity & { requestId: string; method: "POST"; path: string; generation: number };
};
export class RecoveryProofError extends Error {
  constructor(public readonly code: "relationship" | "limit" | "read", public readonly id?: string, public readonly unavailable?: "erased" | "source_unavailable" | "not_found") { super(code); }
}
export function statementOf(memory: AvailableMemory): Statement {
  return { kind: memory.kind, content: memory.content, conditions: { ...memory.conditions }, pinned: memory.pinned, validUntil: memory.validUntil };
}
export function participantIds(state: Recovery): string[] { return [...new Set([state.original.id, state.target.id, ...state.participants])]; }
export function correctionOutcome(state: Recovery, event: CorrectionOutcome): Recovery | null {
  const attempt = state.attempted;
  if (!attempt || state.epoch !== event.epoch || attempt.generation !== state.generation || attempt.requestId !== event.requestId || attempt.method !== event.method || attempt.path !== event.path) return state;
  if (event.kind === "success") return null;
  if (event.kind === "unknown") return { ...state, phase: "unknown" };
  if (["erased", "memory_not_found", "source_version_unavailable", "source_not_found"].includes(event.code ?? "")) return null;
  const conflict = event.code === "version_conflict" || event.code === "terminal_memory";
  return { ...state, phase: conflict ? "conflict" : "editing", proof: undefined, candidateId: undefined, attempted: undefined };
}
function node(memory: AvailableMemory): ChainNode {
  return { id: memory.id, version: memory.version, supersedesId: memory.supersedesId, intent: memory.intent, validity: memory.validity, displayStatus: memory.displayStatus };
}
export function readableCurrent(memory: Memory, id: string, actor: string, workspaceId: string, suppressed: (id: string) => boolean): AvailableMemory {
  if (memory.id !== id) throw new RecoveryProofError("relationship");
  if (!memory.contentAvailable) throw new RecoveryProofError("relationship", id, memory.reason);
  if (suppressed(id)) throw new RecoveryProofError("relationship", id, "source_unavailable");
  if (memory.ownerUserId !== actor || memory.workspaceId !== workspaceId) throw new RecoveryProofError("relationship");
  return memory;
}
export async function proveSuccessor(candidateId: string, originalId: string, read: (id: string) => Promise<AvailableMemory>): Promise<SuccessorProof> {
  if (candidateId === originalId) throw new RecoveryProofError("relationship");
  const nodes: ChainNode[] = [];
  let id: string | null = candidateId;
  let candidate: AvailableMemory | undefined;
  while (id !== null) {
    if (nodes.some(item => item.id === id)) throw new RecoveryProofError("relationship");
    if (nodes.length === 9) throw new RecoveryProofError("limit");
    const current = await read(id);
    if (current.id !== id || current.intent !== (nodes.length === 0 ? "active" : "superseded")) throw new RecoveryProofError("relationship");
    candidate ??= current;
    nodes.push(node(current));
    if (id === originalId) return { nodes, original: current, candidate };
    id = current.supersedesId;
  }
  throw new RecoveryProofError("relationship");
}
function comparison(memory: AvailableMemory) {
  return { ...node(memory), statement: statementOf(memory), sources: memory.sourceRefs.map(ref => ({ sourceId: ref.sourceId, sourceVersion: ref.sourceVersion, contentSha256: ref.contentSha256, span: ref.span })) };
}
export function sameProof(left: SuccessorProof, right: SuccessorProof): boolean {
  return JSON.stringify({ nodes: left.nodes, original: comparison(left.original), candidate: comparison(left.candidate) }) === JSON.stringify({ nodes: right.nodes, original: comparison(right.original), candidate: comparison(right.candidate) });
}
export async function recheckSuccessor(shown: SuccessorProof, read: (id: string) => Promise<AvailableMemory>): Promise<{ proof: SuccessorProof; unchanged: boolean }> {
  const proof = await proveSuccessor(shown.candidate.id, shown.original.id, read);
  const final = await read(proof.candidate.id);
  if (final.intent !== "active" || final.id !== proof.candidate.id) throw new RecoveryProofError("relationship");
  if (final.supersedesId !== proof.nodes[0].supersedesId) throw new RecoveryProofError("relationship");
  const fresh = { ...proof, candidate: final, nodes: [node(final), ...proof.nodes.slice(1)] };
  return { proof: fresh, unchanged: sameProof(shown, proof) && sameProof(proof, fresh) };
}
