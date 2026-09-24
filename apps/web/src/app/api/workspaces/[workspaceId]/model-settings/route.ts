import { NextResponse } from "next/server";
import { getApiBaseUrl } from "@/lib/api-base-url";
import { buildApiHeaders, readRequiredServerSession, unauthorizedResponse } from "@/lib/auth/server-route";

type Context = { params: Promise<{ workspaceId: string }> };
async function forward(request: Request, context: Context, method: "GET" | "PATCH") {
  const session = await readRequiredServerSession();
  if (!session) return unauthorizedResponse();
  const { workspaceId } = await context.params;
  const response = await fetch(`${getApiBaseUrl()}/v1/workspaces/${encodeURIComponent(workspaceId)}/model-settings`, {
    method, cache: "no-store", headers: buildApiHeaders(session.userId, { "Content-Type": "application/json" }),
    ...(method === "PATCH" ? { body: await request.text() } : {}),
  });
  return NextResponse.json(await response.json(), { status: response.status, headers: { "Cache-Control": "no-store" } });
}
export const GET = (request: Request, context: Context) => forward(request, context, "GET");
export const PATCH = (request: Request, context: Context) => forward(request, context, "PATCH");
