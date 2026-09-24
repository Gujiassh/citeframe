import { NextResponse } from "next/server";
import { getApiBaseUrl } from "@/lib/api-base-url";
import { buildApiHeaders, readRequiredServerSession, unauthorizedResponse } from "@/lib/auth/server-route";

export async function POST(_request: Request, context: { params: Promise<{ workspaceId: string; assetId: string }> }) {
  const session = await readRequiredServerSession();
  if (!session) return unauthorizedResponse();
  const { workspaceId, assetId } = await context.params;
  const response = await fetch(`${getApiBaseUrl()}/v1/workspaces/${encodeURIComponent(workspaceId)}/assets/${encodeURIComponent(assetId)}/reindex`, {
    method: "POST", cache: "no-store", headers: buildApiHeaders(session.userId),
  });
  return NextResponse.json(await response.json(), { status: response.status });
}
