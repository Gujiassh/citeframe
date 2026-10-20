import { kinds, statuses } from "./types";
export const uuid = (v: unknown): v is string => typeof v === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(v);
export const object = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);
const keys = (v: Record<string, unknown>, allowed: string[]) => Object.keys(v).every(k => allowed.includes(k));
const text = (v: unknown, max: number) => typeof v === "string" && [...v].length >= 1 && [...v].length <= max;
const version = (v: unknown) => typeof v === "number" && Number.isSafeInteger(v) && v >= 1;
const timestamp = (v: unknown) => v === null || (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v)));
export type Endpoint = "list" | "current" | "revisions" | "create" | "correct" | "deactivate" | "delete" | "request" | "operation" | "source";
export function validBody(endpoint: Endpoint, v: unknown): boolean {
  if (!object(v)) return false;
  if (endpoint === "source") {
    const r = v.sourceRef;
    return keys(v, ["sourceRef"]) && object(r) && keys(r, ["sourceId", "sourceVersion", "contentSha256", "span"]) && uuid(r.sourceId) && version(r.sourceVersion) && typeof r.contentSha256 === "string" && /^[a-f0-9]{64}$/.test(r.contentSha256) && r.span === null;
  }
  if (!uuid(v.requestId)) return false;
  if (endpoint === "delete" || endpoint === "deactivate") return keys(v, ["requestId", "expectedVersion", ...(endpoint === "deactivate" ? ["intent"] : [])]) && version(v.expectedVersion) && (endpoint !== "deactivate" || v.intent === "inactive");
  if (endpoint !== "create" && endpoint !== "correct") return false;
  if (!keys(v, ["requestId", "kind", "content", "conditions", "pinned", "validUntil", ...(endpoint === "create" ? ["scope", "sourceRefs"] : ["expectedVersion"])])) return false;
  const c = v.conditions;
  if (!object(c) || !keys(c, ["subject", "applicability", "effectiveFrom"]) || !text(c.subject, 256) || !text(c.applicability, 2000) || (c.effectiveFrom !== undefined && !timestamp(c.effectiveFrom))) return false;
  if (!kinds.includes(v.kind as typeof kinds[number]) || !text(v.content, 4000) || (v.pinned !== undefined && typeof v.pinned !== "boolean") || (v.pinned === true && v.kind !== "constraint" && v.kind !== "decision") || (v.validUntil !== undefined && !timestamp(v.validUntil))) return false;
  return endpoint === "correct" ? version(v.expectedVersion) : object(v.scope) && keys(v.scope, ["kind"]) && v.scope.kind === "workspace" && (v.sourceRefs === undefined || (Array.isArray(v.sourceRefs) && v.sourceRefs.length === 0));
}
export function validQuery(endpoint: Endpoint, query: URLSearchParams): boolean {
  const allowed = endpoint === "list" ? ["status", "scope", "limit", "cursor"] : endpoint === "revisions" ? ["limit", "cursor"] : [];
  for (const [key, value] of query) {
    if (!allowed.includes(key) || query.getAll(key).length !== 1) return false;
    if (key === "status" && !statuses.includes(value as typeof statuses[number])) return false;
    if (key === "scope" && value !== "workspace") return false;
    if (key === "limit" && (!/^[1-9][0-9]*$/.test(value) || Number(value) > 100)) return false;
    if (key === "cursor" && (!value || value.length > 4096)) return false;
  }
  return true;
}
export function validKey(v: string | null): v is string { return v !== null && /^[\x21-\x7e]{8,128}$/.test(v); }
