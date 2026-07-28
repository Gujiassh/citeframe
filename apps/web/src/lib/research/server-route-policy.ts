export type ResearchProxyHeaderPolicy = {
  request: readonly string[];
  response: readonly string[];
};

const JSON_RESPONSE_HEADERS = ["content-type"] as const;

export function researchProxyHeaderPolicy(method: string, apiPath: string): ResearchProxyHeaderPolicy {
  const pathname = new URL(apiPath, "http://citeframe.local").pathname;
  if (method === "GET" && pathname.endsWith("/events")) {
    return {
      request: ["accept", "last-event-id"],
      response: ["content-type", "cache-control", "x-accel-buffering"],
    };
  }
  if (method === "GET" && pathname.endsWith("/content")) {
    return {
      request: ["accept"],
      response: ["content-type", "content-length", "content-disposition", "cache-control", "etag"],
    };
  }
  if (method === "POST") {
    return {
      request: ["content-type", "idempotency-key"],
      response: [...JSON_RESPONSE_HEADERS, "location", "idempotency-replayed"],
    };
  }
  return { request: ["accept"], response: [...JSON_RESPONSE_HEADERS, "etag"] };
}
