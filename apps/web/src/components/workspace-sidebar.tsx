"use client";

import React, { useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useAuth } from "@/lib/auth/auth-context";
import { useWorkspace, Asset } from "@/lib/workspace-context";
import { useTheme } from "@/lib/theme-context";
import { useTranslation } from "@/lib/i18n-context";
import { PRODUCTION_UPLOAD_ACCEPT } from "@/lib/assets/production-upload";
import { 
  Plus, Trash2, MessageSquare, 
  Tag as TagIcon, ChevronDown, UploadCloud, X, ChevronLeft, ChevronRight,
  Sun, Moon, Globe, LogOut, Home, RotateCcw
} from "lucide-react";
import { CreateWorkspaceDialog } from "./create-workspace-dialog";
export function WorkspaceSidebar() {
  const {
    workspaces,
    currentWorkspace,
    assets,
    threads,
    activeThread,
    tags,
    activeAssetId,
    leftSidebarOpen,
    selectedAssetIds,
    selectedTagIds,
    switchWorkspace,
    createWorkspace,
    uploadAsset,
    deleteAsset,
    retryAsset,
    retryDeleteAsset,
    openAsset,
    createThread,
    switchThread,
    deleteThread,
    addTag,
    deleteTag,
    toggleAssetTag,
    toggleAssetScope,
    setActiveTab,
    setLeftSidebarOpen,
    setSelectedTagIds,
  } = useWorkspace();

  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { locale, setLocale, t } = useTranslation();

  const [showWsMenu, setShowWsMenu] = useState(false);
  const [showCreateWs, setShowCreateWs] = useState(false);
  const [newTagName, setNewTagName] = useState("");
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const wsAssets = assets.filter((asset) => asset.workspaceId === currentWorkspace?.id);
  const wsThreads = threads.filter((t) => t.workspaceId === currentWorkspace?.id);
  const wsTags = tags.filter((t) => t.workspaceId === currentWorkspace?.id);
  
  const isAnyAssetProcessing = wsAssets.some(
    (asset) => !["ready", "chunked", "failed", "deleted"].includes(asset.status),
  );

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      try {
        await uploadAsset(file);
      } catch (error) {
        alert(error instanceof Error ? error.message : "Upload failed.");
      } finally {
        e.target.value = "";
      }
    }
  };

  const triggerUpload = () => {
    fileInputRef.current?.click();
  };

  const handleCreateThread = () => {
    setActiveTab("chat");
    void createThread();
  };

  const handleSwitchThread = (threadId: string) => {
    setActiveTab("chat");
    switchThread(threadId);
  };



  const handleAddTag = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTagName.trim()) return;
    try {
      await addTag(newTagName.trim());
      setNewTagName("");
    } catch (error) {
      alert(error instanceof Error ? error.message : "Failed to create tag.");
    }
  };

  const toggleTagFilter = (tagId: string) => {
    setSelectedTagIds((prev) =>
      prev.includes(tagId) ? prev.filter((id) => id !== tagId) : [...prev, tagId]
    );
  };

  const getStatusLabel = (asset: Asset) => {
    switch (asset.status) {
      case "pending_upload": return `${t("sidebar.statusPendingUpload")} (${asset.progress}%)`;
      case "uploaded": return `${t("sidebar.statusUploaded")} (${asset.progress}%)`;
      case "parsing": return `${t("sidebar.statusParsing")} (${asset.progress}%)`;
      case "chunking": return `${t("sidebar.statusChunking")} (${asset.progress}%)`;
      case "chunked": return t("sidebar.statusChunked");
      case "embedding": return `${t("sidebar.statusEmbedding")} (${asset.progress}%)`;
      case "ready": return t("sidebar.statusReady");
      case "deleting": return t("sidebar.statusDeleting");
      default: return t("sidebar.statusFailed");
    }
  };

  // 1. COLLAPSED SIDEBAR (Slim Rail)
  if (!leftSidebarOpen) {
    return (
      <div className="flex h-full w-16 flex-col items-center justify-between border-r border-border bg-background py-4 shrink-0 transition-all duration-300 hidden md:flex">
        <div className="flex flex-col items-center gap-6 w-full">
          {/* Expand Toggle */}
          <button
            onClick={() => setLeftSidebarOpen(true)}
            className="flex h-9 w-9 items-center justify-center rounded-xl bg-card text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 transition active:scale-95 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white"
            title={t("sidebar.expandTooltip")}
          >
            <ChevronRight className="h-4.5 w-4.5" />
          </button>

          <div className="h-px w-8 bg-border" />

          {/* Current Workspace Icon Indicator */}
          <button
            onClick={() => setLeftSidebarOpen(true)}
            className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-600 text-white font-extrabold text-sm shadow-md hover:bg-emerald-500 transition active:scale-95"
            title={currentWorkspace?.name}
          >
            {currentWorkspace?.name.slice(0, 1)}
          </button>

          {/* Quick upload icon */}
          <button
            onClick={triggerUpload}
            className="group relative flex h-9 w-9 items-center justify-center rounded-xl bg-card text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 transition active:scale-95 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white"
            title={t("sidebar.uploadTooltip")}
          >
            <UploadCloud className="h-4 w-4" />
            {isAnyAssetProcessing && (
              <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-cyan-400 animate-ping" />
            )}
          </button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept={PRODUCTION_UPLOAD_ACCEPT}
            className="hidden"
          />

          {/* Quick Thread Icon */}
          <button
            onClick={handleCreateThread}
            className="flex h-9 w-9 items-center justify-center rounded-xl bg-card text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 transition active:scale-95 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white"
            title={t("sidebar.newThread")}
          >
            <MessageSquare className="h-4 w-4" />
          </button>
        </div>

        {/* Bottom controls */}
        <div className="flex flex-col items-center gap-4">
          <button
            onClick={toggleTheme}
            aria-label={t("sidebar.themeTooltip")}
            className="rounded-lg p-1.5 text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-900 dark:hover:text-white"
            title={t("sidebar.themeTooltip")}
          >
            {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
          </button>
          <button
            onClick={logout}
            className="p-1.5 rounded-lg text-zinc-500 hover:text-rose-500 transition"
            title={t("sidebar.logout")}
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    );
  }

  // 2. EXPANDED SIDEBAR (Full Width)
  return (
    <div className="absolute inset-y-0 left-0 z-40 flex h-screen w-72 shrink-0 flex-col border-r border-border bg-background text-foreground shadow-2xl transition-all duration-300 lg:relative lg:z-auto lg:shadow-none">
      
      {/* Expanded Header */}
      <div className="relative flex items-center justify-between gap-2.5 border-b border-border p-4">
        {/* Home icon button - Return to Home */}
        <Link
          href="/"
          className="flex shrink-0 cursor-pointer items-center justify-center rounded-lg border border-border p-1.5 text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-900 dark:hover:text-white"
          title={t("sidebar.homeTooltip")}
        >
          <Home className="h-4 w-4" />
        </Link>

        <button
          onClick={() => setShowWsMenu(!showWsMenu)}
          className="flex flex-1 items-center justify-between rounded-xl border border-border bg-card px-3 py-2 text-left shadow-sm transition hover:border-zinc-300 hover:bg-zinc-100 active:scale-[0.98] dark:hover:border-zinc-700 dark:hover:bg-zinc-900"
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-white font-extrabold text-sm shadow-md">
              {currentWorkspace?.name.slice(0, 1)}
            </div>
            <div className="min-w-0">
              <div className="truncate text-xs font-bold text-zinc-900 dark:text-white">{currentWorkspace?.name}</div>
              <div className="text-[10px] font-semibold text-zinc-500">{t("dashboard.role")}: {currentWorkspace?.role}</div>
            </div>
          </div>
          <ChevronDown className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
        </button>

        {/* Collapse Sidebar Button */}
        <button
          onClick={() => setLeftSidebarOpen(false)}
          className="shrink-0 rounded-lg border border-border p-1.5 text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-900 dark:hover:text-white"
          title={t("sidebar.collapseTooltip")}
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>

        {showWsMenu && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setShowWsMenu(false)} />
            <div className="absolute left-4 right-4 top-16 z-20 mt-1.5 rounded-2xl border border-border bg-card p-2 text-foreground shadow-2xl animate-in fade-in slide-in-from-top-1 duration-150">
              <div className="max-h-56 overflow-y-auto space-y-0.5">
                {workspaces.map((ws) => (
                  <button
                    key={ws.id}
                    onClick={() => {
                      switchWorkspace(ws.id);
                      setShowWsMenu(false);
                    }}
                    className={`flex w-full items-center justify-between rounded-xl px-2.5 py-2 text-left text-xs transition hover:bg-zinc-100 dark:hover:bg-zinc-800 ${
                      ws.id === currentWorkspace?.id
                        ? "bg-zinc-100 font-semibold text-zinc-900 dark:bg-zinc-800 dark:text-white"
                        : "text-zinc-600 dark:text-zinc-400"
                    }`}
                  >
                    <div className="truncate pr-2">
                      <div className="truncate">{ws.name}</div>
                      <div className="truncate text-[10px] text-zinc-500">{ws.description || t("sidebar.noDesc")}</div>
                    </div>
                    {ws.id === currentWorkspace?.id && (
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shrink-0" />
                    )}
                  </button>
                ))}
              </div>
              
              <div className="mt-2 border-t border-border pt-2">
                <button
                  onClick={() => setShowCreateWs(true)}
                  className="flex w-full items-center justify-center gap-1.5 rounded-xl bg-zinc-900 px-2 py-2 text-xs font-bold text-white transition hover:bg-zinc-700 dark:bg-white dark:text-zinc-950 dark:hover:bg-zinc-200"
                >
                  <Plus className="h-3.5 w-3.5" />
                  {t("dashboard.createBtn")}
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Navigation and Lists */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        
        {/* Assets section (Tab enabled) */}
        <div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">{t("sidebar.assetsHeader")}</span>
            <button
              onClick={triggerUpload}
              className="flex items-center gap-1 rounded-lg border border-border bg-card px-2 py-1 text-[10px] font-bold text-zinc-800 transition hover:bg-zinc-100 active:scale-95 dark:bg-zinc-900 dark:text-white dark:hover:bg-zinc-800"
            >
              <Plus className="h-3 w-3" />
              {t("sidebar.uploadBtn")}
            </button>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept={PRODUCTION_UPLOAD_ACCEPT}
              className="hidden"
            />
          </div>

          <div className="mt-2.5 space-y-1">
            {wsAssets.length === 0 ? (
              <div 
                onClick={triggerUpload}
                className="group flex cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed border-zinc-300 bg-zinc-100/60 p-5 text-center transition hover:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-900/10 dark:hover:border-zinc-700"
              >
                <UploadCloud className="h-6 w-6 text-zinc-600 group-hover:text-zinc-400 transition" />
                <span className="mt-1.5 text-[10px] font-bold text-zinc-500">{t("sidebar.dropzone")}</span>
              </div>
            ) : (
              wsAssets.map((asset) => {
                const isActive = activeAssetId === asset.id;
                
                return (
                  <div
                    key={asset.id}
                    data-asset-id={asset.id}
                    data-asset-status={asset.status}
                    onClick={() => (asset.status === "chunked" || asset.status === "ready") && openAsset(asset.id)}
                    className={`group relative flex cursor-pointer items-center justify-between rounded-xl px-2.5 py-2 transition ${
                      isActive
                        ? "bg-zinc-100 font-semibold text-zinc-900 dark:bg-zinc-900 dark:text-white"
                        : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-900/40 dark:hover:text-zinc-200"
                    }`}
                  >
                    <div className="flex min-w-0 flex-1 items-start gap-2">
                      <input
                        type="checkbox"
                        checked={selectedAssetIds.includes(asset.id)}
                        disabled={asset.status !== "ready"}
                        onClick={(event) => event.stopPropagation()}
                        onChange={() => toggleAssetScope(asset.id)}
                        aria-label={t("sidebar.toggleAssetScope").replace("{asset}", asset.title)}
                        className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-emerald-600 disabled:cursor-not-allowed disabled:opacity-30"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-xs">{asset.sourceFilename}</div>
                        <div className="mt-0.5 flex items-center gap-1.5 text-[9px] text-zinc-500 font-semibold">
                          <span className="uppercase">{asset.kind}</span>
                          <span>•</span>
                          <span>{asset.size}</span>
                          {asset.status !== "ready" && (
                            <>
                              <span>•</span>
                              <span className="text-cyan-400 font-bold">{getStatusLabel(asset)}</span>
                            </>
                          )}
                        </div>
                        {asset.status === "failed" && asset.errorMsg && (
                          <div
                            className="mt-1 line-clamp-2 text-[9px] font-medium leading-3 text-rose-600 dark:text-rose-400"
                            title={asset.errorMsg}
                          >
                            {asset.errorMsg}
                          </div>
                        )}
                        {wsTags.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {wsTags.map((tag) => {
                              const hasTag = asset.tags.includes(tag.name);
                              return (
                                <button
                                  key={tag.id}
                                  type="button"
                                  title={tag.name}
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    void toggleAssetTag(asset.id, tag.name).catch((error) => alert(error instanceof Error ? error.message : "Failed to update asset tags."));
                                  }}
                                  className={`rounded-full px-1.5 py-0.5 text-[8px] font-bold transition ${hasTag ? "text-zinc-950" : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 hover:text-zinc-900 dark:bg-zinc-900 dark:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"}`}
                                  style={{ backgroundColor: hasTag ? tag.color : undefined }}
                                >
                                  {tag.name}
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </div>
                    
                    <div className={`flex shrink-0 items-center gap-1 transition ${
                      (asset.status === "failed" || (asset.status === "deleting" && asset.errorMsg))
                        ? "opacity-100"
                        : "opacity-100 md:opacity-0 md:group-hover:opacity-100"
                    }`}>
                      {(asset.status === "failed" || (asset.status === "deleting" && asset.errorMsg)) && (
                        <button
                          type="button"
                          title={t(asset.status === "failed" ? "sidebar.retryAsset" : "sidebar.retryDeleteAsset")}
                          aria-label={t(asset.status === "failed" ? "sidebar.retryAsset" : "sidebar.retryDeleteAsset")}
                          onClick={(event) => {
                            event.stopPropagation();
                            const retry = asset.status === "failed" ? retryAsset : retryDeleteAsset;
                            void retry(asset.id).catch((error) => {
                              alert(error instanceof Error ? error.message : "Retry failed.");
                            });
                          }}
                          className="flex h-11 w-11 items-center justify-center text-zinc-500 transition hover:text-sky-500 md:h-7 md:w-7"
                        >
                          <RotateCcw className="h-3 w-3" />
                        </button>
                      )}
                      {asset.status !== "deleting" && (
                        <button
                          type="button"
                          title={t("sidebar.deleteAsset")}
                          aria-label={t("sidebar.deleteAsset")}
                          onClick={(event) => {
                            event.stopPropagation();
                            void deleteAsset(asset.id).catch((error) => {
                              alert(error instanceof Error ? error.message : "Delete failed.");
                            });
                          }}
                          className="flex h-11 w-11 items-center justify-center text-zinc-500 transition hover:text-rose-500 md:h-7 md:w-7"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      )}
                    </div>

                    {asset.status !== "ready" && asset.status !== "chunked" && asset.status !== "failed" && (
                      <div className="absolute bottom-0 left-0 right-0 h-0.5 overflow-hidden bg-zinc-200 dark:bg-zinc-900">
                        <div 
                          className="h-full bg-cyan-400 transition-all duration-300"
                          style={{ width: `${asset.progress}%` }}
                        />
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Tags management */}
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">{t("sidebar.tagsHeader")}</span>
          <form onSubmit={handleAddTag} className="mt-2.5 flex gap-1.5">
            <input
              type="text"
              placeholder={t("sidebar.placeholder")}
              value={newTagName}
              onChange={(e) => setNewTagName(e.target.value)}
              className="flex-1 rounded-lg border border-border bg-card px-2.5 py-1 text-xs text-zinc-900 outline-none focus:border-zinc-400 dark:bg-zinc-900 dark:text-white dark:focus:border-zinc-700"
            />
            <button 
              type="submit" 
              className="rounded-lg border border-border bg-card px-2 py-1 text-[10px] font-bold text-zinc-800 transition hover:bg-zinc-100 active:scale-95 dark:bg-zinc-900 dark:text-white dark:hover:bg-zinc-800"
            >
              {t("sidebar.add")}
            </button>
          </form>

          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {wsTags.length === 0 ? (
              <span className="text-[10px] text-zinc-500 dark:text-zinc-600">{t("sidebar.noTags")}</span>
            ) : (
              wsTags.map((tag) => {
                const isSelected = selectedTagIds.includes(tag.id);
                return (
                  <div key={tag.id} className="group/tag flex items-center rounded-full">
                    <button
                      onClick={() => toggleTagFilter(tag.id)}
                      className={`flex items-center gap-0.5 rounded-full px-2.5 py-0.5 text-[9px] font-bold transition ${
                        isSelected
                          ? "font-black text-zinc-950"
                          : "border border-zinc-200 bg-zinc-100 text-zinc-600 hover:border-zinc-300 hover:text-zinc-900 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-500 dark:hover:border-zinc-700 dark:hover:text-zinc-300"
                      }`}
                      style={{ backgroundColor: isSelected ? tag.color : undefined }}
                    >
                      <TagIcon className="h-2 w-2 shrink-0" />
                      {tag.name}
                    </button>
                    <button
                      type="button"
                      title={t("sidebar.deleteTag")}
                      onClick={() => {
                        if (!window.confirm(t("sidebar.confirmDeleteTag"))) return;
                        void deleteTag(tag.id).catch((error) => alert(error instanceof Error ? error.message : "Failed to delete tag."));
                      }}
                      className="-ml-1 hidden rounded-full p-0.5 text-zinc-500 hover:text-rose-400 group-hover/tag:block"
                    >
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Chat History section */}
        <div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">{t("sidebar.threadsHeader")}</span>
            <button
              onClick={handleCreateThread}
              title={t("sidebar.newThread")}
              aria-label={t("sidebar.newThread")}
              className="flex items-center gap-0.5 rounded-lg border border-border bg-card px-1.5 py-0.5 text-[10px] font-bold text-zinc-800 transition hover:bg-zinc-100 active:scale-95 dark:bg-zinc-900 dark:text-white dark:hover:bg-zinc-800"
            >
              <Plus className="h-3 w-3" />
            </button>
          </div>

          <div className="mt-2.5 space-y-0.5">
            {wsThreads.length === 0 ? (
              <span className="text-[10px] text-zinc-600 block">{t("sidebar.noThreads")}</span>
            ) : (
              wsThreads.map((th) => (
                <div
                  key={th.id}
                  onClick={() => handleSwitchThread(th.id)}
                  className={`group flex cursor-pointer items-center justify-between rounded-lg px-2 py-1.5 text-xs transition ${
                    activeThread?.id === th.id
                      ? "bg-zinc-100 font-semibold text-zinc-900 dark:bg-zinc-900 dark:text-white"
                      : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-500 dark:hover:bg-zinc-900/20 dark:hover:text-zinc-300"
                  }`}
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <MessageSquare className="h-3 w-3 text-zinc-600" />
                    <span className="truncate text-xs">{th.title || t("sidebar.newThread")}</span>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteThread(th.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-0.5 hover:text-rose-500 transition"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>

      </div>

      {/* Footer controls with language & theme selector */}
      <div className="flex shrink-0 items-center justify-between border-t border-border bg-background p-3 text-xs">
        <div className="flex items-center gap-2">
          {user && (
            <Image
              src={user.avatarUrl}
              alt={user.name}
              width={28}
              height={28}
              unoptimized
              className="h-7 w-7 rounded-lg border border-border bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-800"
            />
          )}
          <div className="text-left leading-none">
            <div className="max-w-[80px] truncate text-[10px] font-bold text-zinc-900 dark:text-white">{user?.name}</div>
            <div className="text-[9px] text-zinc-500 truncate max-w-[80px] mt-0.5">{user?.email}</div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {/* Language Switch */}
          <button
            onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
            className="flex items-center gap-0.5 rounded-lg p-1 text-[10px] font-bold text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-900 dark:hover:text-white"
            title={locale === "zh" ? "Switch to English" : "切换为中文"}
          >
            <Globe className="h-3.5 w-3.5" />
            {locale === "zh" ? "EN" : "中"}
          </button>

          {/* Theme Switch */}
          <button
            onClick={toggleTheme}
            aria-label={t("sidebar.themeTooltip")}
            className="rounded-lg p-1.5 text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-900 dark:hover:text-white"
            title={t("sidebar.themeTooltip")}
          >
            {theme === "light" ? <Moon className="h-3.5 w-3.5" /> : <Sun className="h-3.5 w-3.5" />}
          </button>

          {/* Logout */}
          <button
            onClick={logout}
            className="rounded-lg p-1 text-zinc-500 transition hover:bg-zinc-100 hover:text-rose-500 dark:hover:bg-zinc-900 dark:hover:text-rose-400"
            title={t("sidebar.logout")}
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* New Workspace modal overlay */}
      <CreateWorkspaceDialog
        show={showCreateWs}
        onClose={() => setShowCreateWs(false)}
        onCreate={async (name, desc) => {
          await createWorkspace(name, desc);
          setShowWsMenu(false);
        }}
        t={t}
      />
    </div>
  );
}
