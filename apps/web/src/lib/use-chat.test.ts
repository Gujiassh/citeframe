import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAssetScope,
  getMessageParentId,
  getNextActiveThreadId,
  reconcileFailedOptimisticMessages,
  replaceUiThread,
} from "./use-chat";
import type { ChatThread } from "@/lib/chat/types";

const threads: ChatThread[] = [
  {
    id: "thread-1",
    workspaceId: "ws-1",
    title: "First",
    createdAt: "2026-07-15T00:00:00Z",
    messages: [
      {
        id: "message-1",
        role: "user",
        content: "Question",
        createdAt: "2026-07-15T00:00:00Z",
        parentMessageId: null,
      },
      {
        id: "message-2",
        role: "assistant",
        content: "Answer",
        createdAt: "2026-07-15T00:01:00Z",
        parentMessageId: "message-1",
      },
    ],
  },
];

test("chat hydration keeps the active thread when it remains in the workspace", () => {
  assert.equal(getNextActiveThreadId(threads, "thread-1"), "thread-1");
  assert.equal(getNextActiveThreadId(threads, "missing"), "thread-1");
  assert.equal(getNextActiveThreadId([], "missing"), null);
});

test("chat asset scope is explicit and preserves selected asset order", () => {
  assert.deepEqual(buildAssetScope([]), { mode: "all_ready" });
  assert.deepEqual(buildAssetScope(["asset-2", "asset-1"]), {
    mode: "selected",
    assetIds: ["asset-2", "asset-1"],
  });
  assert.deepEqual(
    buildAssetScope(["asset-2"], [{
      kind: "image_region",
      assetId: "asset-1",
      processingGeneration: 3,
      coordinateSpace: "image_normalized_top_left_v1",
      regions: [{ x: 0.1, y: 0.2, width: 0.3, height: 0.4 }],
    }]),
    { mode: "selected", assetIds: ["asset-2", "asset-1"] },
  );
});


test("mixed PDF+Image+Markdown selected scope stays exact without dedupe reordering", () => {
  // D-WEB/D-G2: Quick Chat selected scope must preserve the three mixed modality
  // asset ids the sidebar checkbox order produced; evidence targets only add
  // missing ids and never invent or reshuffle unrelated ids.
  const mixedSelected = ["asset-pdf", "asset-image", "asset-document"];
  assert.deepEqual(buildAssetScope(mixedSelected), {
    mode: "selected",
    assetIds: mixedSelected,
  });
  assert.deepEqual(
    buildAssetScope(mixedSelected, [{
      kind: "image_region",
      assetId: "asset-image",
      processingGeneration: 1,
      coordinateSpace: "image_normalized_top_left_v1",
      regions: [{ x: 0.1, y: 0.2, width: 0.3, height: 0.4 }],
    }]),
    { mode: "selected", assetIds: mixedSelected },
  );
  assert.deepEqual(
    buildAssetScope(["asset-pdf", "asset-document"], [{
      kind: "image_region",
      assetId: "asset-image",
      processingGeneration: 1,
      coordinateSpace: "image_normalized_top_left_v1",
      regions: [{ x: 0.1, y: 0.2, width: 0.3, height: 0.4 }],
    }]),
    { mode: "selected", assetIds: ["asset-pdf", "asset-document", "asset-image"] },
  );
});

test("chat parent selection preserves branch editing semantics", () => {
  assert.equal(getMessageParentId(threads[0], "message-2"), "message-1");
  assert.equal(getMessageParentId(threads[0]), "message-2");
  assert.equal(getMessageParentId(undefined), null);
});


test("replacing hydrated chat threads preserves sibling messages and workspace isolation", () => {
  const threadA: ChatThread = {
    ...threads[0],
    id: "thread-a",
    title: "A",
    messages: [{ ...threads[0].messages[0], id: "a-message", content: "A message" }],
  };
  const threadB: ChatThread = {
    ...threads[0],
    id: "thread-b",
    title: "B",
    messages: [{ ...threads[0].messages[0], id: "b-message", content: "B message" }],
  };

  const afterBReplacement = replaceUiThread(
    [threadA, threadB],
    { ...threadB, messages: [{ ...threadB.messages[0], content: "B refreshed" }] },
  );

  assert.deepEqual(afterBReplacement.find((thread) => thread.id === "thread-a")?.messages, threadA.messages);
  assert.equal(afterBReplacement.find((thread) => thread.id === "thread-b")?.messages[0]?.content, "B refreshed");

  const afterAReplacement = replaceUiThread(
    afterBReplacement,
    { ...threadA, messages: [{ ...threadA.messages[0], content: "A refreshed" }] },
  );

  assert.equal(afterAReplacement.length, 2);
  assert.equal(afterAReplacement.find((thread) => thread.id === "thread-a")?.messages[0]?.content, "A refreshed");
  assert.equal(afterAReplacement.find((thread) => thread.id === "thread-b")?.messages[0]?.content, "B refreshed");

  const sameIdOtherWorkspace = { ...threadA, workspaceId: "ws-2", messages: [{ ...threadA.messages[0], content: "Other workspace" }] };
  const afterForeignReplacement = replaceUiThread(afterAReplacement, sameIdOtherWorkspace);

  assert.equal(afterForeignReplacement.length, 3);
  assert.equal(afterForeignReplacement.find((thread) => thread.workspaceId === "ws-1" && thread.id === "thread-a")?.messages[0]?.content, "A refreshed");
  assert.equal(afterForeignReplacement.find((thread) => thread.workspaceId === "ws-2" && thread.id === "thread-a")?.messages[0]?.content, "Other workspace");
});

test("accepted chat fallback preserves the user and locked Evidence when stream recovery fails", () => {
  const messages = reconcileFailedOptimisticMessages({
    messages: [
      {
        id: "server-user",
        role: "user",
        content: "Analyze this region.",
        createdAt: "2026-07-19T00:00:00Z",
        pendingInputEvidenceCount: 1,
      },
      {
        id: "server-assistant",
        role: "assistant",
        content: "partial",
        createdAt: "2026-07-19T00:00:00Z",
        parentMessageId: "server-user",
        status: "streaming",
      },
    ],
    requestAccepted: true,
    temporaryUserMessageId: "pending-user",
    temporaryAssistantMessageId: "pending-assistant",
    userMessageId: "server-user",
    assistantMessageId: "server-assistant",
    errorMessage: "Chat stream ended before completion.",
    createdAt: "2026-07-19T00:00:00Z",
  });

  assert.deepEqual(messages, [
    {
      id: "server-user",
      role: "user",
      content: "Analyze this region.",
      createdAt: "2026-07-19T00:00:00Z",
      pendingInputEvidenceCount: 1,
    },
    {
      id: "server-assistant",
      role: "assistant",
      content: "Chat stream ended before completion.",
      citations: [],
      createdAt: "2026-07-19T00:00:00Z",
      parentMessageId: "server-user",
      status: "failed",
    },
  ]);
});

test("rejected chat fallback removes the unpersisted optimistic user", () => {
  const messages = reconcileFailedOptimisticMessages({
    messages: [
      {
        id: "pending-user",
        role: "user",
        content: "Invalid question.",
        createdAt: "2026-07-19T00:00:00Z",
      },
      {
        id: "pending-assistant",
        role: "assistant",
        content: "",
        createdAt: "2026-07-19T00:00:00Z",
        parentMessageId: "pending-user",
        status: "streaming",
      },
    ],
    requestAccepted: false,
    temporaryUserMessageId: "pending-user",
    temporaryAssistantMessageId: "pending-assistant",
    userMessageId: "pending-user",
    assistantMessageId: "pending-assistant",
    errorMessage: "Evidence target could not be resolved.",
    createdAt: "2026-07-19T00:00:00Z",
  });

  assert.equal(messages.some((message) => message.role === "user"), false);
  assert.deepEqual(messages[0], {
    id: "pending-assistant",
    role: "assistant",
    content: "Evidence target could not be resolved.",
    citations: [],
    createdAt: "2026-07-19T00:00:00Z",
    parentMessageId: null,
    status: "failed",
  });
});
