import assert from "node:assert/strict";
import fs from "node:fs";
import { parseResearchSse, consumeResearchStream } from "../src/lib/research/sse.ts";
const [file, schema, origin] = process.argv.slice(2);
const wire = fs.readFileSync(file, "utf8");
const parsed = parseResearchSse(wire).events;
const decisions = parsed.filter(e => e.type === "decision_submitted");
assert.equal(decisions.length, 2);
for (const e of decisions) {
  assert.equal(e.schemaVersion, Number(schema));
  if (schema === "1") {
    assert.equal(e.data.decisionOrigin, undefined);
    assert.ok(e.data.actorUserId);
  } else {
    assert.equal(e.data.decisionOrigin, origin);
    if (origin === "human") assert.ok(e.data.actorUserId);
    else assert.equal(e.data.actorUserId, null);
  }
}
const consumed = [];
await consumeResearchStream(new Response(wire), parsed[0].runId, parsed[0].seq - 1, e => consumed.push(e));
assert.equal(consumed.length, parsed.length);
console.log(JSON.stringify({ events: consumed.length, decisionSchema: Number(schema), origin }));
