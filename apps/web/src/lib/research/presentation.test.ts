import assert from "node:assert/strict";
import test from "node:test";
import type { ResearchRunDetail } from "./types";

import { canManageResearchRun, canSubmitWorkspaceQuestion, getFrozenResearchProfile, latestResearchRun, sortResearchRunsLatest } from "./presentation";

test("Quick questions still require a chat thread", () => {
  assert.equal(canSubmitWorkspaceQuestion({
    mode: "quick",
    question: "Compare the evidence",
    assetsReady: true,
    quickThreadReady: false,
    busy: false,
  }), false);
});

test("Research questions do not require a chat thread", () => {
  assert.equal(canSubmitWorkspaceQuestion({
    mode: "research",
    question: "Compare the evidence",
    assetsReady: true,
    quickThreadReady: false,
    busy: false,
  }), true);
});

test("Neither mode submits without ready assets or a question", () => {
  assert.equal(canSubmitWorkspaceQuestion({
    mode: "research",
    question: " ",
    assetsReady: true,
    quickThreadReady: true,
    busy: false,
  }), false);
  assert.equal(canSubmitWorkspaceQuestion({
    mode: "research",
    question: "Compare",
    assetsReady: false,
    quickThreadReady: true,
    busy: false,
  }), false);
});


const run = (id: string, createdAt: string, createdByUserId = "creator") => ({
  id, workspaceId: "workspace-1", createdByUserId, question: id, status: "completed" as const,
  stateVersion: 1, requestedAssetScope: { mode: "all_ready" as const }, frozenAssetCount: 1,
  currentPlanRevisionNumber: 1, currentEventSeq: 1, estimatedCost: null,
  consumedCost: { currency: "USD", amountMicros: 0 }, createdAt, updatedAt: createdAt, finishedAt: createdAt,
});

test("Research history chooses the latest run by createdAt and id, not response order", () => {
  const items = [run("older", "2026-07-26T00:00:00Z"), run("z-latest", "2026-07-27T00:00:00Z"), run("a-latest", "2026-07-27T00:00:00Z")];
  assert.equal(latestResearchRun(items)?.id, "z-latest");
  assert.deepEqual(sortResearchRunsLatest(items).map((item) => item.id), ["z-latest", "a-latest", "older"]);
});


test("Only the Research run creator can manage creator-only actions", () => {
  const item = run("run-1", "2026-07-27T00:00:00Z");
  assert.equal(canManageResearchRun(item, "creator"), true);
  assert.equal(canManageResearchRun(item, "reader"), false);
  assert.equal(canManageResearchRun(item, null), false);
});

const providerSnapshot = (generationModel: string) => ({
  generationProvider: "openai",
  generationModel,
  embeddingProvider: "ollama",
  embeddingModel: "frozen-embedding",
  embeddingVersion: "embedding-v1",
  retrievalStrategy: "hybrid",
  retrievalTopK: 6,
  providerConfigFingerprint: "a".repeat(64),
  pricingVersion: null,
  dataBoundaryPolicyVersion: "v1",
});

test("Approved execution snapshot wins over a complete proposed revision", () => {
  const frozen = providerSnapshot("frozen-model");
  const proposed = providerSnapshot("revision-model");
  const result = getFrozenResearchProfile({
    researchExecution: { execution: { provider: frozen } },
    plan: {
      status: "proposed",
      inputSnapshot: { proposedResearchExecution: { provider: proposed } },
    },
  } as unknown as ResearchRunDetail);

  assert.deepEqual(result, { source: "execution", snapshot: frozen });
});

test("A proposed plan uses its frozen proposed research execution snapshot", () => {
  const proposed = providerSnapshot("revision-model");
  const result = getFrozenResearchProfile({
    researchExecution: null,
    plan: {
      status: "proposed",
      inputSnapshot: { proposedResearchExecution: { provider: proposed } },
    },
  } as unknown as ResearchRunDetail);

  assert.deepEqual(result, { source: "proposed_revision", snapshot: proposed });
});

test("An incomplete execution snapshot never falls through to a proposed revision", () => {
  const result = getFrozenResearchProfile({
    researchExecution: { execution: { provider: { generationProvider: "openai" } } },
    plan: {
      status: "proposed",
      inputSnapshot: { proposedResearchExecution: { provider: providerSnapshot("revision-model") } },
    },
  } as unknown as ResearchRunDetail);

  assert.equal(result, null);
});

test("An incomplete proposed revision snapshot is unavailable", () => {
  const result = getFrozenResearchProfile({
    researchExecution: null,
    plan: {
      status: "proposed",
      inputSnapshot: { proposedResearchExecution: { provider: { generationProvider: "openai" } } },
    },
  } as unknown as ResearchRunDetail);

  assert.equal(result, null);
});

test("Approved or legacy runs without execution snapshots stay unavailable", () => {
  assert.equal(getFrozenResearchProfile({ plan: null } as unknown as ResearchRunDetail), null);
  assert.equal(getFrozenResearchProfile({
    researchExecution: null,
    plan: { status: "approved", inputSnapshot: { proposedResearchExecution: { provider: providerSnapshot("revision-model") } } },
  } as unknown as ResearchRunDetail), null);
});
