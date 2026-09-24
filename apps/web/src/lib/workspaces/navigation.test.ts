import assert from "node:assert/strict";
import test from "node:test";
import { workspaceNavigation } from "./navigation";

test("sidebar selection changes the client route to the chosen workspace", () => {
  let route = "/workspaces/a";
  const navigation = workspaceNavigation((href) => { route = href; }, async () => "unused");
  navigation.open("b");
  assert.equal(route, "/workspaces/b");
});

test("create-and-enter waits for creation and navigates using the returned ID", async () => {
  const routes: string[] = [];
  let finish!: (id: string) => void;
  const navigation = workspaceNavigation((href) => routes.push(href), async (name, description) => {
    assert.equal(name, "New workspace"); assert.equal(description, null);
    return new Promise<string>((resolve) => { finish = resolve; });
  });
  const creating = navigation.createAndOpen("New workspace", null);
  assert.deepEqual(routes, []);
  finish("new-id"); await creating;
  assert.deepEqual(routes, ["/workspaces/new-id"]);
});

test("failed workspace creation preserves the current route", async () => {
  const navigation = workspaceNavigation(() => assert.fail("must not navigate"), async () => { throw new Error("Denied"); });
  await assert.rejects(navigation.createAndOpen("New workspace", null), /Denied/);
});
