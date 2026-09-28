import { validResponse } from "./response";
import { memoryAdmissionEnabled } from "./activation";
import { errorDetail, errors, knownCode, type ErrorCode } from "./errors";
import { object, uuid, validBody, validKey, validQuery, type Endpoint } from "./validation";
const noStore = { "Cache-Control": "private, no-store, max-age=0", "Vary": "Cookie" };
export type ProxyConfig = { endpoint: Endpoint; workspaceId: string; id?: string };
export type ProxyDependencies = { session: () => Promise<{ userId: string } | null>; headers: (userId: string) => Record<string, string>; baseUrl: string; fetch: typeof fetch };
const methods: Record<Endpoint, string> = { list: "GET", current: "GET", revisions: "GET", request: "GET", operation: "GET", create: "POST", correct: "POST", deactivate: "PATCH", delete: "DELETE", source: "POST" };
export async function memoryProxy(request: Request, config: ProxyConfig, deps: ProxyDependencies): Promise<Response> {
  const { endpoint, workspaceId, id } = config;
  const method = methods[endpoint];
  const mutation = ["create", "correct", "deactivate", "delete"].includes(endpoint);
  let requestId: string | null = null;
  const fail = (code: ErrorCode) => Response.json({ detail: errorDetail(code, requestId) }, { status: errors[code][0], headers: noStore });
  if (request.method !== method) return fail("invalid_request");
  let body: unknown;
  if (method !== "GET") {
    try {
      const raw = await request.text();
      if (new TextEncoder().encode(raw).length > 65536) return fail("invalid_request");
      body = JSON.parse(raw);
    } catch { return fail("invalid_request"); }
  }
  const session = await deps.session();
  if (!session) return fail("authentication_required");
  if (mutation && object(body) && uuid(body.requestId)) requestId = body.requestId;
  if (endpoint === "request" && uuid(id)) requestId = id;
  const url = new URL(request.url);
  if (method !== "GET" && ((request.headers.get("origin") && request.headers.get("origin") !== url.origin) || request.headers.get("sec-fetch-site") === "cross-site")) return fail("invalid_request");
  if (!uuid(workspaceId) || (!["list", "create", "source"].includes(endpoint) && !uuid(id)) || (id !== undefined && !uuid(id)) || !validQuery(endpoint, url.searchParams)) return fail("invalid_request");
  if (method !== "GET" && (!request.headers.get("content-type")?.startsWith("application/json") || !validBody(endpoint, body))) return fail("invalid_request");
  const key = request.headers.get("idempotency-key");
  if (mutation && !validKey(key)) return fail("invalid_request");
  if ((endpoint === "create" || endpoint === "correct") && !memoryAdmissionEnabled) return fail("temporarily_unavailable");
  const suffix: Record<Endpoint, string> = { list: "memories", create: "memories", current: `memories/${id}`, correct: `memories/${id}/corrections`, deactivate: `memories/${id}`, delete: `memories/${id}`, revisions: `memories/${id}/revisions`, request: `memories/requests/${id}`, operation: `memories/operations/${id}`, source: "sources/read" };
  const headers = deps.headers(session.userId);
  if (method !== "GET") headers["Content-Type"] = "application/json";
  if (mutation) headers["Idempotency-Key"] = key!;
  try {
    const response = await deps.fetch(`${deps.baseUrl}/v1/workspaces/${workspaceId}/${suffix[endpoint]}${url.search}`, {
      method, headers, body: method === "GET" ? undefined : JSON.stringify(body), cache: "no-store", redirect: "error", signal: AbortSignal.timeout(20000),
    });
    const payload: unknown = await response.json();
    if (!response.ok) {
      const detail = object(payload) && object(payload.detail) ? payload.detail : null;
      if (detail && knownCode(detail.code) && response.status === errors[detail.code][0]) {
        // Upstream text and arbitrary metadata are never relayed to the browser.
        return Response.json({ detail: errorDetail(detail.code, uuid(detail.requestId) ? detail.requestId : null, typeof detail.currentVersion === "number" ? detail.currentVersion : undefined) }, { status: response.status, headers: noStore });
      }
      return fail(mutation ? "outcome_unknown" : "temporarily_unavailable");
    }
    const expectedStatus = endpoint === "create" || endpoint === "correct" ? 201 : 200;
    if (response.status !== expectedStatus || !validResponse(endpoint, payload, workspaceId, session.userId, id)) return fail(mutation ? "outcome_unknown" : "temporarily_unavailable");
    if (endpoint === "source" && object(payload) && object(body)) {
      const actual = payload.sourceRef, requested = body.sourceRef;
      if (!object(actual) || !object(requested) || ["sourceId", "sourceVersion", "contentSha256", "span"].some(k => actual[k] !== requested[k])) return fail("temporarily_unavailable");
    }
    return Response.json(payload, { status: response.status, headers: noStore });
  } catch { return fail(mutation ? "outcome_unknown" : "temporarily_unavailable"); }
}
