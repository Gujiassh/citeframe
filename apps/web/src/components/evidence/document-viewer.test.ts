import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  codePointLength,
  sha256HexUtf8,
  sliceByCodePoints,
  type DocumentNormalizedBlock,
} from "@/lib/evidence/document-content";
import { DocumentBlockView, renderDocumentBlockText } from "./document-viewer";

if (!globalThis.crypto?.subtle) {
  Object.defineProperty(globalThis, "crypto", {
    value: webcrypto,
    configurable: true,
  });
}

test("document block renderer highlights exact non-BMP code-point ranges", async () => {
  const text = "pre 😀 post";
  const localStart = codePointLength("pre ");
  const localEnd = localStart + 1;
  const block: DocumentNormalizedBlock = {
    blockId: "emoji-block",
    blockOrder: 0,
    blockKind: "paragraph",
    headingLevel: null,
    headingPath: ["Intro"],
    charStart: 0,
    charEnd: codePointLength(text),
    textSha256: await sha256HexUtf8(text),
    text,
  };

  const parts = renderDocumentBlockText(block, { localStart, localEnd });
  assert.notEqual(typeof parts, "string");

  const html = renderToStaticMarkup(
    createElement(DocumentBlockView, {
      block,
      active: true,
      highlight: { localStart, localEnd },
      onActivate: () => undefined,
    }),
  );

  assert.match(html, /data-document-block-id="emoji-block"/);
  assert.match(html, /data-document-highlight-range="true"/);
  assert.match(html, /<mark[^>]*>😀<\/mark>/);
  assert.match(html, /type="button"/);
  assert.match(html, /data-document-block-active="true"/);
  assert.equal(sliceByCodePoints(text, localStart, localEnd), "😀");
  // Ensure we did not highlight a broken surrogate half.
  assert.doesNotMatch(html, /<mark[^>]*>\ud83d<\/mark>/);
});

test("document block renderer is a semantic button without first-block fallback data", () => {
  const block: DocumentNormalizedBlock = {
    blockId: "block-2",
    blockOrder: 1,
    blockKind: "paragraph",
    headingLevel: null,
    headingPath: ["Intro"],
    charStart: 0,
    charEnd: 4,
    textSha256: "a".repeat(64),
    text: "body",
  };
  const html = renderToStaticMarkup(
    createElement(DocumentBlockView, {
      block,
      active: false,
      highlight: null,
      onActivate: () => undefined,
    }),
  );
  assert.match(html, /<button/);
  assert.match(html, /data-document-block-id="block-2"/);
  assert.doesNotMatch(html, /block-1/);
});

test("document heading renderer uses headingLevel instead of headingPath length", () => {
  const block: DocumentNormalizedBlock = {
    blockId: "heading-deep",
    blockOrder: 0,
    blockKind: "heading",
    headingLevel: 3,
    // Path length intentionally disagrees with headingLevel to prove we prefer headingLevel.
    headingPath: ["A", "B", "C", "D"],
    charStart: 0,
    charEnd: 5,
    textSha256: "a".repeat(64),
    text: "Deep",
  };
  const html = renderToStaticMarkup(
    createElement(DocumentBlockView, {
      block,
      active: false,
      highlight: null,
      onActivate: () => undefined,
    }),
  );
  assert.match(html, /data-document-heading-level="3"/);
  assert.match(html, /font-semibold/);
});
