"use client";

import React, { createContext, useContext, useRef } from "react";

import { useAuth } from "@/lib/auth/auth-context";
import type { ChatThread } from "@/lib/chat/types";
import type {
  EvidenceLocator,
  EvidenceTarget,
  EvidenceTargetRequest,
  SourceVersions,
} from "@/lib/evidence/types";
import type { UploadQueueItem } from "@/lib/assets/upload-queue";
import type { TagDto } from "@/lib/notes/types";

import { useTranslation } from "./i18n-context";
import { useChat } from "./use-chat";
import { useAssets } from "./use-assets";
import { useNotesTags } from "./use-notes-tags";
import { useWorkspaceViewState } from "./workspace-view-state";
import { useWorkspaces } from "./use-workspaces";

export type Workspace = {
  id: string;
  name: string;
  description: string | null;
  role: string;
  systemPrompt: string;
  retrievalTopK: number;
  chunkSize: number;
  embeddingProvider: string;
  embeddingModel: string;
  embeddingDimensions: number;
  embeddingVersion: string;
  generationProvider: string;
  generationModel: string;
  assetCount: number;
  noteCount: number;
  threadCount: number;
  createdAt: string;
  updatedAt: string;
};

export type AssetStatus = "pending_upload" | "uploaded" | "parsing" | "chunking" | "chunked" | "embedding" | "ready" | "failed" | "deleting" | "deleted";

export type Asset = {
  id: string;
  workspaceId: string;
  kind: string;
  title: string;
  sourceFilename: string;
  mimeType: string;
  size: string;
  status: AssetStatus;
  currentProcessingGeneration: number;
  progress: number;
  errorMsg?: string;
  tags: string[];
  createdAt: string;
};

export type { ChatThread, Citation, Message } from "@/lib/chat/types";

export type NoteSource = {
  messageCitationId?: string;
  assetId: string;
  assetKind: string;
  assetTitle: string;
  sourceAvailable: boolean;
  excerpt: string;
  locator: EvidenceLocator;
  sourceVersions: SourceVersions;
};

export type Note = {
  id: string;
  workspaceId: string;
  title: string;
  content: string;
  source?: NoteSource;
  tags: string[];
  createdAt: string;
};

export type Tag = {
  id: string;
  workspaceId: string;
  name: string;
  color: string;
};

type WorkspaceContextType = {
  isHydrating: boolean;
  workspaces: Workspace[];
  currentWorkspace: Workspace | null;
  assets: Asset[];
  notes: Note[];
  threads: ChatThread[];
  activeThread: ChatThread | null;
  tags: Tag[];
  openAssetIds: string[];
  activeAssetId: string | null;
  activeEvidenceLocator: EvidenceLocator | null;
  activeEvidenceSourceVersions: SourceVersions | null;
  activePdfPage: number;
  activeTab: "chat" | "notes" | "settings";
  leftSidebarOpen: boolean;
  evidencePanelOpen: boolean;
  evidencePanelExpanded: boolean;
  selectionText: string | null;
  selectedAssetIds: string[];
  selectedTagIds: string[];
  switchWorkspace: (id: string) => void;
  createWorkspace: (name: string, description: string | null) => Promise<void>;
  deleteWorkspace: (id: string) => Promise<void>;
  updateWorkspaceSettings: (id: string, settings: WorkspaceSettingsInput) => Promise<void>;
  uploadQueue: UploadQueueItem[];
  enqueueUploads: (files: readonly File[]) => void;
  retryUpload: (id: string) => void;
  deleteAsset: (id: string) => Promise<void>;
  retryAsset: (id: string) => Promise<void>;
  retryDeleteAsset: (id: string) => Promise<void>;
  openAsset: (id: string) => void;
  openEvidence: (target: EvidenceTarget) => void;
  closeAsset: (id: string) => void;
  createThread: () => Promise<void>;
  switchThread: (id: string) => void;
  deleteThread: (id: string) => Promise<void>;
  sendMessage: (content: string, options?: SendMessageOptions) => Promise<boolean>;
  createNote: (title: string, content: string, options?: CreateNoteOptions) => Promise<void>;
  submitEvidenceQuestion: (content: string, target: EvidenceTargetRequest) => Promise<boolean>;
  createEvidenceNote: (
    title: string,
    content: string,
    target: EvidenceTargetRequest,
  ) => Promise<void>;
  updateNote: (id: string, title: string, content: string) => Promise<void>;
  deleteNote: (id: string) => Promise<void>;
  addTag: (name: string) => Promise<void>;
  deleteTag: (id: string) => Promise<void>;
  toggleAssetTag: (assetId: string, tagName: string) => Promise<void>;
  toggleNoteTag: (noteId: string, tagName: string) => Promise<void>;
  setActiveAssetId: (id: string | null) => void;
  setActivePdfPage: (page: number) => void;
  setActiveTab: (tab: "chat" | "notes" | "settings") => void;
  setLeftSidebarOpen: (open: boolean) => void;
  setEvidencePanelOpen: (open: boolean) => void;
  setEvidencePanelExpanded: (expanded: boolean) => void;
  closeEvidencePanel: () => void;
  setSelectionText: (text: string | null) => void;
  toggleAssetScope: (assetId: string) => void;
  clearAssetScope: () => void;
  setSelectedTagIds: React.Dispatch<React.SetStateAction<string[]>>;
};

export type SendMessageOptions = {
  editMessageId?: string;
  evidenceTargets?: EvidenceTargetRequest[];
  onRequestAccepted?: () => void;
};

export type CreateNoteOptions = {
  source?: NoteSource;
  evidenceTargets?: EvidenceTargetRequest[];
};

export type WorkspaceSettingsInput = {
  systemPrompt: string;
  retrievalTopK: number;
  chunkSize: number;
};

const WorkspaceContext = createContext<WorkspaceContextType | undefined>(undefined);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const { locale } = useTranslation();
  const { user, isHydrating: isAuthHydrating } = useAuth();
  const viewState = useWorkspaceViewState();
  const assetsRef = useRef<Asset[]>([]);
  const tagRelationsRef = useRef<TagDto[]>([]);
  const syncWorkspaceViewState = viewState.syncWorkspaceViewState;
  const clearWorkspaceViewState = viewState.clearWorkspaceViewState;

  const onWorkspaceSelected = React.useCallback(
    (workspaceId: string) => {
      syncWorkspaceViewState(workspaceId, assetsRef.current);
    },
    [syncWorkspaceViewState],
  );
  const onWorkspaceCleared = React.useCallback(() => {
    clearWorkspaceViewState();
  }, [clearWorkspaceViewState]);

  const workspaceState = useWorkspaces({
    locale,
    user,
    isAuthHydrating,
    currentWorkspaceId: viewState.currentWorkspaceId,
    currentWorkspaceIdRef: viewState.currentWorkspaceIdRef,
    setCurrentWorkspaceId: viewState.setCurrentWorkspaceId,
    onWorkspaceSelected,
    onWorkspaceCleared,
  });

  const assetState = useAssets({
    locale,
    user,
    isAuthHydrating,
    currentWorkspaceId: viewState.currentWorkspaceId,
    tagRelationsRef,
    assetsRef,
    syncAssetViewState: viewState.syncAssetViewState,
    closeAsset: viewState.closeAsset,
    updateWorkspace: workspaceState.updateWorkspace,
  });

  const notesTagsState = useNotesTags({
    user,
    isAuthHydrating,
    currentWorkspaceId: viewState.currentWorkspaceId,
    currentWorkspaceIdRef: viewState.currentWorkspaceIdRef,
    tagRelationsRef,
    assetsRef,
    setSelectedTagIds: viewState.setSelectedTagIds,
    applyAssetTags: assetState.applyTagRelations,
    updateAssetTags: assetState.updateAssetTags,
    removeAssetTagName: assetState.removeTagName,
    updateWorkspace: workspaceState.updateWorkspace,
  });

  const chatState = useChat({
    locale,
    user,
    isAuthHydrating,
    currentWorkspaceId: viewState.currentWorkspaceId,
    currentWorkspaceIdRef: viewState.currentWorkspaceIdRef,
    activeThreadId: viewState.activeThreadId,
    activeThreadIdRef: viewState.activeThreadIdRef,
    selectionText: viewState.selectionText,
    selectedAssetIds: viewState.selectedAssetIds,
    setActiveThreadId: viewState.setActiveThreadId,
    updateWorkspace: workspaceState.updateWorkspace,
  });

  const deleteWorkspaceFromState = workspaceState.deleteWorkspace;
  const removeAssetsWorkspace = assetState.removeWorkspace;
  const removeNotesTagsWorkspace = notesTagsState.removeWorkspace;
  const removeChatWorkspace = chatState.removeWorkspace;
  const sendChatMessage = chatState.sendMessage;
  const createNoteFromState = notesTagsState.createNote;
  const closeEvidencePanelFromState = viewState.closeEvidencePanel;
  const setActiveTabFromState = viewState.setActiveTab;
  const deleteWorkspace = React.useCallback(
    async (id: string) => {
      await deleteWorkspaceFromState(id);
      removeAssetsWorkspace(id);
      removeNotesTagsWorkspace(id);
      removeChatWorkspace(id);
    },
    [deleteWorkspaceFromState, removeChatWorkspace, removeAssetsWorkspace, removeNotesTagsWorkspace],
  );

  const submitEvidenceQuestion = React.useCallback(
    async (content: string, target: EvidenceTargetRequest) => sendChatMessage(content, {
      evidenceTargets: [target],
      onRequestAccepted: () => {
        setActiveTabFromState("chat");
        closeEvidencePanelFromState();
      },
    }),
    [closeEvidencePanelFromState, sendChatMessage, setActiveTabFromState],
  );

  const createEvidenceNote = React.useCallback(
    async (title: string, content: string, target: EvidenceTargetRequest) => {
      await createNoteFromState(title, content, { evidenceTargets: [target] });
      setActiveTabFromState("notes");
      closeEvidencePanelFromState();
    },
    [closeEvidencePanelFromState, createNoteFromState, setActiveTabFromState],
  );

  return (
    <WorkspaceContext.Provider
      value={{
        isHydrating: workspaceState.isHydrating,
        workspaces: workspaceState.workspaces,
        currentWorkspace: workspaceState.currentWorkspace,
        assets: assetState.assets,
        notes: notesTagsState.notes,
        threads: chatState.threads,
        activeThread: chatState.activeThread,
        tags: notesTagsState.tags,
        openAssetIds: viewState.openAssetIds,
        activeAssetId: viewState.activeAssetId,
        activeEvidenceLocator: viewState.activeEvidenceLocator,
        activeEvidenceSourceVersions: viewState.activeEvidenceSourceVersions,
        activePdfPage: viewState.activePdfPage,
        activeTab: viewState.activeTab,
        leftSidebarOpen: viewState.leftSidebarOpen,
        evidencePanelOpen: viewState.evidencePanelOpen,
        evidencePanelExpanded: viewState.evidencePanelExpanded,
        selectionText: viewState.selectionText,
        selectedAssetIds: viewState.selectedAssetIds,
        selectedTagIds: viewState.selectedTagIds,
        switchWorkspace: workspaceState.switchWorkspace,
        createWorkspace: workspaceState.createWorkspace,
        deleteWorkspace,
        updateWorkspaceSettings: workspaceState.updateWorkspaceSettings,
        uploadQueue: assetState.uploadQueue,
        enqueueUploads: assetState.enqueueUploads,
        retryUpload: assetState.retryUpload,
        deleteAsset: assetState.deleteAsset,
        retryAsset: assetState.retryAsset,
        retryDeleteAsset: assetState.retryDeleteAsset,
        openAsset: viewState.openAsset,
        openEvidence: viewState.openEvidence,
        closeAsset: viewState.closeAsset,
        createThread: chatState.createThread,
        switchThread: chatState.switchThread,
        deleteThread: chatState.deleteThread,
        sendMessage: chatState.sendMessage,
        createNote: notesTagsState.createNote,
        submitEvidenceQuestion,
        createEvidenceNote,
        updateNote: notesTagsState.updateNote,
        deleteNote: notesTagsState.deleteNote,
        addTag: notesTagsState.addTag,
        deleteTag: notesTagsState.deleteTag,
        toggleAssetTag: notesTagsState.toggleAssetTag,
        toggleNoteTag: notesTagsState.toggleNoteTag,
        setActiveAssetId: viewState.setActiveAssetId,
        setActivePdfPage: viewState.setActivePdfPage,
        setActiveTab: viewState.setActiveTab,
        setLeftSidebarOpen: viewState.setLeftSidebarOpen,
        setEvidencePanelOpen: viewState.setEvidencePanelOpen,
        setEvidencePanelExpanded: viewState.setEvidencePanelExpanded,
        closeEvidencePanel: viewState.closeEvidencePanel,
        setSelectionText: viewState.setSelectionText,
        toggleAssetScope: viewState.toggleAssetScope,
        clearAssetScope: viewState.clearAssetScope,
        setSelectedTagIds: viewState.setSelectedTagIds,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (context === undefined) {
    throw new Error("useWorkspace must be used within a WorkspaceProvider");
  }
  return context;
}
