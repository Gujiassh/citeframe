import assert from "node:assert/strict";
import test from "node:test";

import {
  getProductionUploadDescriptor,
  PRODUCTION_UPLOAD_ACCEPT,
  PRODUCTION_UPLOAD_MIME_TYPES,
} from "./production-upload";

test("production upload contract exposes S0 multimodal MIME types", () => {
  assert.deepEqual(PRODUCTION_UPLOAD_MIME_TYPES, [
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "text/markdown",
    "text/html",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "audio/mpeg",
    "audio/wav",
    "audio/mp4",
    "audio/webm",
    "video/mp4",
    "video/webm",
  ]);
  for (const accept of [
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".md",
    ".markdown",
    ".html",
    ".htm",
    ".docx",
    ".xlsx",
    ".pptx",
    ".mp3",
    ".wav",
    ".m4a",
    ".weba",
    ".mp4",
    ".webm",
  ]) {
    assert.match(PRODUCTION_UPLOAD_ACCEPT, new RegExp(`(^|,)\\${accept}(,|$)`));
  }
});

test("production upload descriptor canonicalizes supported filenames and MIME types", () => {
  assert.deepEqual(
    getProductionUploadDescriptor({ name: "Architecture.JPEG", type: "IMAGE/JPEG" }),
    { mimeType: "image/jpeg" },
  );
  assert.deepEqual(
    getProductionUploadDescriptor({ name: "paper.pdf", type: "application/pdf" }),
    { mimeType: "application/pdf" },
  );
  assert.deepEqual(
    getProductionUploadDescriptor({ name: "notes.MD", type: "text/markdown" }),
    { mimeType: "text/markdown" },
  );
  assert.deepEqual(
    getProductionUploadDescriptor({
      name: "spec.docx",
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }),
    { mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },
  );
});

test("production upload descriptor rejects unsupported and mismatched declarations", () => {
  assert.equal(getProductionUploadDescriptor({ name: "notes.txt", type: "text/plain" }), null);
  assert.equal(getProductionUploadDescriptor({ name: "chart.png", type: "image/jpeg" }), null);
  assert.equal(getProductionUploadDescriptor({ name: "scan.webp", type: "" }), null);
  assert.equal(getProductionUploadDescriptor({ name: "unknown.bin", type: "" }), null);
});
