import { NextResponse } from "next/server";

import { getApiBaseUrl } from "@/lib/api-base-url";
import { buildApiHeaders, readRequiredServerSession, unauthorizedResponse } from "@/lib/auth/server-route";

import { researchProxyHeaderPolicy } from "./server-route-policy";

export async function proxyResearchRequest(request: Request, apiPath: string) {
  const session = await readRequiredServerSession();
  if (!session) return unauthorizedResponse();
  const policy = researchProxyHeaderPolicy(request.method, apiPath);
  const headers = new Headers(buildApiHeaders(session.userId));
  for (const name of policy.request) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const method = request.method;
  const response = await fetch(`${getApiBaseUrl()}${apiPath}`, {
    method,
    cache: "no-store",
    headers,
    body: method === "POST" ? await request.text() : undefined,
    signal: request.signal,
  });
  const responseHeaders = new Headers();
  for (const name of policy.response) {
    const value = response.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new NextResponse(response.body, { status: response.status, headers: responseHeaders });
}
