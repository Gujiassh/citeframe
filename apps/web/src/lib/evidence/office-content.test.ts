import assert from "node:assert/strict";
import test from "node:test";

import {
  highlightPptxShape,
  parsePptxNormalizedSlides,
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
