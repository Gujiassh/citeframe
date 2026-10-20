import test from "node:test";
import assert from "node:assert/strict";
import { prepareMutation } from "./client";
import { alignSession, newSession, revokeSession, updatePending } from "./session-state";
const path = "/workspaces/workspace-a";
test("R2 Home and Back retain exactly the same runtime operation without recreation", () => {
  const operation = prepareMutation("memories/a", "DELETE", { expectedVersion: 1 });
  const initial = newSession("owner-a", path);
  const pending = updatePending(initial, initial.epoch, operation);
  assert.equal(alignSession(pending, "owner-a", "/"), pending);
  assert.equal(alignSession(pending, "owner-a", path).pending, operation);
});
for (const change of ["actor", "workspace", "logout", "revoke"] as const) {
  test(`R2 ${change} clears the triple and rejects late mutation/poll setters`, () => {
    const operation = prepareMutation("memories/a", "DELETE", { expectedVersion: 1 });
    const old = updatePending(newSession("owner-a", path), 0, operation);
    const next = change === "revoke" ? revokeSession(old, old.epoch) : alignSession(old, change === "logout" ? null : change === "actor" ? "owner-b" : "owner-a", change === "workspace" ? "/workspaces/workspace-b" : path);
    assert.equal(next.pending, null);
    assert.notEqual(next.epoch, old.epoch);
    assert.equal(updatePending(next, old.epoch, operation), next);
    assert.equal(updatePending(next, old.epoch, null), next);
    const returned = alignSession(next, "owner-a", path);
    assert.equal(returned.pending, null);
    assert.equal(updatePending(returned, old.epoch, operation), returned);
  });
}
