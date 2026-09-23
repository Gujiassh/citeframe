import assert from "node:assert/strict";
import fs from "node:fs";
import { parseResearchSse, consumeResearchStream } from "../src/lib/research/sse.ts";
const wire = fs.readFileSync(process.argv[2], "utf8");
const parsed = parseResearchSse(wire).events;
assert.ok(parsed.length);
const decisions = parsed.filter(e => e.type === "decision_submitted");
assert.ok(decisions.some(e => e.data.decisionOrigin === "policy"));
const consumed = [];
await consumeResearchStream(new Response(wire), parsed[0].runId, parsed[0].seq - 1, e => consumed.push(e));
assert.equal(consumed.length, parsed.length);
function frame(e) { return `id: ${e.seq}\nevent: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`; }
for (const e of decisions) {
  assert.equal(e.schemaVersion, 2);
  assert.equal(e.data.actorUserId, null);
  assert.equal(e.data.policyId, "research-autonomy-v1");
  const human = structuredClone(e);
  human.data.decisionOrigin = "human"; human.data.actorUserId = "historical-user"; human.data.policyId = null;
  assert.equal(parseResearchSse(frame(human)).events.length, 1);
  human.schemaVersion = 1; delete human.data.decisionOrigin; delete human.data.policyId;
  assert.equal(parseResearchSse(frame(human)).events.length, 1);
  human.data.actorUserId = null;
  assert.throws(() => parseResearchSse(frame(human)), /invalid/);
  for (const patch of [{ actorUserId: "forged-human" }, { policyId: null }, { decisionOrigin: "unknown" }, { inputArtifactId: null }]) {
    const bad = structuredClone(e); Object.assign(bad.data, patch);
    assert.throws(() => parseResearchSse(frame(bad)), /invalid/);
  }
}
console.log(JSON.stringify({events: consumed.length, decisions: decisions.map(e => e.data.decisionType)}));
