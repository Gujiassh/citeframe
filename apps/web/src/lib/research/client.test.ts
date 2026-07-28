import assert from "node:assert/strict";
import test from "node:test";

import { getResearchArtifact } from "./client";

const originalFetch = global.fetch;

test.afterEach(() => {
  global.fetch = originalFetch;
});

function artifact(locator: unknown) {
  return {
    artifact: {
      id: "artifact-1",
      runId: "run-1",
      stepId: "step-1",
      kind: "final_report",
      visibility: "user",
      logicalKey: "final-report",
      schemaVersion: "1",
      supersedesArtifactId: null,
      mediaType: "text/markdown",
      byteSize: 3,
      sha256: "a".repeat(64),
      evidenceCount: 1,
      retentionClass: "workspace_lifetime",
      expiresAt: null,
      createdAt: "2026-07-27T00:00:00Z",
      workflowVersionId: "workflow-1",
      promptVersions: [],
      directPromptVersionId: null,
      claims: [],
      evidence: [{
        evidenceLocatorId: "locator-1",
        assetId: "asset-1",
        assetKind: "pdf",
        assetTitle: "Paper",
        sourceAvailable: true,
        excerpt: "Evidence",
        locator,
        sourceVersions: {
          parserVersion: "parser-v1",
          processingGeneration: 1,
          representationId: "representation-1",
          indexVersion: 1,
        },
      }],
    },
  };
}

test("Research Artifact accepts a canonical existing Evidence locator", async () => {
  global.fetch = async () => new Response(JSON.stringify(artifact({ kind: "pdf_page", version: 1, pageNumber: 3 })), {
    status: 200,
    headers: { "content-type": "application/json" },
  });

  const payload = await getResearchArtifact("workspace-1", "run-1", "artifact-1");
  assert.equal(payload.artifact.evidence[0].locator.kind, "pdf_page");
});

test("Research Artifact rejects unknown candidate locator kinds before opening the Viewer", async () => {
  global.fetch = async () => new Response(JSON.stringify(artifact({ kind: "audio_range", version: 1, startMs: 0, endMs: 1000 })), {
    status: 200,
    headers: { "content-type": "application/json" },
  });

  await assert.rejects(
    () => getResearchArtifact("workspace-1", "run-1", "artifact-1"),
    (error: unknown) => Boolean(error && typeof error === "object" && "code" in error && error.code === "research_artifact_invalid"),
  );
});
