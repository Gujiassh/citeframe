import { proxyEvaluationRead } from "@/lib/evaluation/server-route";

type Params = { workspaceId: string; segments?: string[] };

export async function GET(request: Request, context: { params: Promise<Params> }) {
  const params = await context.params;
  const suffix = params.segments?.map(encodeURIComponent).join("/");
  const query = new URL(request.url).search;
  return proxyEvaluationRead(
    request,
    `/v1/workspaces/${encodeURIComponent(params.workspaceId)}/evaluations${suffix ? `/${suffix}` : ""}${query}`,
  );
}
