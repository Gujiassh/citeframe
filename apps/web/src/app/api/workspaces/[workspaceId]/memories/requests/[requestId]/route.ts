import { proxyMemoryRequest } from "@/lib/memory/server-route";

export async function GET(request: Request, context: { params: Promise<{ workspaceId: string; requestId: string }> }) {
  const params = await context.params;
  return proxyMemoryRequest(request, { endpoint: "request", workspaceId: params.workspaceId, id: params.requestId });
}
