import { NextResponse } from "next/server";

import { buildApiHeaders, readRequiredServerSession, unauthorizedResponse } from "@/lib/auth/server-route";
import { getApiBaseUrl } from "@/lib/api-base-url";

export async function PUT(
  request: Request,
  context: { params: Promise<{ workspaceId: string; assetId: string }> },
) {
  const session = await readRequiredServerSession();
  if (!session) {
    return unauthorizedResponse();
  }

  const { workspaceId, assetId } = await context.params;
  const objectKey = new URL(request.url).searchParams.get("objectKey");
  const contentType = request.headers.get("content-type")?.trim();
  if (!objectKey) {
    return NextResponse.json({ error: { code: "object_key_required", message: "objectKey is required." } }, { status: 400 });
  }
  if (!contentType) {
    return NextResponse.json(
      { error: { code: "content_type_required", message: "Upload Content-Type is required." } },
      { status: 415 },
    );
  }

  const requestInit: RequestInit & { duplex?: "half" } = {
    method: "PUT",
    cache: "no-store",
    headers: {
      ...buildApiHeaders(session.userId),
      "content-type": contentType,
    },
    body: request.body,
    duplex: "half",
  };
  const response = await fetch(
    `${getApiBaseUrl()}/v1/workspaces/${workspaceId}/assets/${assetId}/upload?objectKey=${encodeURIComponent(objectKey)}`,
    requestInit,
  );

  if (!response.ok) {
    const data = (await response.json()) as unknown;
    return NextResponse.json(data, { status: response.status });
  }

  return new NextResponse(null, { status: 204 });
}
