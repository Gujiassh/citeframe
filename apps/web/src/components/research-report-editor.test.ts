import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ResearchReportEditor } from "./research-report-editor";

test("report editor initially exposes original only and disables editing until authoritative load", () => {
  const html = renderToStaticMarkup(createElement(ResearchReportEditor, {
    workspaceId: "workspace", runId: "run", originalArtifactId: "artifact", originalSha256: "sha",
    originalMarkdown: "# Original", canEdit: true, completed: true,
  }));
  assert.match(html, /Original/);
  assert.match(html, /Loading saved report/);
  assert.match(html, /disabled=""[^>]*>User-edited/);
  assert.doesNotMatch(html, />Edit<\/button>/);
  assert.doesNotMatch(html, /Unverified/);
});
