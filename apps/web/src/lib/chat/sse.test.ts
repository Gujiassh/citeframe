import assert from "node:assert/strict";
import test from "node:test";

import { ChatStreamContractError, consumeChatStream, parseSseEvents } from "./sse";

test("SSE parser retains incomplete frames across chunks", () => {
  const first = parseSseEvents('event: delta\ndata: {"text":"first"');
  assert.deepEqual(first.events, []);

  const second = parseSseEvents(`${first.remainder}}\n\nevent: unknown\ndata: {"ignored":true}\n\n`);
  assert.deepEqual(second.events, [
    { name: "delta", data: { text: "first" } },
    { name: "unknown", data: { ignored: true } },
  ]);
  assert.equal(second.remainder, "");
});

test("chat stream dispatch ignores unknown events and handles split response chunks", async () => {
  const chunks = [
    'event: meta\ndata: {"threadId":"thread_1","userMessageId":"user_1",',
    '"assistantMessageId":"assistant_1"}\n\nevent: mystery\ndata: {"value":1}\n\n',
    'event: delta\ndata: {"text":"Hello"}\n\nevent: delta\ndata: {"text":" world"}\n\n',
    'event: citations\ndata: {"items":[]}\n\nevent: done\ndata: {"threadId":"thread_1","assistantMessageId":"assistant_1"}\n\n',
  ];
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(new TextEncoder().encode(chunk));
      }
      controller.close();
    },
  });

  const events: string[] = [];
  await consumeChatStream(new Response(stream), {
    onMeta: (payload) => events.push(`meta:${payload.assistantMessageId}`),
    onDelta: (payload) => events.push(`delta:${payload.text}`),
    onCitations: () => events.push("citations"),
    onDone: (payload) => events.push(`done:${payload.threadId}`),
  });

  assert.deepEqual(events, [
    "meta:assistant_1",
    "delta:Hello",
    "delta: world",
    "citations",
    "done:thread_1",
  ]);
});

test("SSE parser dispatches provider errors", async () => {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('event: error\ndata: {"code":"generation_failed","message":"provider failed"}\n\n'));
      controller.close();
    },
  });

  let error: string | undefined;
  await consumeChatStream(new Response(stream), {
    onError: (payload) => { error = `${payload.code}:${payload.message}`; },
  });

  assert.equal(error, "generation_failed:provider failed");
});

test("chat stream rejects malformed terminal events", async () => {
  for (const frame of [
    'event: done\ndata: {"threadId":"thread-1"}\n\n',
    'event: error\ndata: {"code":"generation_failed"}\n\n',
  ]) {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(frame));
        controller.close();
      },
    });

    await assert.rejects(
      consumeChatStream(new Response(stream), {}),
      ChatStreamContractError,
    );
  }
});

test("citation stream rejects an invalid evidence locator instead of filtering it", async () => {
  const valid = {
    id: "citation-1",
    messageId: "message-1",
    citationIndex: 0,
    assetId: "asset-1",
    assetKind: "pdf",
    assetTitle: "paper.pdf",
    sourceAvailable: true,
    excerpt: "evidence",
    locator: { kind: "pdf_page", version: 1, pageNumber: 3 },
    sourceVersions: {
      parserVersion: "parser-v1",
      processingGeneration: 1,
      representationId: "representation-1",
      indexVersion: 1,
    },
  };
  const invalidLocator = { ...valid, id: "citation-2", locator: { kind: "unknown", version: 1 } };
  const payload = JSON.stringify({ items: [valid, invalidLocator] });
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(
        `event: citations\ndata: ${payload}\n\nevent: done\ndata: {"threadId":"thread-1","assistantMessageId":"message-1"}\n\n`,
      ));
      controller.close();
    },
  });

  await assert.rejects(
    consumeChatStream(new Response(stream), {}),
    {
      name: "ChatStreamContractError",
      message: "Chat citations event contains an invalid evidence envelope.",
    },
  );
});

test("citation stream rejects an incomplete evidence source version envelope", async () => {
  const payload = JSON.stringify({
    items: [{
      id: "citation-1",
      messageId: "message-1",
      citationIndex: 0,
      assetId: "asset-1",
      assetKind: "pdf",
      assetTitle: "paper.pdf",
      sourceAvailable: true,
      excerpt: "evidence",
      locator: { kind: "pdf_page", version: 1, pageNumber: 3 },
    }],
  });
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(
        `event: citations\ndata: ${payload}\n\nevent: done\ndata: {"threadId":"thread-1","assistantMessageId":"message-1"}\n\n`,
      ));
      controller.close();
    },
  });

  await assert.rejects(
    consumeChatStream(new Response(stream), {}),
    /invalid evidence envelope/,
  );
});

test("citation stream rejects an unsupported evidence locator version", async () => {
  const payload = JSON.stringify({
    items: [{
      id: "citation-1",
      messageId: "message-1",
      citationIndex: 0,
      assetId: "asset-1",
      assetKind: "pdf",
      assetTitle: "paper.pdf",
      sourceAvailable: true,
      excerpt: "evidence",
      locator: { kind: "pdf_page", version: 2, pageNumber: 3 },
      sourceVersions: {
        parserVersion: "parser-v1",
        processingGeneration: 1,
        representationId: "representation-1",
        indexVersion: 1,
      },
    }],
  });
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(
        `event: citations\ndata: ${payload}\n\nevent: done\ndata: {"threadId":"thread-1","assistantMessageId":"message-1"}\n\n`,
      ));
      controller.close();
    },
  });

  await assert.rejects(
    consumeChatStream(new Response(stream), {}),
    /invalid evidence envelope/,
  );
});

test("citation stream rejects inconsistent PDF region geometry", async () => {
  const payload = JSON.stringify({
    items: [{
      id: "citation-1",
      messageId: "message-1",
      citationIndex: 0,
      assetId: "asset-1",
      assetKind: "pdf",
      assetTitle: "paper.pdf",
      sourceAvailable: true,
      excerpt: "evidence",
      locator: {
        kind: "pdf_region",
        version: 1,
        pageNumber: 3,
        coordinateSpace: "pdf_crop_box_normalized_top_left_v1",
        pageGeometry: {
          cropBoxPoints: [0, 0, 612, 792],
          rotationDegrees: 90,
          displayWidthPoints: 612,
          displayHeightPoints: 792,
        },
        regions: [{ x: 0.1, y: 0.2, width: 0.3, height: 0.1 }],
      },
      sourceVersions: {
        parserVersion: "parser-v1",
        processingGeneration: 1,
        representationId: "representation-1",
        indexVersion: 1,
      },
    }],
  });
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(
        `event: citations\ndata: ${payload}\n\nevent: done\ndata: {"threadId":"thread-1","assistantMessageId":"message-1"}\n\n`,
      ));
      controller.close();
    },
  });

  await assert.rejects(
    consumeChatStream(new Response(stream), {}),
    /invalid evidence envelope/,
  );
});

test("citation stream rejects unsupported evidence coordinate spaces", async () => {
  const payload = JSON.stringify({
    items: [{
      id: "citation-1",
      messageId: "message-1",
      citationIndex: 0,
      assetId: "asset-1",
      assetKind: "pdf",
      assetTitle: "paper.pdf",
      sourceAvailable: true,
      excerpt: "evidence",
      locator: {
        kind: "pdf_region",
        version: 1,
        pageNumber: 3,
        coordinateSpace: "wrong_space",
        pageGeometry: {
          cropBoxPoints: [0, 0, 612, 792],
          rotationDegrees: 0,
          displayWidthPoints: 612,
          displayHeightPoints: 792,
        },
        regions: [{ x: 0.1, y: 0.2, width: 0.3, height: 0.1 }],
      },
      sourceVersions: {
        parserVersion: "parser-v1",
        processingGeneration: 1,
        representationId: "representation-1",
        indexVersion: 1,
      },
    }],
  });
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(
        `event: citations\ndata: ${payload}\n\nevent: done\ndata: {"threadId":"thread-1","assistantMessageId":"message-1"}\n\n`,
      ));
      controller.close();
    },
  });

  await assert.rejects(
    consumeChatStream(new Response(stream), {}),
    /invalid evidence envelope/,
  );
});

test("citation stream rejects image evidence outside canonical geometry", async () => {
  for (const locator of [
    {
      kind: "image_region",
      version: 1,
      coordinateSpace: "image_normalized_top_left_v1",
      widthPixels: 1200,
      heightPixels: 800,
      orientationApplied: false,
      regions: [{ x: 0.1, y: 0.2, width: 0.3, height: 0.1 }],
    },
    {
      kind: "image_region",
      version: 1,
      coordinateSpace: "image_normalized_top_left_v1",
      widthPixels: 1200,
      heightPixels: 800,
      orientationApplied: true,
      regions: [{ x: 0.8, y: 0.2, width: 0.3, height: 0.1 }],
    },
  ]) {
    const payload = JSON.stringify({
      items: [{
        id: "citation-1",
        messageId: "message-1",
        citationIndex: 0,
        assetId: "asset-1",
        assetKind: "image",
        assetTitle: "evidence.png",
        sourceAvailable: true,
        excerpt: "evidence",
        locator,
        sourceVersions: {
          parserVersion: "image-caption-v1",
          processingGeneration: 1,
          representationId: "representation-1",
          indexVersion: 1,
        },
      }],
    });
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          `event: citations\ndata: ${payload}\n\nevent: done\ndata: {"threadId":"thread-1","assistantMessageId":"message-1"}\n\n`,
        ));
        controller.close();
      },
    });

    await assert.rejects(
      consumeChatStream(new Response(stream), {}),
      /invalid evidence envelope/,
    );
  }
});

test("citation stream rejects a malformed citations event", async () => {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(
        'event: citations\ndata: {"citations":[]}\n\nevent: done\ndata: {"threadId":"thread-1","assistantMessageId":"message-1"}\n\n',
      ));
      controller.close();
    },
  });

  await assert.rejects(
    consumeChatStream(new Response(stream), {}),
    /invalid evidence envelope/,
  );
});


test("chat stream surfaces a transport interruption after partial output", async () => {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('event: delta\ndata: {"text":"partial"}\n\n'));
      controller.close();
    },
  });

  const deltas: string[] = [];
  await assert.rejects(
    consumeChatStream(new Response(stream), {
      onDelta: (payload) => deltas.push(payload.text),
    }),
    /ended before completion/,
  );
  assert.deepEqual(deltas, ["partial"]);
});


test("citation stream accepts document_anchor evidence locators", async () => {
  const payload = JSON.stringify({
    items: [{
      id: "citation-doc-1",
      messageId: "message-1",
      citationIndex: 0,
      assetId: "asset-doc",
      assetKind: "document",
      assetTitle: "notes.md",
      sourceAvailable: true,
      excerpt: "paragraph",
      locator: {
        kind: "document_anchor",
        version: 1,
        blockId: "block-2",
        blockKind: "paragraph",
        headingPath: ["Intro"],
        charStart: 10,
        charEnd: 15,
        textSha256: "b".repeat(64),
        normalizationVersion: "document-normalization-v1",
      },
      sourceVersions: {
        parserVersion: "document-parser-v1",
        processingGeneration: 1,
        representationId: "representation-doc",
        indexVersion: 1,
      },
    }],
  });
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(
        `event: citations\ndata: ${payload}\n\nevent: done\ndata: {"threadId":"thread-1","assistantMessageId":"message-1"}\n\n`,
      ));
      controller.close();
    },
  });
  const citations: Array<{ locator: { kind: string } }> = [];
  await consumeChatStream(new Response(stream), {
    onCitations: (event) => {
      citations.push(...event.items);
    },
  });
  assert.equal(citations.length, 1);

  assert.equal(citations[0]?.locator.kind, "document_anchor");
});

test("citation stream accepts S0 office/html/audio/video evidence locators", async () => {
  const sha = "a".repeat(64);
  const cases = [
    {
      kind: "docx_anchor",
      version: 1,
      blockId: "b1",
      blockKind: "paragraph",
      headingPath: ["Intro"],
      charStart: 0,
      charEnd: 4,
      textSha256: sha,
      normalizationVersion: "docx-normalization-v1",
    },
    {
      kind: "xlsx_range",
      version: 1,
      sheetName: "Sheet1",
      startCell: "A1",
      endCell: "B2",
      textSha256: sha,
      displayedText: "42",
      normalizationVersion: "xlsx-normalization-v1",
    },
    {
      kind: "pptx_shape",
      version: 1,
      slideIndex: 1,
      shapeId: "sh1",
      textSha256: sha,
      displayedText: "Title",
      normalizationVersion: "pptx-normalization-v1",
    },
    {
      kind: "html_anchor",
      version: 1,
      blockId: "h1",
      blockKind: "paragraph",
      headingPath: ["Intro"],
      charStart: 0,
      charEnd: 3,
      textSha256: sha,
      normalizationVersion: "html-normalization-v1",
    },
    {
      kind: "audio_range",
      version: 1,
      startMs: 0,
      endMs: 1500,
      textSha256: sha,
      segmentId: "seg-1",
      normalizationVersion: "audio-normalization-v1",
    },
    {
      kind: "video_range",
      version: 1,
      startMs: 100,
      endMs: 2000,
      textSha256: sha,
      segmentId: "vseg-1",
      normalizationVersion: "video-normalization-v1",
    },
    {
      kind: "video_frame",
      version: 1,
      timestampMs: 500,
      frameIndex: null,
      keyframeObjectKey: null,
      normalizationVersion: "video-normalization-v1",
    },
  ] as const;

  for (const locator of cases) {
    const payload = JSON.stringify({
      items: [{
        id: "citation-s0-1",
        messageId: "message-1",
        citationIndex: 0,
        assetId: "asset-1",
        assetKind: "document",
        assetTitle: "fixture",
        sourceAvailable: true,
        excerpt: "excerpt",
        locator,
        sourceVersions: {
          parserVersion: "parser-v1",
          processingGeneration: 1,
          representationId: "representation-1",
          indexVersion: 1,
        },
      }],
    });
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          `event: citations\ndata: ${payload}\n\nevent: done\ndata: {"threadId":"thread-1","assistantMessageId":"message-1"}\n\n`,
        ));
        controller.close();
      },
    });
    const kinds: string[] = [];
    await consumeChatStream(new Response(stream), {
      onCitations: (event) => {
        kinds.push(event.items[0]?.locator.kind ?? "");
      },
    });
    assert.deepEqual(kinds, [locator.kind], `expected to accept ${locator.kind}`);
  }
});
