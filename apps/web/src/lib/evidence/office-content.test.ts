import assert from "node:assert/strict";
import test from "node:test";

import {
  highlightPptxShape,
  parsePptxNormalizedSlides,
  resolvePptxSlides,
  shapeHasGeometry,
} from "./office-content";

test("parsePptxNormalizedSlides groups shapes by slide", () => {
  const slides = parsePptxNormalizedSlides(
    "slide1#2=Title one\nslide1#3=Bullet A\nslide2#4=Closing\nnot-a-line\n",
  );
  assert.equal(slides.length, 2);
  assert.equal(slides[0]?.slideIndex, 1);
  assert.equal(slides[0]?.shapes.length, 2);
  assert.equal(slides[0]?.shapes[0]?.shapeId, "2");
  assert.equal(slides[0]?.shapes[0]?.text, "Title one");
  assert.equal(slides[1]?.slideIndex, 2);
  assert.equal(slides[1]?.shapes[0]?.text, "Closing");
});

test("highlightPptxShape matches slide and shape id", () => {
  const slides = parsePptxNormalizedSlides("slide1#2=Title\nslide2#2=Other\n");
  const hit = highlightPptxShape(slides, "2", 2);
  assert.deepEqual(hit, { slideIndex: 2, shapeId: "2", text: "Other" });
  assert.equal(highlightPptxShape(slides, "missing", 1), null);
  assert.equal(highlightPptxShape(slides, undefined, 1), null);
});

test("resolvePptxSlides prefers structured layout", () => {
  const resolved = resolvePptxSlides({
    assetId: "a",
    representationId: "r",
    processingGeneration: 1,
    format: "pptx",
    contentSha256: "x",
    normalizedText: "slide1#2=legacy",
    layoutVersion: "pptx-layout-v1",
    slideWidthEmu: 1000,
    slideHeightEmu: 500,
    slides: [
      {
        slideIndex: 1,
        shapes: [
          {
            shapeId: "2",
            shapeKind: "text",
            text: "Title",
            xEmu: 10,
            yEmu: 20,
            cxEmu: 100,
            cyEmu: 40,
            mediaPart: null,
            mediaContentType: null,
            hasMedia: false,
          },
        ],
      },
    ],
  });
  assert.equal(resolved.layoutVersion, "pptx-layout-v1");
  assert.equal(resolved.slideWidthEmu, 1000);
  assert.equal(resolved.slides[0]?.shapes[0]?.text, "Title");
  assert.equal(shapeHasGeometry(resolved.slides[0]!.shapes[0]!), true);
});

test("resolvePptxSlides falls back to line parse", () => {
  const resolved = resolvePptxSlides({
    assetId: "a",
    representationId: "r",
    processingGeneration: 1,
    format: "pptx",
    contentSha256: "x",
    normalizedText: "slide1#9=Only text path\n",
  });
  assert.equal(resolved.slides[0]?.shapes[0]?.shapeId, "9");
  assert.equal(shapeHasGeometry(resolved.slides[0]!.shapes[0]!), false);
});
