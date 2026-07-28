"use client";

import { useState } from "react";
import { AlertCircle, BarChart3, Check, Cpu, Save, Settings2, Sliders } from "lucide-react";

import { EvaluationDashboard } from "@/components/evaluation-dashboard";
import { translations, useTranslation } from "@/lib/i18n-context";
import { Workspace, WorkspaceSettingsInput, useWorkspace } from "@/lib/workspace-context";

type SettingsFormProps = {
  currentWorkspace: Workspace;
  onSaveSettings: (workspaceId: string, settings: WorkspaceSettingsInput) => Promise<void>;
  t: (key: keyof typeof translations.zh) => string;
};

function SettingsForm({ currentWorkspace, onSaveSettings, t }: SettingsFormProps) {
  const [prompt, setPrompt] = useState(currentWorkspace.systemPrompt);
  const [topK, setTopK] = useState(currentWorkspace.retrievalTopK);
  const [chunkSize, setChunkSize] = useState(currentWorkspace.chunkSize);
  const [isSaving, setIsSaving] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isOwner = currentWorkspace.role === "owner";

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSaving(true);
    setIsSaved(false);
    setError(null);
    try {
      await onSaveSettings(currentWorkspace.id, {
        systemPrompt: prompt,
        retrievalTopK: topK,
        chunkSize,
      });
      setIsSaved(true);
      window.setTimeout(() => setIsSaved(false), 2000);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Failed to save settings.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex h-full flex-col bg-white transition-colors duration-200 dark:bg-zinc-950">
      <div className="flex-1 overflow-y-auto p-4 sm:p-8">
        <div className="mx-auto w-full max-w-3xl space-y-6">
        <form onSubmit={handleSave} className="space-y-3">
          <div>
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                <Settings2 className="h-3.5 w-3.5 text-zinc-400" />
                {t("settings.promptLabel")}
              </label>
              {isSaved ? (
                <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-600">
                  <Check className="h-3 w-3" />
                  {t("settings.saved")}
                </span>
              ) : null}
            </div>

            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              rows={6}
              disabled={!isOwner || isSaving}
              placeholder={t("settings.promptPlaceholder")}
              className="mt-2 w-full resize-none rounded-xl border border-zinc-200 bg-zinc-50/30 px-3 py-2.5 text-xs leading-5 text-zinc-800 outline-none transition focus:border-zinc-400 focus:bg-white disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-200 dark:focus:border-zinc-700 dark:focus:bg-zinc-950"
            />
          </div>

          <button
            type="submit"
            disabled={!isOwner || isSaving}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-zinc-950 px-4 py-2.5 text-xs font-bold text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-zinc-950 dark:hover:bg-zinc-100"
          >
            <Save className="h-3.5 w-3.5" />
            {isSaving ? t("settings.saving") : t("settings.saveBtn")}
          </button>
          {error ? (
            <p className="flex items-start gap-1.5 text-[10px] font-medium text-red-500">
              <AlertCircle className="mt-0.5 h-3 w-3 shrink-0" />
              {error}
            </p>
          ) : null}
        </form>

        <div className="h-px bg-zinc-100 dark:bg-zinc-800" />

        <div className="space-y-4">
          <h4 className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
            <Cpu className="h-3.5 w-3.5 text-zinc-400" />
            {t("settings.providerLabel")}
          </h4>
          <dl className="grid gap-2 text-xs">
            <div className="flex items-center justify-between gap-4">
              <dt className="text-[10px] font-semibold text-zinc-500">{t("settings.providerOption")}</dt>
              <dd className="font-mono text-[10px] text-zinc-800 dark:text-zinc-200">{currentWorkspace.embeddingProvider}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-[10px] font-semibold text-zinc-500">{t("settings.providerModel")}</dt>
              <dd className="max-w-[65%] break-all text-right font-mono text-[10px] text-zinc-800 dark:text-zinc-200">{currentWorkspace.embeddingModel}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-[10px] font-semibold text-zinc-500">{t("settings.generationModel")}</dt>
              <dd className="max-w-[65%] break-all text-right font-mono text-[10px] text-zinc-800 dark:text-zinc-200">{currentWorkspace.generationProvider} / {currentWorkspace.generationModel}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-[10px] font-semibold text-zinc-500">{t("settings.embeddingDimensions")}</dt>
              <dd className="font-mono text-[10px] text-zinc-800 dark:text-zinc-200">{currentWorkspace.embeddingDimensions} / {currentWorkspace.embeddingVersion}</dd>
            </div>
          </dl>
        </div>

        <div className="h-px bg-zinc-100 dark:bg-zinc-800" />

        <div className="space-y-4">
          <h4 className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
            <Sliders className="h-3.5 w-3.5 text-zinc-400" />
            {t("settings.hyperParams")}
          </h4>

          <div className="space-y-4 text-xs">
            <div>
              <div className="flex justify-between text-[10px] font-semibold text-zinc-500 dark:text-zinc-400">
                <span>{t("settings.topKLabel")}</span>
                <span className="font-bold text-zinc-900 dark:text-white">{topK} chunks</span>
              </div>
              <input
                type="range"
                min="1"
                max="20"
                step="1"
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
                disabled={!isOwner || isSaving}
                className="mt-2 w-full accent-zinc-900 disabled:opacity-50 dark:accent-white"
              />
            </div>

            <div>
              <div className="flex justify-between text-[10px] font-semibold text-zinc-500 dark:text-zinc-400">
                <span>{t("settings.chunkSizeLabel")}</span>
                <span className="font-bold text-zinc-900 dark:text-white">{chunkSize} chars</span>
              </div>
              <input
                type="range"
                min="200"
                max="4000"
                step="50"
                value={chunkSize}
                onChange={(event) => setChunkSize(Number(event.target.value))}
                disabled={!isOwner || isSaving}
                className="mt-2 w-full accent-zinc-900 disabled:opacity-50 dark:accent-white"
              />
            </div>
          </div>
        </div>
        </div>
      </div>
    </div>
  );
}

export function SettingsPanel() {
  const { currentWorkspace, updateWorkspaceSettings } = useWorkspace();
  const { t } = useTranslation();
  const [view, setView] = useState<"workspace" | "evaluation">("workspace");

  if (!currentWorkspace) {
    return null;
  }
  const isOwner = currentWorkspace.role === "owner";
  const activeView = isOwner ? view : "workspace";

  return (
    <div className="flex h-full flex-col bg-white dark:bg-zinc-950">
      <header className="flex shrink-0 flex-col gap-3 border-b border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <div>
          <h3 className="text-sm font-bold text-zinc-900 dark:text-white">{t("settings.header")}</h3>
          <span className="mt-0.5 block text-[10px] font-semibold text-zinc-400 dark:text-zinc-500">{t("settings.subtitle")}</span>
        </div>
        {isOwner ? (
          <div role="tablist" aria-label={t("settings.viewTabs")} className="flex w-fit items-center border border-border bg-background p-1">
            <button type="button" role="tab" aria-selected={activeView === "workspace"} onClick={() => setView("workspace")} className={`flex h-8 items-center gap-1.5 px-3 text-xs font-semibold ${activeView === "workspace" ? "bg-zinc-950 text-white dark:bg-white dark:text-zinc-950" : "text-zinc-500 hover:text-zinc-950 dark:hover:text-white"}`}><Settings2 className="h-3.5 w-3.5" />{t("settings.workspaceTab")}</button>
            <button type="button" role="tab" aria-selected={activeView === "evaluation"} onClick={() => setView("evaluation")} className={`flex h-8 items-center gap-1.5 px-3 text-xs font-semibold ${activeView === "evaluation" ? "bg-zinc-950 text-white dark:bg-white dark:text-zinc-950" : "text-zinc-500 hover:text-zinc-950 dark:hover:text-white"}`}><BarChart3 className="h-3.5 w-3.5" />{t("evaluation.title")}</button>
          </div>
        ) : null}
      </header>
      <div className="min-h-0 flex-1 overflow-hidden">
        {activeView === "workspace" ? (
          <SettingsForm key={currentWorkspace.id} currentWorkspace={currentWorkspace} onSaveSettings={updateWorkspaceSettings} t={t} />
        ) : (
          <div className="h-full overflow-y-auto"><EvaluationDashboard key={currentWorkspace.id} workspaceId={currentWorkspace.id} /></div>
        )}
      </div>
    </div>
  );
}
