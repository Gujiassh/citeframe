import assert from "node:assert/strict";
import test from "node:test";

import {
  loadDocumentViewerContent,
  resolveDocumentHighlight,
  splitTextByCodePointRange,
  verifyDocumentNormalizedContent,
} from "@/lib/evidence/document-content";

test("document viewer executable contracts stay fail-closed and generation-bound", async () => {
  assert.equal(typeof loadDocumentViewerContent, "function");
  assert.equal(typeof verifyDocumentNormalizedContent, "function");
  assert.equal(typeof resolveDocumentHighlight, "function");
  assert.equal(typeof splitTextByCodePointRange, "function");

  const split = splitTextByCodePointRange("a😀b", 1, 2);
  assert.deepEqual(split, { before: "a", selected: "😀", after: "b" });

  const none = await resolveDocumentHighlight({
    locator: null,
    sourceVersions: null,
    content: null,
    contentAvailable: false,
  });
  assert.deepEqual(none, { status: "none" });

  const missing = await loadDocumentViewerContent({
    mode: "current",
    workspaceId: "ws",
    assetId: "asset",
    currentProcessingGeneration: 1,
    fetchImpl: async () => new Response("{}", { status: 404 }),
  });
  assert.deepEqual(missing, { status: "unavailable", reason: "content_unavailable" });
});
