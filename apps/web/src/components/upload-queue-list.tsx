"use client";

import type { UploadQueueItem } from "@/lib/assets/upload-queue";
import { useTranslation } from "@/lib/i18n-context";

export function UploadQueueList({ items, onRetry }: { items: UploadQueueItem[]; onRetry: (id: string) => void }) {
  const { locale } = useTranslation();
  const labels = locale === "en"
    ? { queued: "Queued", uploading: "Uploading", submitted: "Submitted", failed: "Failed" }
    : { queued: "排队中", uploading: "上传中", submitted: "已提交", failed: "上传失败" };
  if (!items.length) return null;
  return (
    <section aria-label={locale === "en" ? "Upload queue" : "上传队列"} className="mt-3 rounded-lg border border-border p-2">
      <h3 className="mb-1 text-[10px] font-bold text-zinc-500">{locale === "en" ? "Upload queue" : "上传队列"}</h3>
      <ul className="max-h-48 space-y-2 overflow-y-auto" aria-live="polite" aria-relevant="additions text">
        {items.map((item) => (
          <li key={item.id} data-upload-id={item.id} data-upload-status={item.status} className="text-[11px]">
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate" title={item.filename}>{item.filename}</span>
              <span className="shrink-0 text-zinc-500">{labels[item.status]}</span>
            </div>
            {item.status === "failed" && (
              <div className="mt-1 flex items-start justify-between gap-2">
                <span className="min-w-0 break-words text-rose-500">{item.error}</span>
                <button type="button" className="shrink-0 underline" onClick={() => onRetry(item.id)} aria-label={`${locale === "en" ? "Retry" : "重试"} ${item.filename}`}>
                  {locale === "en" ? "Retry" : "重试"}
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
