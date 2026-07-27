import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./image-viewer.tsx", import.meta.url), "utf8");

test("image viewer retry refetches current detail and mobile controls expose 44px targets", () => {
  assert.match(source, /fetch\(`\/api\/workspaces\/\$\{workspaceId\}\/assets\/\$\{asset\.id\}`/);
  assert.match(source, /setCurrentGeometry\(null\);[\s\S]*setLoadAttempt/);
  assert.match(source, /h-11 w-11[\s\S]*sm:h-8 sm:w-8/);
  assert.match(source, /data-image-toolbar[\s\S]*overflow-x-auto/);
  assert.match(source, /observer\.observe\(viewport\);[\s\S]*\}, \[viewerSource\.status\]\);/);
});

test("image viewer wires touch pan, pinch zoom, keyboard pan, and keyboard selection", () => {
  assert.match(source, /event\.pointerType === "touch"/);
  assert.match(source, /calculatePinchZoom\(/);
  assert.match(source, /onPointerCancel=/);
  assert.match(source, /onKeyDown=\{handleSurfaceKeyDown\}/);
  assert.match(source, /viewport\.scrollBy/);
  assert.match(source, /event\.key === "Enter" \|\| event\.key === " "/);
  assert.match(source, /tabIndex=\{imageState === "ready" \? 0 : -1\}/);
  assert.match(source, /event\.stopImmediatePropagation\(\)/);
  assert.match(source, /addEventListener\("keydown", handleEscape, \{ capture: true \}\)/);
});

test("image region actions submit only current generation canonical targets", () => {
  assert.match(source, /viewerSource\.mode === "current"/);
  assert.match(source, /kind: "image_region" as const/);
  assert.match(source, /processingGeneration: currentGeometry\?\.processingGeneration \?\? 0/);
  assert.match(source, /coordinateSpace: "image_normalized_top_left_v1" as const/);
  assert.match(source, /regions: \[selection\]/);
  assert.match(source, /<ImageRegionActions/);
});
