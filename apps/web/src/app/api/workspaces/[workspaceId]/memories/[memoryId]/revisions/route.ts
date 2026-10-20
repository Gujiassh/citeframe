import { proxyMemoryRequest } from "@/lib/memory/server-route";

export async function GET(request: Request, context: { params: Promise<{ workspaceId: string; memoryId: string }> }) {
  const params = await context.params;
  return proxyMemoryRequest(request, { endpoint: "revisions", workspaceId: params.workspaceId, id: params.memoryId });
}
