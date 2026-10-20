import { proxyMemoryRequest } from "@/lib/memory/server-route";

export async function GET(request: Request, context: { params: Promise<{ workspaceId: string; memoryId: string }> }) {
  const params = await context.params;
  return proxyMemoryRequest(request, { endpoint: "current", workspaceId: params.workspaceId, id: params.memoryId });
}

export async function PATCH(request: Request, context: { params: Promise<{ workspaceId: string; memoryId: string }> }) {
  const params = await context.params;
  return proxyMemoryRequest(request, { endpoint: "deactivate", workspaceId: params.workspaceId, id: params.memoryId });
}

export async function DELETE(request: Request, context: { params: Promise<{ workspaceId: string; memoryId: string }> }) {
  const params = await context.params;
  return proxyMemoryRequest(request, { endpoint: "delete", workspaceId: params.workspaceId, id: params.memoryId });
}
