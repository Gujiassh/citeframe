"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getReportEdit, putReportEdit, ReportEditError, type ReportEdit } from "@/lib/research/report-edit-client";
import { ResearchReportMarkdown } from "./research-report-markdown";

type Props = {
  workspaceId: string;
  runId: string;
  originalArtifactId: string;
  originalSha256: string;
  originalMarkdown: string;
  canEdit: boolean;
  completed: boolean;
};

const articleClass = "mt-3 max-w-none text-sm leading-6 text-zinc-700 [&_a]:text-emerald-700 [&_a]:underline [&_h1]:mb-3 [&_h1]:mt-6 [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:mb-2 [&_h2]:mt-5 [&_h2]:text-base [&_h2]:font-semibold [&_li]:my-1 [&_ol]:my-3 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-3 [&_strong]:font-semibold [&_strong]:text-zinc-950 [&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-5 dark:text-zinc-200 dark:[&_a]:text-emerald-400 dark:[&_strong]:text-white";

export function ResearchReportEditor({ workspaceId, runId, originalArtifactId, originalSha256, originalMarkdown, canEdit, completed }: Props) {
  const [selected, setSelected] = useState<"original" | "edited">("original");
  const [saved, setSaved] = useState<ReportEdit | null>(null);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState<"loading" | "saving" | null>(completed ? "loading" : null);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const epoch = useRef(0);
  const pending = useRef<AbortController | null>(null);

  const validate = useCallback((edit: ReportEdit) => {
    if (edit.originalArtifactId !== originalArtifactId || edit.originalSha256 !== originalSha256) {
      throw new Error("The original report changed. Reload the research run.");
    }
    return edit;
  }, [originalArtifactId, originalSha256]);

  const load = useCallback((keepDraft: boolean) => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    const request = ++epoch.current;
    return getReportEdit(workspaceId, runId, controller.signal)
      .then(validate)
      .then((edit) => {
        if (request !== epoch.current || controller.signal.aborted) return;
        setSaved(edit);
        if (!keepDraft) {
          setDraft(edit.markdown ?? originalMarkdown);
          setConflict(false);
          setEditing(false);
        }
      })
      .catch((cause: unknown) => {
        if (request !== epoch.current || controller.signal.aborted) return;
        setError(cause instanceof Error ? cause.message : "Unable to load the report edit.");
      })
      .finally(() => {
        if (request === epoch.current && !controller.signal.aborted) setBusy(null);
      });
  }, [workspaceId, runId, originalMarkdown, validate]);

  useEffect(() => {
    if (completed) void load(false);
    return () => {
      epoch.current += 1;
      pending.current?.abort();
    };
  }, [completed, load]);

  const reload = (keepDraft: boolean) => {
    setBusy("loading");
    setError(null);
    return load(keepDraft);
  };

  const save = async () => {
    if (!saved || !editing || conflict || busy) return;
    if (!draft.trim() || draft.length > 200_000 || new TextEncoder().encode(draft).length > 1_000_000) {
      setError("Report text must be non-empty and at most 1 MB.");
      return;
    }
    const controller = new AbortController();
    pending.current = controller;
    const request = ++epoch.current;
    setBusy("saving");
    setError(null);
    try {
      const edit = validate(await putReportEdit(workspaceId, runId, saved.version, draft, { originalArtifactId, originalSha256 }, controller.signal));
      if (request !== epoch.current || controller.signal.aborted) return;
      setSaved(edit);
      setEditing(false);
    } catch (cause) {
      if (request !== epoch.current || controller.signal.aborted) return;
      if (cause instanceof ReportEditError && cause.status === 409 && cause.code === "report_edit_version_conflict") {
        setConflict(true);
        void reload(true);
      } else {
        setError(cause instanceof Error ? cause.message : "Unable to save the report edit.");
      }
    } finally {
      if (request === epoch.current && !controller.signal.aborted) setBusy(null);
    }
  };

  const startEdit = () => {
    if (!saved || !canEdit || busy || error) return;
    setDraft(saved.markdown ?? originalMarkdown);
    setSelected("edited");
    setEditing(true);
  };

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <div role="tablist" aria-label="Report versions" className="flex gap-1">
          <button type="button" role="tab" aria-selected={selected === "original"} onClick={() => setSelected("original")} className="rounded-md border border-border px-3 py-1.5 text-xs aria-selected:bg-zinc-100 dark:aria-selected:bg-zinc-800">Original</button>
          <button type="button" role="tab" aria-selected={selected === "edited"} onClick={() => setSelected("edited")} disabled={!saved} className="rounded-md border border-border px-3 py-1.5 text-xs disabled:opacity-40 aria-selected:bg-zinc-100 dark:aria-selected:bg-zinc-800">User-edited</button>
        </div>
        {selected === "edited" ? <span className="text-[10px] font-semibold uppercase text-amber-700 dark:text-amber-400">Unverified</span> : null}
        {canEdit && completed && saved && !editing && !busy && !error ? <button type="button" onClick={startEdit} className="ml-auto rounded-md border border-border px-3 py-1.5 text-xs font-semibold">Edit</button> : null}
      </div>

      {busy === "loading" ? <p role="status" className="mt-3 text-xs text-zinc-500">Loading saved report…</p> : null}
      {busy === "saving" ? <p role="status" className="mt-3 text-xs text-zinc-500">Saving…</p> : null}
      {error ? <div className="mt-3 flex items-center gap-2 text-xs"><p role="alert" className="text-red-600">{error}</p><button type="button" onClick={() => void reload(editing)} className="rounded-md border border-border px-2 py-1">Retry</button></div> : null}
      {conflict ? <div className="mt-3 flex flex-wrap items-center gap-2 text-xs"><p role="alert" className="text-amber-700">Another tab saved a newer version. Your draft is preserved.</p><button type="button" disabled={!saved || !!busy || !!error} onClick={() => setConflict(false)} className="rounded-md border border-border px-2 py-1 disabled:opacity-40">Use my draft with latest version</button><button type="button" disabled={!saved || !!busy || !!error} onClick={() => { setDraft(saved!.markdown ?? originalMarkdown); setConflict(false); setEditing(false); }} className="rounded-md border border-border px-2 py-1 disabled:opacity-40">Discard draft</button></div> : null}

      {editing && selected === "edited" ? (
        <div className="mt-3">
          <label className="block text-xs font-semibold" htmlFor="research-report-markdown">Markdown</label>
          <textarea id="research-report-markdown" aria-label="Report Markdown" value={draft} onChange={(event) => setDraft(event.target.value)} disabled={!!busy} rows={18} className="mt-2 w-full resize-y rounded-md border border-border bg-background p-3 font-mono text-xs leading-5 disabled:opacity-50" />
          <div className="mt-2 flex justify-end gap-2">
            <button type="button" disabled={!!busy} onClick={() => { setDraft(saved?.markdown ?? originalMarkdown); setEditing(false); setConflict(false); setError(null); }} className="rounded-md border border-border px-3 py-1.5 text-xs">Cancel</button>
            <button type="button" disabled={!!busy || conflict || !draft.trim() || draft.length > 200_000} onClick={() => void save()} className="rounded-md bg-zinc-950 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40 dark:bg-white dark:text-zinc-950">Save</button>
          </div>
        </div>
      ) : selected === "edited" && saved?.markdown ? (
        <article className={articleClass}><ResearchReportMarkdown content={saved.markdown} /></article>
      ) : selected === "edited" ? <p className="mt-3 text-xs text-zinc-500">No user edit saved.</p> : (
        <article className={articleClass}><ResearchReportMarkdown content={originalMarkdown} /></article>
      )}
    </div>
  );
}
