import assert from "node:assert/strict";
import test from "node:test";

import {
  consumeResearchStream,
  parseResearchSse,
  RESEARCH_EVENT_NAMES,
  runResearchStreamLoop,
} from "./sse";

function frame(seq: number, name = "run_status_changed") {
  const data = name === "run_status_changed"
    ? { previousStatus: "planning", status: "running", runStateVersion: seq, reasonCode: null }
    : { status: "running", createdByUserId: "user-1", runStateVersion: seq };
  return `id: ${seq}\nevent: ${name}\ndata: ${JSON.stringify({ schemaVersion: 1, eventId: `event-${seq}`, runId: "run-1", seq, type: name, occurredAt: "2026-07-27T00:00:00Z", data })}\n\n`;
}

test("Research SSE exposes the exact 15-event allowlist", () => {
  assert.equal(RESEARCH_EVENT_NAMES.length, 15);
  assert.equal(new Set(RESEARCH_EVENT_NAMES).size, 15);
});

test("Research SSE retains partial frames and validates decimal seq ids", () => {
  const first = parseResearchSse(frame(1).slice(0, 30));
  assert.equal(first.events.length, 0);
  const complete = parseResearchSse(first.remainder + frame(1).slice(30));
  assert.equal(complete.events[0].seq, 1);
});

test("Research SSE rejects the obsolete compound cursor shape", () => {
  assert.throws(
    () => parseResearchSse(frame(1).replace("id: 1", "id: run-1:1")),
    /event id does not match seq/,
  );
});

test("Research SSE rejects an obsolete event envelope field", () => {
  const obsolete = frame(1).replace('"type":"run_status_changed"', '"event":"run_status_changed"');
  assert.throws(() => parseResearchSse(obsolete), /event envelope is invalid/);
});

test("Research stream rejects sequence gaps", async () => {
  const response = new Response(frame(1) + frame(3), { headers: { "content-type": "text/event-stream" } });
  await assert.rejects(() => consumeResearchStream(response, "run-1", 0, () => undefined), /sequence has a gap/);
});

test("Research SSE rejects unknown events", () => {
  assert.throws(() => parseResearchSse(frame(1, "token_delta")), /Unknown Research event/);
});

test("Research SSE rejects extra envelope and event data fields", () => {
  assert.throws(() => parseResearchSse(frame(1).replace('"data":{', '"prompt":"secret","data":{')), /envelope is invalid/);
  assert.throws(() => parseResearchSse(frame(1).replace('"reasonCode":null', '"reasonCode":null,"prompt":"secret"')), /event data is invalid/);
});

test("Research stream rejects an event from another run", async () => {
  const response = new Response(frame(1).replace('"runId":"run-1"', '"runId":"run-2"'));
  await assert.rejects(() => consumeResearchStream(response, "run-1", 0, () => undefined), /run does not match/);
});

test("Research stream loop reconnects from the last continuous seq and ignores duplicate delivery", async () => {
  const controller = new AbortController();
  const cursors: number[] = [];
  const applied: number[] = [];
  const streams = [frame(1) + frame(2), frame(2) + frame(3)];

  await runResearchStreamLoop({
    runId: "run-1",
    afterSeq: 0,
    signal: controller.signal,
    reconnectDelayMs: 0,
    open: async (afterSeq) => {
      cursors.push(afterSeq);
      const body = streams.shift();
      if (!body) {
        controller.abort();
        return new Response("");
      }
      return new Response(body, { headers: { "content-type": "text/event-stream" } });
    },
    onEvent: (event) => applied.push(event.seq),
    onReconnect: () => undefined,
    onHistoryUnavailable: async () => 0,
    onCursorConflict: async () => 0,
  });

  assert.deepEqual(cursors, [0, 2, 3]);
  assert.deepEqual(applied, [1, 2, 3]);
});

test("Research stream loop resumes future events from a current snapshot on 410", async () => {
  const controller = new AbortController();
  let restored = false;
  const cursors: number[] = [];

  await runResearchStreamLoop({
    runId: "run-1",
    afterSeq: 3,
    signal: controller.signal,
    reconnectDelayMs: 0,
    open: async (afterSeq) => {
      cursors.push(afterSeq);
      if (afterSeq === 3) throw Object.assign(new Error("gone"), { status: 410 });
      controller.abort();
      return new Response("");
    },
    onEvent: () => undefined,
    onReconnect: () => undefined,
    onHistoryUnavailable: async () => {
      restored = true;
      return 8;
    },
    onCursorConflict: async () => 0,
  });

  assert.equal(restored, true);
  assert.deepEqual(cursors, [3, 8]);
});

test("Research stream loop rereads the run and replaces a cursor rejected with 409", async () => {
  const controller = new AbortController();
  const cursors: number[] = [];

  await runResearchStreamLoop({
    runId: "run-1",
    afterSeq: 12,
    signal: controller.signal,
    reconnectDelayMs: 0,
    open: async (afterSeq) => {
      cursors.push(afterSeq);
      if (afterSeq === 12) throw Object.assign(new Error("ahead"), { status: 409 });
      controller.abort();
      return new Response("");
    },
    onEvent: () => undefined,
    onReconnect: () => undefined,
    onHistoryUnavailable: async () => 0,
    onCursorConflict: async () => 7,
  });

  assert.deepEqual(cursors, [12, 7]);
});
