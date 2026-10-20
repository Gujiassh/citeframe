import { proxyMemoryRequest } from "@/lib/memory/server-route";

export async function POST(request: Request, context: { params: Promise<{ workspaceId: string }> }) {
  const params = await context.params;
  return proxyMemoryRequest(request, { endpoint: "source", workspaceId: params.workspaceId });
}
