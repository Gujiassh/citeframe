"use client";

import { useWorkspace } from "@/lib/workspace-context";
import { useTranslation } from "@/lib/i18n-context";
import { reindexActive } from "@/lib/assets/reindex-tracker";

export function ReindexAssets({ workspaceId, requiredAssetIds = [] }: { workspaceId: string; requiredAssetIds?: string[] }) {
  const { assets, reindexJobs, reindexAsset, refreshReindexJob } = useWorkspace();
  const { locale } = useTranslation(); const en = locale === "en";
  const items = assets.filter((asset) => asset.workspaceId === workspaceId && ["chunked", "embedding", "ready", "failed"].includes(asset.status));
  if (!items.length) return null;
  const labels: Record<string, string> = en ? { queued: "Queued", running: "Reindexing", succeeded: "Index updated", failed: "Reindex failed", cancelled: "Cancelled" } : { queued: "排队中", running: "重建中", succeeded: "索引已更新", failed: "重建失败", cancelled: "已取消" };
  return (
    <section className="space-y-3 border-t border-border pt-4" aria-label={en ? "Reindex assets" : "重建文件索引"}>
      <h4 className="text-xs font-bold">{en ? "Reindex assets" : "重建文件索引"}</h4>
      <p className="text-[10px] text-zinc-500">{en ? "Reindex uses the current embedding configuration. Existing index data is retained until replacement succeeds." : "使用当前向量配置重建；成功替换前保留已有索引数据。"}</p>
      <ul className="space-y-3">
        {items.map((asset) => {
          const row = reindexJobs.find((item) => item.workspaceId === workspaceId && item.assetId === asset.id);
          const error = row?.error || row?.job?.errorMessage;
          return <li key={asset.id} className="rounded-lg border border-border p-3 text-xs" data-reindex-asset-id={asset.id}>
            <div className="flex items-center justify-between gap-3">
              <span className="min-w-0 truncate" title={asset.title}>{asset.title}</span>
              <button type="button" disabled={reindexActive(row)} className="shrink-0 underline disabled:opacity-50" onClick={() => void reindexAsset(workspaceId, asset.id)} aria-label={`${en ? "Reindex" : "重建索引"} ${asset.title}`}>{en ? "Reindex" : "重建索引"}</button>
            </div>
            {requiredAssetIds.includes(asset.id) && <p className="mt-1 text-[10px] text-amber-600">{en ? "Embedding configuration changed; reindex required." : "向量配置已变更，需重建索引。"}</p>}
            {row && <p role="status" className="mt-1 text-[10px] text-zinc-500">{row.submitting ? (en ? "Submitting" : "提交中") : row.job ? labels[row.job.status] ?? row.job.status : null}</p>}
            {error && <p role="alert" className="mt-1 break-words text-[10px] text-rose-500">{error}</p>}
            {row?.error && row.job && <button type="button" className="mt-1 text-[10px] underline" onClick={() => refreshReindexJob(workspaceId, asset.id)}>{en ? "Refresh job status" : "重新查询任务状态"}</button>}
          </li>;
        })}
      </ul>
    </section>
  );
}
