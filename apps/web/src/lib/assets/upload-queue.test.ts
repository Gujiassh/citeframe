import assert from "node:assert/strict";
import test from "node:test";
import { UploadQueue, takeSelectedFiles } from "./upload-queue";

const file = (name: string) => new File([name], name, { type: "text/markdown" });
const tick = () => new Promise<void>((resolve) => setImmediate(resolve));
function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => { resolve = done; });
  return { promise, resolve };
}

test("FIFO queue appends while running and never overlaps transfers", async () => {
  const queue = new UploadQueue(); queue.start();
  const gate = deferred(); const started: string[] = [];
  let active = 0; let maxActive = 0;
  const task = (f: File) => async () => {
    started.push(f.name); maxActive = Math.max(maxActive, ++active);
    if (f.name === "a.md") await gate.promise;
    active--;
  };
  queue.enqueue("a", [file("a.md"), file("b.md")], task);
  queue.enqueue("a", [file("c.md")], task);
  assert.deepEqual(queue.getSnapshot().map((item) => item.status), ["uploading", "queued", "queued"]);
  gate.resolve(); await tick();
  assert.deepEqual(started, ["a.md", "b.md", "c.md"]);
  assert.equal(maxActive, 1);
  assert.ok(queue.getSnapshot().every((item) => item.status === "submitted"));
});

test("failure continues and retry appends without replaying successful items", async () => {
  const queue = new UploadQueue(); queue.start();
  const started: string[] = []; const gate = deferred(); let fail = true;
  queue.enqueue("a", [file("bad.md"), file("good.md")], (f) => async () => {
    started.push(f.name);
    if (f.name === "bad.md" && fail) throw new Error("Denied");
    if (f.name === "good.md") await gate.promise;
  });
  await tick();
  assert.equal(queue.getSnapshot()[0].error, "Denied");
  fail = false; queue.retry(queue.getSnapshot()[0].id);
  queue.retry(queue.getSnapshot()[0].id);
  assert.deepEqual(started, ["bad.md", "good.md"]);
  gate.resolve(); await tick();
  queue.retry(queue.getSnapshot()[1].id);
  assert.deepEqual(started, ["bad.md", "good.md", "bad.md"]);
});

test("selections and completions remain bound to workspace even while another is selected", async () => {
  const queue = new UploadQueue(); queue.start();
  const gate = deferred(); const calls: string[] = [];
  let workspace = "a";
  function select(name: string) {
    const selectedWorkspace = workspace;
    queue.enqueue(selectedWorkspace, [file(name)], () => async () => {
      calls.push(selectedWorkspace);
      if (selectedWorkspace === "a") await gate.promise;
    });
  }
  select("a.md"); workspace = "b"; select("b.md");
  assert.deepEqual(queue.getSnapshot().filter((item) => item.workspaceId === workspace).map((item) => item.filename), ["b.md"]);
  gate.resolve(); await tick(); assert.deepEqual(calls, ["a", "b"]);
  assert.deepEqual(queue.getSnapshot().map((item) => item.workspaceId), ["a", "b"]);
});

test("stop aborts active work, clears queued files and ignores late completion", async () => {
  const queue = new UploadQueue(); queue.start();
  const gate = deferred(); let signal: AbortSignal | undefined; let calls = 0;
  queue.enqueue("a", [file("a.md"), file("b.md")], () => async (s) => { calls++; signal = s; await gate.promise; });
  queue.stop(); assert.equal(signal?.aborted, true); assert.deepEqual(queue.getSnapshot(), []);
  gate.resolve(); await tick(); assert.equal(calls, 1); assert.deepEqual(queue.getSnapshot(), []);
  queue.start(); queue.enqueue("b", [file("c.md")], () => async () => {});
  await tick(); assert.equal(queue.getSnapshot()[0].status, "submitted");
});

test("workspace removal cancels its uploads and preserves other workspace queue", async () => {
  const queue = new UploadQueue(); queue.start(); const gate = deferred(); const calls: string[] = [];
  queue.enqueue("a", [file("a.md"), file("b.md")], (f) => async () => { calls.push(f.name); await gate.promise; });
  queue.enqueue("b", [file("c.md")], (f) => async () => { calls.push(f.name); });
  queue.removeWorkspace("a"); gate.resolve(); await tick();
  assert.deepEqual(calls, ["a.md", "c.md"]);
  assert.deepEqual(queue.getSnapshot().map((item) => item.workspaceId), ["b"]);
});

test("picker resets immediately and selecting the same file again creates a distinct entry", async () => {
  const queue = new UploadQueue(); queue.start();
  const selected = file("same.md");
  const input = { files: [selected] as unknown as FileList, value: "same.md" };
  const files = takeSelectedFiles(input); assert.equal(input.value, "");
  queue.enqueue("a", files, () => async () => {});
  input.value = "same.md"; queue.enqueue("a", takeSelectedFiles(input), () => async () => {});
  await tick(); assert.equal(input.value, "");
  assert.equal(queue.getSnapshot().length, 2); assert.notEqual(queue.getSnapshot()[0].id, queue.getSnapshot()[1].id);
});
