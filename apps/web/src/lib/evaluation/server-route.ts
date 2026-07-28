import { NextResponse } from "next/server";

import { getApiBaseUrl } from "@/lib/api-base-url";
import { buildApiHeaders, readRequiredServerSession, unauthorizedResponse } from "@/lib/auth/server-route";

export async function proxyEvaluationRead(request: Request, apiPath: string) {
  const session = await readRequiredServerSession();
  if (!session) return unauthorizedResponse();
  const headers = new Headers(buildApiHeaders(session.userId));
  const accept = request.headers.get("accept");
  if (accept) headers.set("accept", accept);
  const response = await fetch(`${getApiBaseUrl()}${apiPath}`, {
    method: "GET",
    cache: "no-store",
    headers,
    signal: request.signal,
  });
  const responseHeaders = new Headers();
  for (const name of ["content-type", "etag"]) {
    const value = response.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new NextResponse(response.body, { status: response.status, headers: responseHeaders });
}
