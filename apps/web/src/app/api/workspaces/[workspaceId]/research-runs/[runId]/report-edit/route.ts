import { NextResponse } from "next/server";

import { getApiBaseUrl } from "@/lib/api-base-url";
import { buildApiHeaders, readRequiredServerSession, unauthorizedResponse } from "@/lib/auth/server-route";

type Params = { workspaceId: string; runId: string };

async function proxy(request: Request, params: Params) {
  const session = await readRequiredServerSession();
  if (!session) return unauthorizedResponse();
  const headers = new Headers(buildApiHeaders(session.userId));
  if (request.method === "PUT") headers.set("content-type", "application/json");
  const path = `/v1/workspaces/${encodeURIComponent(params.workspaceId)}/research-runs/${encodeURIComponent(params.runId)}/report-edit`;
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: request.method,
    headers,
    cache: "no-store",
    body: request.method === "PUT" ? await request.text() : undefined,
    signal: request.signal,
  });
  return new NextResponse(response.body, {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") ?? "application/json", "cache-control": "no-store" },
  });
}

export async function GET(request: Request, context: { params: Promise<Params> }) {
  return proxy(request, await context.params);
}

export async function PUT(request: Request, context: { params: Promise<Params> }) {
  return proxy(request, await context.params);
}
