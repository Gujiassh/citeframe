import { object, uuid, type Endpoint } from "./validation";
import { kinds, statuses } from "./types";
const exact = (v: Record<string, unknown>, fields: string[]) => fields.length === Object.keys(v).length && fields.every(k => Object.hasOwn(v, k));
const member = (v: unknown, values: readonly string[]) => typeof v === "string" && values.includes(v);
const positive = (v: unknown) => typeof v === "number" && Number.isSafeInteger(v) && v > 0;
const timestamp = (v: unknown) => typeof v === "string" && /(?:Z|\+00:00)$/.test(v) && Number.isFinite(Date.parse(v));
const nullableTime = (v: unknown) => v === null || timestamp(v);
const bounded = (v: unknown, max: number) => typeof v === "string" && [...v].length >= 1 && [...v].length <= max;
function sourceRef(v: unknown): boolean {
  return object(v)
    && exact(v, ["sourceId", "sourceVersion", "contentSha256", "span"])
    && uuid(v.sourceId)
    && positive(v.sourceVersion)
    && typeof v.contentSha256 === "string"
    && /^[a-f0-9]{64}$/.test(v.contentSha256)
    && v.span === null;
}
function validMemory(v: unknown, workspaceId: string, ownerId: string): boolean {
  if (!object(v) || !uuid(v.id) || !positive(v.version) || !member(v.intent, ["active", "inactive", "superseded", "deleted"]) || !member(v.validity, ["valid", "invalidated"]) || !member(v.displayStatus, statuses.filter(s => s !== "all"))) return false;
  const head = ["id", "version", "intent", "validity", "displayStatus", "contentAvailable"];
  if (v.contentAvailable === false) return exact(v, [...head, "reason"]) && member(v.reason, ["erased", "source_unavailable"]);
  if (v.contentAvailable !== true || v.intent === "deleted" || v.validity === "invalidated" || v.displayStatus === "invalidated" || !exact(v, [...head, "workspaceId", "ownerUserId", "visibility", "scope", "revisionId", "kind", "confirmation", "conditions", "pinned", "validUntil", "supersedesId", "createdAt", "updatedAt", "content", "sourceRefs"])) return false;
  const scope = v.scope, conditions = v.conditions;
  return v.workspaceId === workspaceId
    && v.ownerUserId === ownerId
    && v.visibility === "private"
    && object(scope)
    && exact(scope, ["kind", "threadId", "runId"])
    && scope.kind === "workspace"
    && scope.threadId === null
    && scope.runId === null
    && uuid(v.revisionId)
    && member(v.kind, kinds)
    && member(v.confirmation, ["explicit_remember", "user_confirmed"])
    && object(conditions)
    && exact(conditions, ["subject", "applicability", "effectiveFrom"])
    && bounded(conditions.subject, 256)
    && bounded(conditions.applicability, 2000)
    && nullableTime(conditions.effectiveFrom)
    && typeof v.pinned === "boolean"
    && nullableTime(v.validUntil)
    && (v.supersedesId === null || uuid(v.supersedesId))
    && timestamp(v.createdAt)
    && timestamp(v.updatedAt)
    && bounded(v.content, 4000)
    && Array.isArray(v.sourceRefs)
    && v.sourceRefs.every(sourceRef);
}
export function validResponse(endpoint: Endpoint, v: unknown, workspaceId: string, ownerId: string, targetId?: string): boolean {
  if (!object(v)) return false;
  if (endpoint === "list" || endpoint === "revisions") return exact(v, ["items", "nextCursor"]) && Array.isArray(v.items) && v.items.length <= 100 && v.items.every(m => validMemory(m, workspaceId, ownerId) && (endpoint !== "revisions" || !targetId || (object(m) && m.id === targetId))) && (v.nextCursor === null || (typeof v.nextCursor === "string" && v.nextCursor.length <= 4096));
  if (endpoint === "current") return exact(v, ["memory"]) && validMemory(v.memory, workspaceId, ownerId) && (!targetId || (object(v.memory) && v.memory.id === targetId));
  if (endpoint === "source") {
    const provenance = v.provenance;
    return exact(v, ["sourceRef", "content", "contentKind", "occurredAt", "sourceState", "provenance", "branchRelation", "truncated", "nextCursor"]) && sourceRef(v.sourceRef) && bounded(v.content, 4000) && v.contentKind === "explicit_instruction" && timestamp(v.occurredAt) && v.sourceState === "current" && object(provenance) && exact(provenance, ["role", "actorUserId", "actorAttribution", "threadId", "runId", "parentMessageId", "confirmation"]) && provenance.role === "user" && provenance.actorUserId === ownerId && provenance.actorAttribution === "authenticated" && provenance.threadId === null && provenance.runId === null && provenance.parentMessageId === null && provenance.confirmation === "explicit_remember" && v.branchRelation === "other_task" && v.truncated === false && v.nextCursor === null;
  }
  const receipt = ["requestId", "operationId", "resultVersion"];
  if (!uuid(v.requestId) || !uuid(v.operationId) || !positive(v.resultVersion)) return false;
  if (endpoint === "request" || endpoint === "operation") return exact(v, [...receipt, "accepted", "state", "resourceId", "currentVersion", "intent", "contentAvailable", "cleanupState"]) && (!targetId || (endpoint === "request" ? v.requestId === targetId : v.operationId === targetId)) && v.accepted === true && v.state === "committed" && uuid(v.resourceId) && positive(v.currentVersion) && member(v.intent, ["active", "inactive", "superseded", "deleted"]) && typeof v.contentAvailable === "boolean" && member(v.cleanupState, ["not_required", "completed"]);
  if (endpoint === "delete") return exact(v, [...receipt, "id", "intent", "version", "cleanupState"]) && uuid(v.id) && (!targetId || v.id === targetId) && v.intent === "deleted" && positive(v.version) && v.cleanupState === "completed";
  return exact(v, [...receipt, "memory", "indexState", ...(endpoint === "correct" ? ["supersededMemoryId"] : [])])
    && validMemory(v.memory, workspaceId, ownerId)
    && v.indexState === "not_enabled"
    && (endpoint !== "deactivate" || !targetId || (object(v.memory) && v.memory.id === targetId))
    && (endpoint !== "correct" || (uuid(v.supersededMemoryId) && (!targetId || v.supersededMemoryId === targetId) && object(v.memory) && v.memory.id !== v.supersededMemoryId));
}
