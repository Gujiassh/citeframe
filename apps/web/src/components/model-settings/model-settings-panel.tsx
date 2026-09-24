"use client";

import { useTranslation } from "@/lib/i18n-context";
import { useWorkspace } from "@/lib/workspace-context";
import { ModelSettingsError } from "@/lib/model-settings/client";
import { modelSettingsRecovery } from "@/lib/model-settings/recovery";
import { useModelSettings } from "@/lib/model-settings/use-model-settings";
import { completedReindexVersion } from "@/lib/assets/reindex-tracker";
import { CapabilityForm } from "./capability-form";
import { ReindexAssets } from "./reindex-assets";

export function ModelSettingsPanel({ workspaceId }: { workspaceId: string }) {
  const { locale } = useTranslation(); const en = locale === "en";
  const { refreshWorkspace, reindexJobs } = useWorkspace();
  const state = useModelSettings(workspaceId, refreshWorkspace, completedReindexVersion(reindexJobs, workspaceId));
  return (
    <section className="space-y-4" aria-label={en ? "Model configuration" : "模型配置"}>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-xs font-bold">{en ? "Model configuration" : "模型配置"}</h3>
        <button type="button" disabled={state.busy} onClick={state.reload} className="text-xs underline disabled:opacity-50">{en ? "Reload configuration" : "重新加载配置"}</button>
      </div>
      {state.error && <p role="alert" className="break-words text-xs text-rose-500">{(state.error instanceof ModelSettingsError && modelSettingsRecovery(state.error.code, locale)) || state.error.message}{state.conflict && (en ? " Reload configuration before saving again." : " 请重新加载配置后再保存。")}</p>}
      {state.saved && <p role="status" className="text-xs text-emerald-600">{en ? "Saved" : "已保存"}</p>}
      {!state.settings ? <p className="text-xs text-zinc-500">{state.error ? (en ? "Configuration unavailable" : "暂无法加载配置") : (en ? "Loading" : "加载中")}</p> : <>
        {!state.settings.encryptionReady && <p role="alert" className="text-xs text-amber-600">{en ? "An administrator must configure the shared model encryption key on API and Worker before saving API keys." : "保存 API Key 前，管理员需为 API 与 Worker 配置共用的模型加密密钥。"}</p>}
        {(["generation", "embedding"] as const).map((capability) => <CapabilityForm
          key={`${capability}:${state.settings![capability].revision}:${state.formVersion}`}
          capability={capability} settings={state.settings![capability]} locale={locale}
          disabled={state.busy || state.conflict || !state.settings!.encryptionReady}
          onDirty={state.clearSaved}
          onSave={(command) => state.save({ [capability]: command })}
        />)}
      </>}
      <ReindexAssets workspaceId={workspaceId} requiredAssetIds={state.settings?.embedding.reindexAssetIds} />
    </section>
  );
}
