"use client";

import React, { useEffect, useRef, useState } from "react";
import { ArrowUp, Library, MessageCircleQuestion, Search, X } from "lucide-react";

import { useAuth } from "@/lib/auth/auth-context";
import { isNearChatBottom } from "@/lib/chat-scroll";
import type { InputEvidence } from "@/lib/chat/types";
import { getLocatorSummary } from "@/lib/evidence/types";
import { useTranslation } from "@/lib/i18n-context";
import { canSubmitWorkspaceQuestion, type WorkspaceQuestionMode } from "@/lib/research/presentation";
import { useResearch } from "@/lib/use-research";
import { Citation, useWorkspace } from "@/lib/workspace-context";

import { ChatBubble } from "./chat-bubble";
import { ResearchRunPanel } from "./research-run-panel";

export function ChatPanel() {
  const {
    currentWorkspace,
    activeThread,
    assets,
    selectedAssetIds,
    selectionText,
    setSelectionText,
    sendMessage,
    createNote,
    openEvidence,
    clearAssetScope,
    setActiveTab,
  } = useWorkspace();

  const { t } = useTranslation();
  const { user } = useAuth();
  const [mode, setMode] = useState<WorkspaceQuestionMode>("quick");
  const [input, setInput] = useState("");
  const [quickLoading, setQuickLoading] = useState(false);
  const [showNoteEditorId, setShowNoteEditorId] = useState<string | null>(null);
  const [quickNoteTitle, setQuickNoteTitle] = useState("");
  const [quickNoteContent, setQuickNoteContent] = useState("");
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const shouldFollowMessagesRef = useRef(true);
  const activeThreadIdRef = useRef<string | null>(null);

  const workspaceAssets = assets.filter((asset) => asset.workspaceId === currentWorkspace?.id);
  const readyAssetCount = workspaceAssets.filter((asset) => asset.status === "ready").length;
  const assetsReady = readyAssetCount > 0;
  const research = useResearch(currentWorkspace?.id ?? "", selectedAssetIds, user?.userId ?? null);
  const loading = mode === "quick" ? quickLoading : research.loading;
  const canSubmit = canSubmitWorkspaceQuestion({
    mode,
    question: input,
    assetsReady,
    quickThreadReady: Boolean(activeThread),
    busy: loading,
  });

  const handleMessagesScroll = () => {
    const container = messagesContainerRef.current;
    if (container) {
      shouldFollowMessagesRef.current = isNearChatBottom(container);
    }
  };

  useEffect(() => {
    const threadId = activeThread?.id ?? null;
    const switchedThread = activeThreadIdRef.current !== threadId;
    activeThreadIdRef.current = threadId;

    if (switchedThread) {
      shouldFollowMessagesRef.current = true;
    }
    if (!shouldFollowMessagesRef.current) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      const container = messagesContainerRef.current;
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [activeThread?.id, activeThread?.messages]);

  useEffect(() => {
    if (selectionText) {
      composerRef.current?.focus();
    }
  }, [selectionText]);

  const submitMessage = async () => {
    const text = input.trim();
    if (!canSubmit) {
      return;
    }

    setInput("");
    if (mode === "research") {
      await research.start(text);
      composerRef.current?.focus();
      return;
    }

    setQuickLoading(true);
    try {
      await sendMessage(text);
    } finally {
      setQuickLoading(false);
      composerRef.current?.focus();
    }
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    void submitMessage();
  };

  const handleEditMessage = async (messageId: string, content: string) => {
    if (loading) return;
    setQuickLoading(true);
    try {
      await sendMessage(content, { editMessageId: messageId });
    } finally {
      setQuickLoading(false);
    }
  };

  const handleCitationClick = (citation: Citation) => {
    if (!citation.sourceAvailable) {
      return;
    }
    openEvidence(citation);
  };

  const handleInputEvidenceClick = (evidence: InputEvidence) => {
    if (evidence.sourceAvailable) {
      openEvidence(evidence);
    }
  };

  const openQuickNoteEditor = (citation: Citation) => {
    setShowNoteEditorId(citation.id);
    setQuickNoteTitle(
      t("chat.noteTitleTemplate")
        .replace("{doc}", citation.assetTitle)
        .replace("{locator}", getLocatorSummary(citation.locator)),
    );
    setQuickNoteContent(t("chat.noteContentTemplate").replace("{snippet}", citation.excerpt));
  };

  const handleSaveQuickNote = async (citation: Citation) => {
    if (!quickNoteTitle.trim()) return;

    try {
      await createNote(quickNoteTitle, quickNoteContent, {
        source: {
          messageCitationId: citation.id,
          assetId: citation.assetId,
          assetKind: citation.assetKind,
          assetTitle: citation.assetTitle,
          sourceAvailable: citation.sourceAvailable,
          excerpt: citation.excerpt,
          locator: citation.locator,
          sourceVersions: citation.sourceVersions,
        },
      });
      setShowNoteEditorId(null);
      setQuickNoteTitle("");
      setQuickNoteContent("");
      setActiveTab("notes");
    } catch (error) {
      alert(error instanceof Error ? error.message : "Failed to save note.");
    }
  };

  return (
    <div className="flex h-full flex-col bg-card text-foreground">
      <div className="shrink-0 border-b border-border bg-card px-4 py-3 sm:px-8">
        <div className="mx-auto flex w-full max-w-4xl items-center justify-between gap-4">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-zinc-950 dark:text-white sm:text-base">
              {mode === "research" ? t("research.modeResearch") : activeThread ? activeThread.title : t("chat.header")}
            </h2>
            <div className="mt-1 flex items-center gap-1.5 text-[10px] font-medium text-zinc-500 dark:text-zinc-400">
              <Library className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
              <span>{readyAssetCount} {t("workspace.readyAssets")}</span>
              <span aria-hidden="true">·</span>
              <span className="truncate">
                {selectedAssetIds.length > 0
                  ? t("chat.scopeSelected").replace("{count}", String(selectedAssetIds.length))
                  : t("chat.scopeAll")}
              </span>
              {selectedAssetIds.length > 0 ? (
                <button
                  type="button"
                  onClick={clearAssetScope}
                  title={t("chat.clearScope")}
                  aria-label={t("chat.clearScope")}
                  className="flex h-5 w-5 items-center justify-center rounded text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-900 dark:hover:text-white"
                >
                  <X className="h-3 w-3" />
                </button>
              ) : null}
            </div>
          </div>
          <div
            role="tablist"
            aria-label={t("research.modeLabel")}
            className="grid shrink-0 grid-cols-2 rounded-md border border-border bg-background p-0.5"
          >
            <button
              type="button"
              role="tab"
              aria-selected={mode === "quick"}
              onClick={() => setMode("quick")}
              className={`h-7 min-w-16 rounded px-2 text-[11px] font-semibold transition-colors ${mode === "quick" ? "bg-zinc-950 text-white dark:bg-white dark:text-zinc-950" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-950 dark:hover:bg-zinc-900 dark:hover:text-white"}`}
            >
              {t("research.modeQuick")}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "research"}
              onClick={() => setMode("research")}
              className={`h-7 min-w-20 rounded px-2 text-[11px] font-semibold transition-colors ${mode === "research" ? "bg-emerald-700 text-white dark:bg-emerald-500 dark:text-emerald-950" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-950 dark:hover:bg-zinc-900 dark:hover:text-white"}`}
            >
              {t("research.modeResearch")}
            </button>
          </div>
        </div>
      </div>

      <div
        ref={messagesContainerRef}
        data-chat-scroll={mode === "quick" ? "" : undefined}
        onScroll={handleMessagesScroll}
        className="min-h-0 flex-1 overflow-y-auto scroll-smooth px-4 py-6 sm:px-8 sm:py-8"
      >
        <div className="mx-auto w-full max-w-4xl space-y-8">
          {mode === "research" ? (
            <ResearchRunPanel
              key={`${currentWorkspace?.id ?? "none"}:${research.run?.id ?? "none"}:${research.run?.plan?.version ?? 0}`}
              workspaceId={currentWorkspace?.id ?? ""}
              run={research.run}
              runs={research.runs}
              artifacts={research.artifacts}
              artifactContent={research.artifactContent}
              artifactDetail={research.artifactDetail}
              conflictArtifactContent={research.conflictArtifactContent}
              conflictArtifactDetail={research.conflictArtifactDetail}
              canManage={research.canManage}
              loading={research.loading}
              streamState={research.streamState}
              error={research.error}
              onSelectRun={(runId) => { void research.selectRun(runId); }}
              onApprove={() => { void research.approve(); }}
              onRevisePlan={(question, comment) => { void research.revisePlan(question, comment); }}
              onCancelPlan={() => { void research.cancelPlan(); }}
              onResolveConflict={(action) => { void research.resolveConflict(action); }}
              onRetryStep={(step) => { void research.retryStep(step); }}
              onOpenEvidence={openEvidence}
              onCancel={() => { void research.cancel(); }}
            />
          ) : !activeThread || activeThread.messages.length === 0 ? (
            <div className="flex min-h-[45vh] flex-col items-center justify-center text-center text-zinc-400 dark:text-zinc-600">
              <span className="flex h-11 w-11 items-center justify-center rounded-full border border-border bg-background">
                <MessageCircleQuestion className="h-5 w-5" />
              </span>
              <span className="mt-3 text-xs font-semibold text-zinc-500 dark:text-zinc-400">{t("chat.emptyTitle")}</span>
            </div>
          ) : (
            activeThread.messages.map((message) => (
              <ChatBubble
                key={message.id}
                msg={message}
                onCitationClick={handleCitationClick}
                onInputEvidenceClick={handleInputEvidenceClick}
                onQuickNoteOpen={openQuickNoteEditor}
                showNoteEditorId={showNoteEditorId}
                setShowNoteEditorId={setShowNoteEditorId}
                quickNoteTitle={quickNoteTitle}
                setQuickNoteTitle={setQuickNoteTitle}
                quickNoteContent={quickNoteContent}
                setQuickNoteContent={setQuickNoteContent}
                onSaveQuickNote={handleSaveQuickNote}
                onEditMessage={handleEditMessage}
                t={t}
              />
            ))
          )}
        </div>
      </div>

      <div className="shrink-0 border-t border-border bg-card px-3 py-3 sm:px-8 sm:py-4">
        <div className="mx-auto w-full max-w-4xl">
          {mode === "quick" && selectionText ? (
            <div className="mb-2 flex items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-900/70 dark:bg-amber-950/30">
              <div className="min-w-0 flex-1">
                <span className="block text-[9px] font-bold uppercase text-amber-700 dark:text-amber-400">
                  {t("chat.selectionContext")}
                </span>
                <p className="mt-0.5 truncate text-[11px] text-amber-950/70 dark:text-amber-100/70">
                  &quot;{selectionText}&quot;
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectionText(null)}
                title={t("chat.clearSelection")}
                aria-label={t("chat.clearSelection")}
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-amber-700 transition hover:bg-amber-100 dark:text-amber-300 dark:hover:bg-amber-900/60"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : null}

          <form onSubmit={handleSubmit} className="relative flex items-end gap-2 rounded-xl border border-border bg-background p-2 shadow-sm transition focus-within:border-zinc-400 focus-within:shadow-md dark:focus-within:border-zinc-600">
            <textarea
              ref={composerRef}
              rows={1}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submitMessage();
                }
              }}
              disabled={!assetsReady || loading || (mode === "quick" && !activeThread)}
              placeholder={
                !assetsReady
                  ? t("chat.inputPlaceholderNoDocs")
                  : mode === "research"
                    ? t("research.placeholder")
                    : !activeThread
                    ? t("chat.inputPlaceholderEmpty")
                    : t("chat.placeholder")
              }
              aria-label={mode === "research" ? t("research.placeholder") : t("chat.placeholder")}
              className="max-h-32 min-h-9 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-5 text-zinc-900 outline-none placeholder:text-zinc-400 disabled:cursor-not-allowed disabled:text-zinc-400 dark:text-zinc-100 dark:placeholder:text-zinc-600"
            />
            <button
              type="submit"
              disabled={!canSubmit}
              title={mode === "research" ? t("research.start") : t("chat.send")}
              aria-label={mode === "research" ? t("research.start") : t("chat.send")}
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-white transition active:scale-95 disabled:cursor-not-allowed disabled:bg-zinc-200 disabled:text-zinc-400 dark:disabled:bg-zinc-900 dark:disabled:text-zinc-700 ${mode === "research" ? "bg-emerald-700 hover:bg-emerald-600 dark:bg-emerald-500 dark:text-emerald-950 dark:hover:bg-emerald-400" : "bg-zinc-950 hover:bg-zinc-800 dark:bg-white dark:text-zinc-950 dark:hover:bg-zinc-100"}`}
            >
              {mode === "research" ? <Search className="h-4 w-4" /> : <ArrowUp className="h-4 w-4" />}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
