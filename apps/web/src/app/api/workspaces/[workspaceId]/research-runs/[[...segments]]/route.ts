import { proxyResearchRequest } from "@/lib/research/server-route";

type Params = { workspaceId: string; segments?: string[] };

function apiPath(params: Params, request: Request): string {
  const suffix = params.segments?.map(encodeURIComponent).join("/");
  const query = new URL(request.url).search;
  return `/v1/workspaces/${encodeURIComponent(params.workspaceId)}/research-runs${suffix ? `/${suffix}` : ""}${query}`;
}

export async function GET(request: Request, context: { params: Promise<Params> }) {
  return proxyResearchRequest(request, apiPath(await context.params, request));
}

export async function POST(request: Request, context: { params: Promise<Params> }) {
  return proxyResearchRequest(request, apiPath(await context.params, request));
}
