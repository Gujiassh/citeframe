import assert from "node:assert/strict";
import test from "node:test";
import { AssetListOrder } from "./list-order";
import { replaceAssetsForWorkspace } from "../use-assets";
import type { Asset } from "../workspace-context";

const asset = (id: string, status: Asset["status"] = "uploaded") => ({ id, workspaceId: "a", status, tags: [] }) as unknown as Asset;

test("delayed hydrate cannot erase a later upload or remove its polling trigger", async () => {
  const order = new AssetListOrder(); let assets: Asset[] = [];
  const ticket = order.begin("a");
  const lateHydrate = Promise.resolve([]).then((list) => {
    if (order.accept(ticket)) assets = replaceAssetsForWorkspace("a", list, assets);
  });
  order.invalidate("a"); assets = [asset("fresh")];
  await lateHydrate;
  assert.deepEqual(assets.map((item) => item.id), ["fresh"]);
  assert.ok(assets.some((item) => !["chunked", "ready", "failed", "deleted"].includes(item.status)));
});

test("fresh authoritative list still removes deleted assets without union merging", () => {
  const order = new AssetListOrder(); let assets = [asset("deleted", "deleting")];
  const old = order.begin("a"); order.invalidate("a");
  assert.equal(order.accept(old), false);
  const fresh = order.begin("a");
  if (order.accept(fresh)) assets = replaceAssetsForWorkspace("a", [], assets);
  assert.deepEqual(assets, []);
});

test("out-of-order list responses cannot replace an already applied newer snapshot", () => {
  const order = new AssetListOrder(); const old = order.begin("a"); const fresh = order.begin("a");
  assert.equal(order.accept(fresh), true); assert.equal(order.accept(old), false);
});

test("another workspace upload does not invalidate this workspace list", () => {
  const order = new AssetListOrder(); const a = order.begin("a"); const b = order.begin("b");
  order.invalidate("a"); assert.equal(order.accept(a), false); assert.equal(order.accept(b), true);
});
