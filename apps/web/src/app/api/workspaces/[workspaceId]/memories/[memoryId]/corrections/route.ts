import { proxyMemoryRequest } from "@/lib/memory/server-route";

export async function POST(request: Request, context: { params: Promise<{ workspaceId: string; memoryId: string }> }) {
  const params = await context.params;
  return proxyMemoryRequest(request, { endpoint: "correct", workspaceId: params.workspaceId, id: params.memoryId });
}
