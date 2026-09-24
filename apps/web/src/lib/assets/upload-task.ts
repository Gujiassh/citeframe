import { getProductionUploadDescriptor } from "./production-upload";
import type { AssetListResponseDto, AssetSummaryDto, CreateUploadSessionResponseDto, FinalizeUploadResponseDto } from "./types";
import type { UploadTask } from "./upload-queue";

type UploadOptions = {
  file: File;
  workspaceId: string;
  locale: "zh" | "en";
  onAsset: (asset: AssetSummaryDto, created: boolean) => void;
};

// Retain the session and completed stages for explicit retries of this file only.
export function createAssetUploadTask({ file, workspaceId, locale, onAsset }: UploadOptions): UploadTask {
  let session: CreateUploadSessionResponseDto | undefined;
  let uploaded = false;
  let finalizeAttempted = false;
  const message = (en: string, zh: string) => locale === "en" ? en : zh;

  return async (signal) => {
    const request = async <T>(url: string, init: RequestInit, fallback: string): Promise<T> => {
      signal.throwIfAborted();
      const response = await fetch(url, { ...init, signal });
      const payload = await response.json().catch(() => undefined);
      signal.throwIfAborted();
      if (!response.ok) throw new Error(payload?.error?.message || payload?.detail || fallback);
      return payload as T;
    };
    const publish = (asset: AssetSummaryDto, created: boolean) => {
      signal.throwIfAborted();
      onAsset(asset, created);
    };
    const descriptor = getProductionUploadDescriptor(file);
    if (!descriptor) throw new Error(message(
      "Choose a PDF, PNG, JPEG, WebP, or Markdown file.",
      "请选择 PDF、PNG、JPEG、WebP 或 Markdown 文件。",
    ));

    if (!session) {
      const payload = await request<CreateUploadSessionResponseDto>(`/api/workspaces/${workspaceId}/assets/upload-session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sourceFilename: file.name, mimeType: descriptor.mimeType, byteSize: file.size }),
      }, message("Failed to create upload session.", "创建上传会话失败。"));
      if (!payload?.asset || !payload.upload?.url) throw new Error(message("Invalid upload session.", "上传会话无效。"));
      session = payload;
      publish(session.asset, true);
    }

    const assetUrl = `/api/workspaces/${workspaceId}/assets/${session.asset.id}`;
    // A lost finalize response can still have committed the ingestion job.
    if (finalizeAttempted) {
      const list = await request<AssetListResponseDto>(`/api/workspaces/${workspaceId}/assets`, { cache: "no-store" }, message("Failed to check upload.", "检查上传状态失败。"));
      const existing = list?.items?.find((item) => item.id === session!.asset.id);
      if (!existing) throw new Error(message("Asset no longer exists.", "文件已不存在。"));
      if (["uploaded", "parsing", "chunking", "chunked", "embedding", "ready", "failed"].includes(existing.status)) {
        publish(existing, false);
        return;
      }
      if (existing.status !== "pending_upload") throw new Error(message("Asset is no longer awaiting upload.", "文件已不处于待上传状态。"));
    }

    if (!uploaded) {
      await request(session.upload.url!, {
        method: session.upload.method, headers: session.upload.headers, body: file,
      }, message("Failed to upload file.", "上传文件失败。"));
      uploaded = true;
    }
    finalizeAttempted = true;
    const payload = await request<FinalizeUploadResponseDto>(`${assetUrl}/finalize-upload`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ objectKey: session.upload.objectKey }),
    }, message("Failed to finalize upload.", "确认上传失败。"));
    if (!payload?.asset) throw new Error(message("Invalid finalize response.", "确认上传响应无效。"));
    publish(payload.asset, false);
  };
}
