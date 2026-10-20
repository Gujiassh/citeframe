import test from "node:test";
import assert from "node:assert/strict";
import { correctionOutcome, participantIds, proveSuccessor, readableCurrent, recheckSuccessor, RecoveryProofError, sameProof, statementOf, type Recovery } from "./correction-recovery";
import type { AvailableMemory, Memory } from "./types";
const originalId = "P";
const make = (id: string, supersedesId: string | null, intent: AvailableMemory["intent"] = "superseded"): AvailableMemory => ({
  id, supersedesId, intent, version: 1, validity: "valid", displayStatus: intent === "superseded" ? "superseded" : "active", contentAvailable: true,
  workspaceId: "workspace", ownerUserId: "actor", visibility: "private", scope: { kind: "workspace", threadId: null, runId: null }, revisionId: id,
  kind: "constraint", confirmation: "explicit_remember", conditions: { subject: " 原文主体 ", applicability: "α\n约束", effectiveFrom: "2026-09-29T00:00:00Z" },
  pinned: true, validUntil: "2030-01-01T00:00:00Z", createdAt: "2026-09-29T00:00:00Z", updatedAt: "2026-09-29T00:00:00Z", content: "  Exact\n原文  ", sourceRefs: [{ sourceId: id, sourceVersion: 1, contentSha256: "a".repeat(64), span: null }],
});
const original = make(originalId, null);
const candidate = make("C", originalId, "active");
const reader = (rows: AvailableMemory[], calls: string[]) => async (id: string) => { calls.push(id); const memory = rows.find(row => row.id === id); if (!memory) throw new RecoveryProofError("read", id, "not_found"); return memory; };
const editing = (): Recovery => ({ epoch: 2, generation: 4, candidateGeneration: 1, phase: "submitting", original: { id: originalId, version: 1 }, target: { id: "C", version: 2 }, participants: [originalId, "C"], draft: statementOf(original), attempted: { id: "C", version: 2, path: "memories/C/corrections", method: "POST", requestId: "request", generation: 4 } });

test("successor proof uses backward identities and keeps intermediate bodies out of metadata", async () => {
  const calls: string[] = [];
  const proof = await proveSuccessor("C", originalId, reader([original, make("Q", originalId), { ...candidate, supersedesId: "Q" }], calls));
  assert.deepEqual(calls, ["C", "Q", originalId]);
  assert.deepEqual(Object.keys(proof.nodes[1]).sort(), ["displayStatus", "id", "intent", "supersedesId", "validity", "version"]);
  assert.equal(proof.original, original); assert.equal(proof.candidate.id, "C");
});
test("selection permits exactly eight edges/nine actual GETs; adoption exactly ten GETs and no extra distinct node", async () => {
  const rows = [original]; for (let i = 1; i <= 8; i++) rows.push(make(`N${i}`, i === 1 ? originalId : `N${i - 1}`, i === 8 ? "active" : "superseded"));
  const selection: string[] = [];
  const proof = await proveSuccessor("N8", originalId, reader(rows, selection));
  assert.equal(selection.length, 9); assert.equal(new Set(selection).size, 9);
  const adoption: string[] = [];
  const result = await recheckSuccessor(proof, reader(rows, adoption));
  assert.equal(result.unchanged, true); assert.equal(adoption.length, 10); assert.equal(new Set(adoption).size, 9); assert.equal(adoption.at(-1), "N8");
});
test("over-limit chain stops at nine actual GETs without fetching tenth distinct node", async () => {
  const rows = [original]; for (let i = 1; i <= 9; i++) rows.push(make(`N${i}`, i === 1 ? originalId : `N${i - 1}`, i === 9 ? "active" : "superseded"));
  const calls: string[] = [];
  await assert.rejects(proveSuccessor("N9", originalId, reader(rows, calls)), (error: unknown) => error instanceof RecoveryProofError && error.code === "limit");
  assert.equal(calls.length, 9); assert.ok(!calls.includes(originalId));
});
test("same identity, no relation, cycles, stale active row and unsuperseded parent fail without retries", async () => {
  for (const [id, rows] of [[originalId, [original]], ["C", [{ ...candidate, supersedesId: null }]], ["C", [{ ...candidate, supersedesId: "Q" }, make("Q", "C")]], ["C", [{ ...candidate, intent: "superseded" }]], ["C", [candidate, { ...original, intent: "active" }]]] as [string, AvailableMemory[]][]) {
    const calls: string[] = []; await assert.rejects(proveSuccessor(id, originalId, reader(rows, calls)), RecoveryProofError);
    assert.equal(calls.length, new Set(calls).size); assert.ok(calls.length <= 2);
  }
});
test("readable guard binds owner/workspace/endpoint and never infers a link from unavailable data", () => {
  for (const memory of [{ ...candidate, id: "other" }, { ...candidate, ownerUserId: "other" }, { ...candidate, workspaceId: "other" }] as Memory[]) assert.throws(() => readableCurrent(memory, "C", "actor", "workspace", () => false), RecoveryProofError);
  assert.throws(() => readableCurrent(candidate, "C", "actor", "workspace", () => true), RecoveryProofError);
  const unavailable: Memory = { id: "C", version: 3, intent: "active", validity: "invalidated", displayStatus: "invalidated", contentAvailable: false, reason: "source_unavailable" };
  assert.throws(() => readableCurrent(unavailable, "C", "actor", "workspace", () => false), (error: unknown) => error instanceof RecoveryProofError && error.id === "C" && error.unavailable === "source_unavailable");
});
test("comparison includes exact Unicode/whitespace, optional fields and source tuples even without version change", async () => {
  const shown = await proveSuccessor("C", originalId, reader([candidate, original], []));
  const changes: Partial<AvailableMemory>[] = [ { content: candidate.content.trim() }, { kind: "decision" }, { pinned: false }, { validUntil: null }, { conditions: { ...candidate.conditions, effectiveFrom: null } }, { conditions: { ...candidate.conditions, applicability: "changed" } }, { sourceRefs: [{ ...candidate.sourceRefs[0], contentSha256: "b".repeat(64) }] }, { version: 2 } ];
  for (const delta of changes) {
    const fresh = await proveSuccessor("C", originalId, reader([{ ...candidate, ...delta }, original], []));
    assert.equal(sameProof(shown, fresh), false);
    assert.equal(sameProof(shown, { ...shown, original: { ...original, ...delta } }), false);
  }
  assert.deepEqual(statementOf(original), { kind: original.kind, content: original.content, conditions: original.conditions, pinned: true, validUntil: original.validUntil });
});
test("final C reread change requires another explicit comparison; it never silently adopts", async () => {
  const shown = await proveSuccessor("C", originalId, reader([candidate, original], []));
  let count = 0;
  const result = await recheckSuccessor(shown, async id => { count++; return id === originalId ? original : count === 3 ? { ...candidate, version: 2, content: "changed" } : candidate; });
  assert.equal(count, 3); assert.equal(result.unchanged, false); assert.equal(result.proof.candidate.version, 2);
  await assert.rejects(recheckSuccessor(shown, async id => id === originalId ? original : { ...candidate, intent: "superseded" }), RecoveryProofError);
});
test("outcome correlation requires matching epoch, draft generation, POST/path and original request", () => {
  const state = editing();
  const event = { epoch: 2, requestId: "request", method: "POST" as const, path: "memories/C/corrections", kind: "failure" as const, code: "version_conflict" };
  for (const change of [{ epoch: 3 }, { requestId: "old" }, { method: "PATCH" as const }, { path: "memories/P/corrections" }]) assert.equal(correctionOutcome(state, { ...event, ...change }), state);
  assert.equal(correctionOutcome({ ...state, generation: 5 }, event)?.phase, "submitting");
  const failed = correctionOutcome(state, event)!;
  assert.equal(failed.phase, "conflict"); assert.equal(failed.draft, state.draft); assert.equal(failed.original.id, originalId); assert.equal(failed.target.id, "C");
  assert.equal(correctionOutcome(state, { ...event, kind: "unknown" })?.phase, "unknown");
  assert.equal(correctionOutcome(state, { ...event, kind: "success" }), null);
  assert.equal(correctionOutcome(state, { ...event, code: "invalid_request" })?.phase, "editing");
});
test("recurrent conflict retains original P, every draft field and proven participant identities", () => {
  const state = editing(); state.participants.push("Q");
  const conflict = correctionOutcome(state, { epoch: 2, requestId: "request", method: "POST", path: "memories/C/corrections", kind: "failure", code: "terminal_memory" })!;
  assert.equal(conflict.original.id, originalId); assert.deepEqual(conflict.draft, statementOf(original));
  assert.deepEqual(participantIds(conflict), [originalId, "C", "Q"]);
});

test("matching definitive target denial clears recovery while unknown acknowledgement retains exact draft", () => {
  const state = editing();
  const event = { epoch: state.epoch, requestId: "request", method: "POST" as const, path: "memories/C/corrections", kind: "failure" as const };
  for (const code of ["erased", "memory_not_found", "source_version_unavailable", "source_not_found"]) assert.equal(correctionOutcome(state, { ...event, code }), null);
  const unknown = correctionOutcome(state, { ...event, kind: "unknown", code: "outcome_unknown" })!;
  assert.equal(unknown.draft, state.draft); assert.equal(unknown.attempted, state.attempted); assert.equal(unknown.phase, "unknown");
});
test("final fresh candidate link change invalidates proof without a follow-link or mutation", async () => {
  const shown = await proveSuccessor("C", originalId, reader([candidate, original], []));
  const calls: string[] = [];
  await assert.rejects(recheckSuccessor(shown, async id => { calls.push(id); return id === originalId ? original : calls.length === 3 ? { ...candidate, supersedesId: "unverified-new-parent" } : candidate; }), RecoveryProofError);
  assert.deepEqual(calls, ["C", originalId, "C"]);
});
