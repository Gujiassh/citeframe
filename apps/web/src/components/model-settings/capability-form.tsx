"use client";

import { useState } from "react";
import { modelSettingsRecovery } from "@/lib/model-settings/recovery";
import { modelDraft, requiresExplicitKey, saveModelCommand } from "@/lib/model-settings/form-state";
import type { EditableProtocol, ModelCapability, ModelSettingsCommand, ModelSettingsView } from "@/lib/model-settings/types";

const inputClass = "mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs outline-none focus:ring-1 focus:ring-zinc-400 disabled:opacity-50";
export function CapabilityForm({ capability, settings, disabled, locale, onSave, onDirty }: {
  capability: ModelCapability; settings: ModelSettingsView; disabled: boolean; locale: "zh" | "en";
  onSave: (command: ModelSettingsCommand) => Promise<boolean>;
  onDirty: () => void;
}) {
  const [draft, setDraft] = useState(() => modelDraft(capability, settings));
  const en = locale === "en";
  const needsKey = requiresExplicitKey(settings, draft.baseUrl);
  const field = (key: "baseUrl" | "model" | "apiKey", value: string) => { onDirty(); setDraft((draft) => ({ ...draft, [key]: value })); };
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (await onSave(saveModelCommand(settings, draft))) { setDraft((draft) => ({ ...draft, apiKey: "" })); }
  };
  return (
    <form onSubmit={submit} className="space-y-3 rounded-xl border border-border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-xs font-bold">{capability === "generation" ? (en ? "Generation" : "生成模型") : (en ? "Embedding · 1024 dimensions" : "向量模型 · 1024 维")}</h4>
        <span className="text-[10px] text-zinc-500">{settings.source === "workspace" ? (en ? "Workspace" : "工作区配置") : (en ? "Server defaults" : "服务端默认")} · r{settings.revision}</span>
      </div>
      <p className="break-all text-[10px] text-zinc-500">{settings.protocol} / {settings.model || "—"} · {settings.status === "configured" ? (en ? "Configured" : "已配置") : settings.status === "unavailable" ? (en ? "Unavailable" : "不可用") : (en ? "Not configured" : "未配置")}</p>
      {settings.errorCode && <p className="break-all text-xs text-rose-500">{modelSettingsRecovery(settings.errorCode, locale) ?? settings.errorCode}</p>}
      <fieldset disabled={disabled} className="space-y-3 disabled:opacity-60">
        <label className="block text-xs">{en ? "Protocol" : "协议"}
          <select className={inputClass} value={draft.protocol} onChange={(event) => { onDirty(); setDraft((draft) => ({ ...draft, protocol: event.target.value as EditableProtocol })); }}>
            {capability === "generation" ? <><option value="openai_responses">OpenAI Responses</option><option value="openai_chat_completions">OpenAI Chat Completions</option></> : <option value="openai_embeddings">OpenAI Embeddings</option>}
          </select>
        </label>
        <label className="block text-xs">API Base URL
          <input type="url" autoComplete="off" maxLength={2048} required value={draft.baseUrl} onChange={(event) => field("baseUrl", event.target.value)} className={inputClass} placeholder="https://api.example.com/v1" />
        </label>
        <label className="block text-xs">{en ? "Model" : "模型名称"}
          <input autoComplete="off" maxLength={128} required value={draft.model} onChange={(event) => field("model", event.target.value)} className={inputClass} />
        </label>
        <label className="block text-xs">API Key
          <input type="password" autoComplete="new-password" required={needsKey} value={draft.apiKey} onChange={(event) => field("apiKey", event.target.value)} className={inputClass} placeholder={!needsKey ? (en ? "Configured; leave blank to retain" : "已配置；留空保留") : (en ? "Required for this endpoint" : "请输入此地址的密钥")} />
        </label>
        {needsKey && settings.source === "workspace" && <p className="text-[10px] text-zinc-500">{en ? "Changing the endpoint requires an explicit API key." : "更换接口地址需重新输入 API Key。"}</p>}
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" className="rounded-lg bg-zinc-950 px-3 py-2 text-xs font-semibold text-white dark:bg-white dark:text-zinc-950">{en ? "Save" : "保存"}</button>
          {settings.source === "workspace" && <button type="button" className="text-xs underline" onClick={() => {
            if (window.confirm(en ? "Reset this capability to server defaults? Its saved API key will be removed." : "恢复此能力的服务端默认配置？已保存的 API Key 将被移除。")) void onSave({ action: "reset", expectedRevision: settings.revision });
          }}>{en ? "Reset to server defaults" : "恢复服务端默认"}</button>}
        </div>
      </fieldset>
    </form>
  );
}
