import assert from "node:assert/strict";
import test from "node:test";
import { startChatStream } from "./client";
import { chatSubmissionScope, questionAfterSubmission, rejectedChatSubmission } from "./submission";

test("prestream embedding mismatch preserves retry draft and actionable server message", async (t) => {
  const message = "Current embedding index does not match the active embedding contract; explicit reindex is required.";
  t.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({ detail: message }), { status: 409 }));
  const question = "What changed in these documents?";
  let failure;
  try {
    await startChatStream("workspace-a", { threadId: "thread-a", question, assetScope: { mode: "all_ready" } });
    assert.fail("request must be rejected before streaming");
  } catch (error) { failure = rejectedChatSubmission(error, question); }
  assert.equal(failure.message, message);
  assert.equal(failure.draft, question);
  assert.equal(questionAfterSubmission(question, false), question);
  // The provider-owned failure is independent of successful thread hydration and tab remount.
  const failures = { [chatSubmissionScope("owner-a", "workspace-a", "thread-a")]: failure };
  assert.equal(failures[chatSubmissionScope("owner-a", "workspace-a", "thread-a")].draft, question);
});

test("accepted retry clears composer while rejected request retains exact input", () => {
  assert.equal(questionAfterSubmission("  keep my draft  ", false), "  keep my draft  ");
  assert.equal(questionAfterSubmission("retry this question", true), "");
});

test("rejected submissions are isolated by authenticated owner, workspace and thread", () => {
  const scope = chatSubmissionScope("a", "workspace-a", "thread-a");
  assert.notEqual(scope, chatSubmissionScope("b", "workspace-a", "thread-a"));
  assert.notEqual(scope, chatSubmissionScope("a", "workspace-b", "thread-a"));
  assert.notEqual(scope, chatSubmissionScope("a", "workspace-a", "thread-b"));
});

test("rejected edit exposes error without converting edited content into a new-question draft", () => {
  assert.deepEqual(rejectedChatSubmission(new Error("Provider unavailable"), "edit content", true), { message: "Provider unavailable", draft: null });
});
