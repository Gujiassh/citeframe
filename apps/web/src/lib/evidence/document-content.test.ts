import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import test from "node:test";

import {
  bindDocumentOwnership,
  buildDocumentContentApiUrl,
  buildDocumentContentUrl,
  codePointLength,
  loadDocumentViewerContent,
  parseDocumentAssetDetail,
  parseDocumentNormalizedContent,
  resolveDocumentHighlight,
  sha256HexUtf8,
  sliceByCodePoints,
  splitTextByCodePointRange,
  verifyDocumentNormalizedContent,
} from "./document-content";
import type { DocumentAnchorLocator, SourceVersions } from "./types";

if (!globalThis.crypto?.subtle) {
  Object.defineProperty(globalThis, "crypto", {
    value: webcrypto,
    configurable: true,
  });
}

async function makeVerifiedFixture(options?: {
  includeEmoji?: boolean;
}) {
  const heading = "Intro";
  const body = options?.includeEmoji ? "hello 😀 world" : "paragraph";
  const normalizedText = `${heading}\n\n${body}`;
  const headingStart = 0;
  const headingEnd = codePointLength(heading);
  const bodyStart = codePointLength(`${heading}\n\n`);
  const bodyEnd = bodyStart + codePointLength(body);

  const contentSha256 = await sha256HexUtf8(normalizedText);
  const headingSha = await sha256HexUtf8(heading);
  const bodySha = await sha256HexUtf8(body);

  const content = {
    assetId: "asset-1",
    representationId: "rep-1",
    processingGeneration: 2,
    format: "markdown" as const,
    parserVersion: "document-parser-v1" as const,
    normalizationVersion: "document-normalization-v1" as const,
    contentSha256,
    normalizedText,
    blocks: [
      {
        blockId: "block-1",
        blockOrder: 0,
        blockKind: "heading" as const,
        headingLevel: 1,
        headingPath: ["Intro"],
        charStart: headingStart,
        charEnd: headingEnd,
        textSha256: headingSha,
        text: heading,
      },
      {
        blockId: "block-2",
        blockOrder: 1,
        blockKind: "paragraph" as const,
        headingLevel: null,
        headingPath: ["Intro"],
        charStart: bodyStart,
        charEnd: bodyEnd,
        textSha256: bodySha,
        text: body,
      },
    ],
  };

  const sourceVersions: SourceVersions = {
    parserVersion: "document-parser-v1",
    processingGeneration: 2,
    representationId: "rep-1",
    indexVersion: 1,
  };

  return { content, sourceVersions, body, bodyStart, bodyEnd, bodySha };
}

test("document DTO parsers accept canonical document detail and normalized content", async () => {
  const detail = parseDocumentAssetDetail({
    kind: "document",
    format: "markdown",
    parserVersion: "document-parser-v1",
    normalizationVersion: "document-normalization-v1",
    representationId: "rep-1",
    blockCount: 2,
    headings: [{ blockId: "block-1", level: 1, text: "Intro", order: 0 }],
  });
  assert.equal(detail?.representationId, "rep-1");
  assert.equal(detail?.headings[0]?.level, 1);

  const { content } = await makeVerifiedFixture();
  const parsed = parseDocumentNormalizedContent(content);
  assert.equal(parsed?.blocks.length, 2);
  assert.equal(parsed?.blocks[0]?.headingLevel, 1);
  assert.equal(parsed?.blocks[1]?.headingLevel, null);
});

test("document DTO parser requires headingLevel 1..6 for headings and null otherwise", async () => {
  const { content } = await makeVerifiedFixture();

  assert.equal(
    parseDocumentNormalizedContent({
      ...content,
      blocks: content.blocks.map((block) =>
        block.blockKind === "heading"
          ? { ...block, headingLevel: null }
          : block,
      ),
    }),
    null,
  );
  assert.equal(
    parseDocumentNormalizedContent({
      ...content,
      blocks: content.blocks.map((block) =>
        block.blockKind === "heading"
          ? { ...block, headingLevel: 0 }
          : block,
      ),
    }),
    null,
  );
  assert.equal(
    parseDocumentNormalizedContent({
      ...content,
      blocks: content.blocks.map((block) =>
        block.blockKind === "paragraph"
          ? { ...block, headingLevel: 2 }
          : block,
      ),
    }),
    null,
  );
  assert.equal(
    parseDocumentNormalizedContent({
      ...content,
      blocks: content.blocks.map((block) => ({
        blockId: block.blockId,
        blockOrder: block.blockOrder,
        blockKind: block.blockKind,
        headingPath: block.headingPath,
        charStart: block.charStart,
        charEnd: block.charEnd,
        textSha256: block.textSha256,
        text: block.text,
      })),
    }),
    null,
  );

  const verified = await verifyDocumentNormalizedContent({
    ...content,
    blocks: content.blocks.map((block) =>
      block.blockKind === "heading"
        ? { ...block, headingLevel: 7 }
        : block,
    ),
  });
  assert.deepEqual(verified, { ok: false, reason: "integrity_failed" });
});

test("document DTO parsers reject unknown versions and missing representation identity", () => {
  assert.equal(
    parseDocumentAssetDetail({
      kind: "document",
      format: "markdown",
      parserVersion: "document-parser-v1",
      normalizationVersion: "document-normalization-v1",
      blockCount: 1,
      headings: [],
    }),
    null,
  );
  assert.equal(
    parseDocumentNormalizedContent({
      assetId: "asset-1",
      representationId: "rep-1",
      processingGeneration: 1,
      format: "markdown",
      parserVersion: "document-parser-v1",
      normalizationVersion: "document-normalization-v2",
      contentSha256: "a".repeat(64),
      normalizedText: "x",
      blocks: [],
    }),
    null,
  );
});

test("cryptographic integrity rejects fake mutually consistent hashes", async () => {
  const { content } = await makeVerifiedFixture();
  const ok = await verifyDocumentNormalizedContent(content, {
    assetId: "asset-1",
    representationId: "rep-1",
    processingGeneration: 2,
  });
  assert.equal(ok.ok, true);

  const fake = {
    ...content,
    contentSha256: "a".repeat(64),
    blocks: content.blocks.map((block) => ({ ...block, textSha256: "b".repeat(64) })),
  };
  const failed = await verifyDocumentNormalizedContent(fake);
  assert.deepEqual(failed, { ok: false, reason: "integrity_failed" });

  const mismatchedRange = {
    ...content,
    blocks: [
      content.blocks[0],
      {
        ...content.blocks[1],
        text: "tampered",
        textSha256: await sha256HexUtf8("tampered"),
      },
    ],
  };
  const rangeFailed = await verifyDocumentNormalizedContent(mismatchedRange);
  assert.deepEqual(rangeFailed, { ok: false, reason: "integrity_failed" });
});

test("ownership binding rejects content that does not match asset/representation/generation", async () => {
  const { content } = await makeVerifiedFixture();
  assert.equal(
    bindDocumentOwnership(content, {
      assetId: "asset-1",
      representationId: "rep-1",
      processingGeneration: 3,
    }),
    false,
  );
  const verified = await verifyDocumentNormalizedContent(content, {
    assetId: "other-asset",
    representationId: "rep-1",
    processingGeneration: 2,
  });
  assert.deepEqual(verified, { ok: false, reason: "snapshot_mismatch" });
});

test("code-point slicing handles non-BMP emoji without UTF-16 index corruption", async () => {
  const text = "ab😀cd";
  assert.equal(codePointLength(text), 5);
  assert.equal(sliceByCodePoints(text, 2, 3), "😀");
  assert.equal(sliceByCodePoints(text, 2, 4), "😀c");
  // UTF-16 slice would split the surrogate pair; code-point slice must not.
  assert.notEqual(text.slice(2, 3), "😀");

  const { content, sourceVersions, bodyStart, bodySha } = await makeVerifiedFixture({
    includeEmoji: true,
  });
  const verified = await verifyDocumentNormalizedContent(content);
  assert.equal(verified.ok, true);
  if (!verified.ok) {
    return;
  }

  // Highlight only the emoji code point inside "hello 😀 world"
  const emojiOffsetInBody = codePointLength("hello ");
  const locator: DocumentAnchorLocator = {
    kind: "document_anchor",
    version: 1,
    blockId: "block-2",
    blockKind: "paragraph",
    headingPath: ["Intro"],
    charStart: bodyStart + emojiOffsetInBody,
    charEnd: bodyStart + emojiOffsetInBody + 1,
    textSha256: await sha256HexUtf8("😀"),
    normalizationVersion: "document-normalization-v1",
  };

  const highlight = await resolveDocumentHighlight({
    locator,
    sourceVersions,
    content: verified.content,
    contentAvailable: true,
    expectedOwnership: {
      assetId: "asset-1",
      representationId: "rep-1",
      processingGeneration: 2,
    },
  });
  assert.equal(highlight.status, "ready");
  if (highlight.status !== "ready") {
    return;
  }
  assert.equal(highlight.selectedText, "😀");
  assert.equal(highlight.localStart, emojiOffsetInBody);
  assert.equal(highlight.localEnd, emojiOffsetInBody + 1);

  const split = splitTextByCodePointRange(
    content.blocks[1].text,
    highlight.localStart,
    highlight.localEnd,
  );
  assert.deepEqual(split, { before: "hello ", selected: "😀", after: " world" });

  // Full-block hash still validates separately.
  assert.equal(content.blocks[1].textSha256, bodySha);
});

test("document highlight jumps to exact verified range and never falls back to first block", async () => {
  const { content, sourceVersions, bodyStart, bodyEnd, bodySha } = await makeVerifiedFixture();
  const verified = await verifyDocumentNormalizedContent(content);
  assert.equal(verified.ok, true);
  if (!verified.ok) {
    return;
  }

  const selected = sliceByCodePoints(content.normalizedText, bodyStart + 0, bodyStart + 4);
  const locator: DocumentAnchorLocator = {
    kind: "document_anchor",
    version: 1,
    blockId: "block-2",
    blockKind: "paragraph",
    headingPath: ["Intro"],
    charStart: bodyStart,
    charEnd: bodyStart + 4,
    textSha256: await sha256HexUtf8(selected),
    normalizationVersion: "document-normalization-v1",
  };

  const ready = await resolveDocumentHighlight({
    locator,
    sourceVersions,
    content: verified.content,
    contentAvailable: true,
  });
  assert.equal(ready.status, "ready");
  if (ready.status === "ready") {
    assert.equal(ready.blockId, "block-2");
    assert.equal(ready.selectedText, selected);
    assert.notEqual(ready.blockId, "block-1");
  }

  assert.deepEqual(
    await resolveDocumentHighlight({
      locator: { ...locator, blockId: "missing" },
      sourceVersions,
      content: verified.content,
      contentAvailable: true,
    }),
    { status: "unavailable", reason: "missing_block" },
  );
  assert.deepEqual(
    await resolveDocumentHighlight({
      locator: { ...locator, textSha256: "d".repeat(64) },
      sourceVersions,
      content: verified.content,
      contentAvailable: true,
    }),
    { status: "unavailable", reason: "hash_mismatch" },
  );
  assert.deepEqual(
    await resolveDocumentHighlight({
      locator: { ...locator, charStart: 0, charEnd: 2 },
      sourceVersions,
      content: verified.content,
      contentAvailable: true,
    }),
    { status: "unavailable", reason: "range_mismatch" },
  );
  assert.deepEqual(
    await resolveDocumentHighlight({
      locator: { ...locator, version: 2 },
      sourceVersions,
      content: verified.content,
      contentAvailable: true,
    }),
    { status: "unavailable", reason: "unknown_version" },
  );
  assert.deepEqual(
    await resolveDocumentHighlight({
      locator,
      sourceVersions: { ...sourceVersions, representationId: "other" },
      content: verified.content,
      contentAvailable: true,
    }),
    { status: "unavailable", reason: "snapshot_mismatch" },
  );
  assert.deepEqual(
    await resolveDocumentHighlight({
      locator,
      sourceVersions,
      content: null,
      contentAvailable: false,
    }),
    { status: "unavailable", reason: "content_unavailable" },
  );
  assert.deepEqual(
    await resolveDocumentHighlight({
      locator,
      sourceVersions,
      content: verified.content,
      contentAvailable: true,
      sourceDeleted: true,
    }),
    { status: "unavailable", reason: "source_deleted" },
  );
  assert.deepEqual(
    await resolveDocumentHighlight({
      locator: null,
      sourceVersions: null,
      content: verified.content,
      contentAvailable: true,
    }),
    { status: "none" },
  );

  // Unverified content with fake hashes must fail closed.
  const fake = {
    ...content,
    contentSha256: "a".repeat(64),
    blocks: content.blocks.map((block) => ({ ...block, textSha256: bodySha })),
  };
  assert.deepEqual(
    await resolveDocumentHighlight({
      locator: {
        ...locator,
        charStart: bodyStart,
        charEnd: bodyEnd,
        textSha256: bodySha,
      },
      sourceVersions,
      content: fake,
      contentAvailable: true,
    }),
    { status: "unavailable", reason: "integrity_failed" },
  );
});

test("current browsing binds generation and rejects stale responses", async () => {
  const { content } = await makeVerifiedFixture();
  let detailCalls = 0;
  const fetchImpl: typeof fetch = async (input) => {
    const url = String(input);
    if (url.includes("/assets/asset-1") && !url.includes("/representations/")) {
      detailCalls += 1;
      if (detailCalls === 1) {
        return new Response(JSON.stringify({
          asset: {
            id: "asset-1",
            kind: "document",
            currentProcessingGeneration: 2,
          },
          detail: {
            kind: "document",
            format: "markdown",
            parserVersion: "document-parser-v1",
            normalizationVersion: "document-normalization-v1",
            representationId: "rep-1",
            blockCount: 2,
            headings: [{ blockId: "block-1", level: 1, text: "Intro", order: 0 }],
          },
        }), { status: 200 });
      }
      // Stale later detail with wrong generation.
      return new Response(JSON.stringify({
        asset: {
          id: "asset-1",
          kind: "document",
          currentProcessingGeneration: 9,
        },
        detail: {
          kind: "document",
          format: "markdown",
          parserVersion: "document-parser-v1",
          normalizationVersion: "document-normalization-v1",
          representationId: "rep-stale",
          blockCount: 2,
          headings: [],
        },
      }), { status: 200 });
    }
    if (url.includes("/representations/rep-1/content")) {
      return new Response(JSON.stringify(content), { status: 200 });
    }
    return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
  };

  const ready = await loadDocumentViewerContent({
    mode: "current",
    workspaceId: "ws-1",
    assetId: "asset-1",
    currentProcessingGeneration: 2,
    fetchImpl,
  });
  assert.equal(ready.status, "ready");
  if (ready.status === "ready") {
    assert.equal(ready.content.processingGeneration, 2);
    assert.equal(ready.content.representationId, "rep-1");
  }

  const stale = await loadDocumentViewerContent({
    mode: "current",
    workspaceId: "ws-1",
    assetId: "asset-1",
    currentProcessingGeneration: 2,
    fetchImpl,
  });
  assert.deepEqual(stale, { status: "unavailable", reason: "snapshot_mismatch" });
});

test("frozen browsing uses only frozen representation snapshot", async () => {
  const { content, sourceVersions } = await makeVerifiedFixture();
  const fetchImpl: typeof fetch = async (input) => {
    const url = String(input);
    if (url.includes("/representations/rep-1/content")) {
      return new Response(JSON.stringify(content), { status: 200 });
    }
    return new Response("should-not-hit-detail", { status: 500 });
  };
  const frozen = await loadDocumentViewerContent({
    mode: "frozen",
    workspaceId: "ws-1",
    assetId: "asset-1",
    sourceVersions,
    fetchImpl,
  });
  assert.equal(frozen.status, "ready");
  if (frozen.status === "ready") {
    assert.equal(frozen.detail, null);
    assert.equal(frozen.content.representationId, "rep-1");
  }
});

test("document content BFF path encodes workspace, asset, and representation ids", () => {
  assert.equal(
    buildDocumentContentUrl("ws/a", "asset/b", "rep/c"),
    "/api/workspaces/ws%2Fa/assets/asset%2Fb/representations/rep%2Fc/content",
  );
  const apiUrl = buildDocumentContentApiUrl("http://api:8000", "ws/a", "asset/b", "rep/c");
  assert.equal(
    apiUrl.pathname,
    "/v1/workspaces/ws%2Fa/assets/asset%2Fb/representations/rep%2Fc/content",
  );
});
