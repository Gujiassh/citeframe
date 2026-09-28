import { proxyMemoryRequest } from "@/lib/memory/server-route";

export async function GET(request: Request, context: { params: Promise<{ workspaceId: string }> }) {
  const params = await context.params;
  return proxyMemoryRequest(request, { endpoint: "list", workspaceId: params.workspaceId });
}

export async function POST(request: Request, context: { params: Promise<{ workspaceId: string }> }) {
  const params = await context.params;
  return proxyMemoryRequest(request, { endpoint: "create", workspaceId: params.workspaceId });
}
