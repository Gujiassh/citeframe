import { NextResponse } from "next/server";

import { getApiBaseUrl } from "@/lib/api-base-url";
import { buildApiHeaders, readRequiredServerSession, unauthorizedResponse } from "@/lib/auth/server-route";
import { buildDocumentContentApiUrl } from "@/lib/evidence/document-content";

export async function GET(
  _request: Request,
  context: {
    params: Promise<{
      workspaceId: string;
      assetId: string;
      representationId: string;
    }>;
  },
) {
  const session = await readRequiredServerSession();
  if (!session) {
    return unauthorizedResponse();
  }

  const { workspaceId, assetId, representationId } = await context.params;
  const apiUrl = buildDocumentContentApiUrl(
    getApiBaseUrl(),
    workspaceId,
    assetId,
    representationId,
  );
  const response = await fetch(apiUrl, {
    cache: "no-store",
    headers: buildApiHeaders(session.userId),
  });
  const data = (await response.json()) as unknown;
  return NextResponse.json(data, { status: response.status });
}
