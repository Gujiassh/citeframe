import { proxyMemoryRequest } from "@/lib/memory/server-route";

export async function GET(request: Request, context: { params: Promise<{ workspaceId: string; operationId: string }> }) {
  const params = await context.params;
  return proxyMemoryRequest(request, { endpoint: "operation", workspaceId: params.workspaceId, id: params.operationId });
}
