import { NextResponse } from "next/server";

import { buildApiHeaders, readRequiredServerSession, unauthorizedResponse } from "@/lib/auth/server-route";
import { getApiBaseUrl } from "@/lib/api-base-url";

const FORWARDED_HEADERS = [
  "cache-control",
  "content-disposition",
  "content-length",
  "content-type",
];

export async function GET(
  request: Request,
  context: { params: Promise<{ workspaceId: string; assetId: string }> },
) {
  const session = await readRequiredServerSession();
  if (!session) {
    return unauthorizedResponse();
  }

  const { workspaceId, assetId } = await context.params;
  const part = new URL(request.url).searchParams.get("part");
  if (!part) {
    return NextResponse.json({ detail: "Missing part query parameter." }, { status: 400 });
  }

  const apiUrl = new URL(
    `${getApiBaseUrl()}/v1/workspaces/${workspaceId}/assets/${assetId}/pptx-media`,
  );
  apiUrl.searchParams.set("part", part);

  const response = await fetch(apiUrl, {
    cache: "no-store",
    headers: {
      ...buildApiHeaders(session.userId),
    },
  });

  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const data = (await response.json()) as unknown;
      return NextResponse.json(data, { status: response.status });
    }
    const detail = (await response.text()).trim() || "Failed to load PPTX media.";
    return NextResponse.json({ detail }, { status: response.status });
  }

  const headers = new Headers();
  for (const name of FORWARDED_HEADERS) {
    const value = response.headers.get(name);
    if (value) {
      headers.set(name, value);
    }
  }

  return new NextResponse(response.body, {
    status: response.status,
    headers,
  });
}
