export const RESEARCH_EVENT_NAMES = [
  "run_created", "run_status_changed", "step_queued", "step_started", "step_waiting",
  "step_succeeded", "step_failed", "attempt_abandoned", "approval_requested",
  "decision_submitted", "cancel_requested", "artifact_published", "run_completed",
  "run_failed", "run_cancelled",
] as const;

export type ResearchEventName = (typeof RESEARCH_EVENT_NAMES)[number];
export type ResearchEvent = {
  schemaVersion: 1;
  eventId: string;
  runId: string;
  seq: number;
  type: ResearchEventName;
  occurredAt: string;
  data: Record<string, unknown>;
};

const EVENT_NAMES = new Set<string>(RESEARCH_EVENT_NAMES);
const EVENT_DATA_FIELDS: Record<ResearchEventName, readonly string[]> = {
  run_created: ["status", "createdByUserId", "runStateVersion"],
  run_status_changed: ["previousStatus", "status", "runStateVersion", "reasonCode"],
  step_queued: ["stepId", "stepKind", "branchKey", "attemptNumber", "stepStateVersion", "runStateVersion"],
  step_started: ["stepId", "stepKind", "branchKey", "attemptId", "attemptNumber", "stepStateVersion", "runStateVersion"],
  step_waiting: ["stepId", "stepKind", "decisionId", "decisionType", "stepStateVersion", "decisionStateVersion", "runStateVersion"],
  step_succeeded: ["stepId", "stepKind", "attemptId", "attemptNumber", "evidenceCount", "artifactIds", "stepStateVersion", "runStateVersion"],
  step_failed: ["stepId", "stepKind", "attemptId", "attemptNumber", "reasonCode", "retryable", "stepStateVersion", "runStateVersion"],
  attempt_abandoned: ["stepId", "attemptId", "attemptNumber", "reasonCode", "stepStateVersion", "runStateVersion"],
  approval_requested: ["decisionId", "decisionType", "inputArtifactId", "inputArtifactSha256", "decisionStateVersion", "runStateVersion"],
  decision_submitted: ["decisionId", "decisionType", "inputArtifactId", "inputArtifactSha256", "action", "actorUserId", "decisionStateVersion", "runStateVersion"],
  cancel_requested: ["actorUserId", "reasonCode", "runStateVersion"],
  artifact_published: ["artifactId", "artifactKind", "visibility", "byteSize", "sha256", "runStateVersion"],
  run_completed: ["status", "finalArtifactId", "runStateVersion"],
  run_failed: ["status", "reasonCode", "retryable", "runStateVersion"],
  run_cancelled: ["status", "reasonCode", "runStateVersion"],
};
const ENVELOPE_FIELDS = ["schemaVersion", "eventId", "runId", "seq", "type", "occurredAt", "data"];
const NON_NEGATIVE_INTEGER_FIELDS = new Set([
  "attemptNumber", "stepStateVersion", "runStateVersion", "decisionStateVersion", "evidenceCount", "byteSize",
]);
const RUN_STATUSES = new Set([
  "planning", "awaiting_plan_approval", "queued", "running", "awaiting_human_decision",
  "awaiting_retry", "cancel_requested", "completed", "failed", "cancelled",
]);
const STEP_KINDS = new Set([
  "planner", "plan_approval_gate", "researcher", "join", "verifier", "critic",
  "conflict_decision_gate", "synthesizer", "artifact_publisher",
]);
const DECISION_TYPES = new Set(["plan_approval", "conflict_resolution"]);
const ARTIFACT_KINDS = new Set([
  "research_plan", "evidence_bundle", "verification_result", "conflict_report",
  "execution_checkpoint", "final_report", "trace_export",
]);
const ARTIFACT_VISIBILITIES = new Set(["user", "internal"]);
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

function hasExactFields(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const canonical = [...expected].sort();
  return actual.length === canonical.length && actual.every((field, index) => field === canonical[index]);
}

function isEventDataValid(type: ResearchEventName, data: Record<string, unknown>): boolean {
  const fields = EVENT_DATA_FIELDS[type];
  if (!hasExactFields(data, fields)) return false;
  for (const [field, value] of Object.entries(data)) {
    if (NON_NEGATIVE_INTEGER_FIELDS.has(field) && (!Number.isInteger(value) || (value as number) < 0)) return false;
    if (field === "retryable" && typeof value !== "boolean") return false;
    if (field === "artifactIds" && (
      !Array.isArray(value)
      || value.some((item) => typeof item !== "string" || !item)
      || value.length !== new Set(value).size
    )) return false;
    if ((field === "branchKey" || field === "reasonCode") && value !== null && typeof value !== "string") return false;
    if (
      !NON_NEGATIVE_INTEGER_FIELDS.has(field)
      && field !== "retryable"
      && field !== "artifactIds"
      && field !== "branchKey"
      && field !== "reasonCode"
      && (typeof value !== "string" || !value)
    ) return false;
  }
  if (("status" in data && !RUN_STATUSES.has(data.status as string))
    || ("previousStatus" in data && !RUN_STATUSES.has(data.previousStatus as string))) return false;
  if ("stepKind" in data && !STEP_KINDS.has(data.stepKind as string)) return false;
  if ("decisionType" in data && !DECISION_TYPES.has(data.decisionType as string)) return false;
  if ("artifactKind" in data && !ARTIFACT_KINDS.has(data.artifactKind as string)) return false;
  if ("visibility" in data && !ARTIFACT_VISIBILITIES.has(data.visibility as string)) return false;
  if ("inputArtifactSha256" in data && !SHA256_PATTERN.test(data.inputArtifactSha256 as string)) return false;
  if ("sha256" in data && !SHA256_PATTERN.test(data.sha256 as string)) return false;
  if ("action" in data) {
    const actions = data.decisionType === "plan_approval"
      ? new Set(["approve", "request_revision", "cancel_run"])
      : new Set(["exclude_conflicted_claims", "keep_as_unresolved", "cancel_run"]);
    if (!actions.has(data.action as string)) return false;
  }
  return true;
}

export class ResearchStreamContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ResearchStreamContractError";
  }
}

export class ResearchStreamGapError extends ResearchStreamContractError {
  constructor() {
    super("Research event sequence has a gap.");
    this.name = "ResearchStreamGapError";
  }
}

function parseBlock(block: string): ResearchEvent | null {
  let id = "";
  let name = "";
  const data: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator < 0 ? line : line.slice(0, separator);
    const value = separator < 0 ? "" : line.slice(separator + 1).trimStart();
    if (field === "id") id = value;
    if (field === "event") name = value;
    if (field === "data") data.push(value);
  }
  if (!data.length) return null;
  if (!EVENT_NAMES.has(name)) throw new ResearchStreamContractError(`Unknown Research event: ${name}`);
  let payload: unknown;
  try { payload = JSON.parse(data.join("\n")); } catch { throw new ResearchStreamContractError("Research event data must be JSON."); }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new ResearchStreamContractError("Research event envelope must be an object.");
  const event = payload as Record<string, unknown>;
  if (
    !hasExactFields(event, ENVELOPE_FIELDS)
    || event.schemaVersion !== 1
    || typeof event.eventId !== "string"
    || !event.eventId
    || typeof event.runId !== "string"
    || !event.runId
    || !Number.isInteger(event.seq)
    || (event.seq as number) < 1
    || typeof event.occurredAt !== "string"
    || !event.occurredAt
    || Number.isNaN(Date.parse(event.occurredAt))
    || event.type !== name
    || !event.data
    || typeof event.data !== "object"
    || Array.isArray(event.data)
  ) {
    throw new ResearchStreamContractError("Research event envelope is invalid.");
  }
  if (!isEventDataValid(name as ResearchEventName, event.data as Record<string, unknown>)) {
    throw new ResearchStreamContractError("Research event data is invalid.");
  }
  if (id !== String(event.seq)) throw new ResearchStreamContractError("Research event id does not match seq.");
  return event as ResearchEvent;
}

export function parseResearchSse(input: string): { events: ResearchEvent[]; remainder: string } {
  const events: ResearchEvent[] = [];
  let remainder = input;
  while (true) {
    const separator = /\r?\n\r?\n/.exec(remainder);
    if (!separator || separator.index === undefined) break;
    const event = parseBlock(remainder.slice(0, separator.index));
    remainder = remainder.slice(separator.index + separator[0].length);
    if (event) events.push(event);
  }
  return { events, remainder };
}

export async function consumeResearchStream(response: Response, runId: string, afterSeq: number, onEvent: (event: ResearchEvent) => void): Promise<number> {
  if (!response.body) throw new ResearchStreamContractError("Research stream has no body.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let lastSeq = afterSeq;
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const parsed = parseResearchSse(buffer);
    buffer = parsed.remainder;
    for (const event of parsed.events) {
      if (event.runId !== runId) throw new ResearchStreamContractError("Research event run does not match the stream.");
      if (event.seq <= lastSeq) continue;
      if (event.seq !== lastSeq + 1) throw new ResearchStreamGapError();
      onEvent(event);
      lastSeq = event.seq;
    }
    if (done) break;
  }
  return lastSeq;
}


type ResearchStreamLoopOptions = {
  runId: string;
  afterSeq: number;
  signal: AbortSignal;
  open: (afterSeq: number, signal: AbortSignal) => Promise<Response>;
  onEvent: (event: ResearchEvent) => void;
  onReconnect: (afterSeq: number) => void;
  onHistoryUnavailable: () => Promise<number>;
  onCursorConflict: () => Promise<number>;
  reconnectDelayMs?: number;
};

function waitForReconnect(delayMs: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    const timeout = globalThis.setTimeout(resolve, delayMs);
    signal.addEventListener("abort", () => {
      globalThis.clearTimeout(timeout);
      resolve();
    }, { once: true });
  });
}

export async function runResearchStreamLoop(options: ResearchStreamLoopOptions): Promise<void> {
  let cursor = options.afterSeq;
  const delayMs = options.reconnectDelayMs ?? 1_000;

  while (!options.signal.aborted) {
    try {
      const response = await options.open(cursor, options.signal);
      cursor = await consumeResearchStream(response, options.runId, cursor, (event) => {
        cursor = event.seq;
        options.onEvent(event);
      });
      if (!options.signal.aborted) options.onReconnect(cursor);
    } catch (reason) {
      if (options.signal.aborted) return;
      if (reason && typeof reason === "object" && "status" in reason && reason.status === 410) {
        cursor = await options.onHistoryUnavailable();
        if (options.signal.aborted) return;
        options.onReconnect(cursor);
      } else if (reason && typeof reason === "object" && "status" in reason && reason.status === 409) {
        cursor = await options.onCursorConflict();
        if (options.signal.aborted) return;
        options.onReconnect(cursor);
      } else {
        if (reason instanceof ResearchStreamContractError && !(reason instanceof ResearchStreamGapError)) throw reason;
        options.onReconnect(cursor);
      }
    }
    await waitForReconnect(delayMs, options.signal);
  }
}
