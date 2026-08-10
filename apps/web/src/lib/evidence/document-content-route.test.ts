import assert from "node:assert/strict";
import test from "node:test";

import { buildDocumentContentApiUrl } from "./document-content";

test("document content BFF helper preserves auth session gate and upstream URL contract", async () => {
  const source = await import(
    "../../app/api/workspaces/[workspaceId]/assets/[assetId]/representations/[representationId]/content/route"
  );
  assert.equal(typeof source.GET, "function");

  // Route source must remain a pure proxy that requires session and uses the API builder.
  const routeSource = await import("node:fs").then((fs) =>
    fs.readFileSync(
      new URL(
        "../../app/api/workspaces/[workspaceId]/assets/[assetId]/representations/[representationId]/content/route.ts",
        import.meta.url,
      ),
      "utf8",
    )
  );
  assert.match(routeSource, /readRequiredServerSession/);
  assert.match(routeSource, /unauthorizedResponse/);
  assert.match(routeSource, /buildDocumentContentApiUrl/);
  assert.match(routeSource, /buildApiHeaders\(session\.userId\)/);
  assert.doesNotMatch(routeSource, /if \(.*document/);

  const apiUrl = buildDocumentContentApiUrl("http://api.test", "w", "a", "r");
  assert.equal(apiUrl.toString(), "http://api.test/v1/workspaces/w/assets/a/representations/r/content");
});
