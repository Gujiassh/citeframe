"use client";
import { useState } from "react";
import { useTranslation } from "@/lib/i18n-context";
import { memoryAdmissionEnabled } from "@/lib/memory/activation";
import { kinds, type Kind, type Statement } from "@/lib/memory/types";
export const control = "w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-xs dark:border-zinc-800 dark:bg-zinc-950";
export const button = "rounded-lg border border-zinc-200 px-3 py-2 text-xs font-semibold disabled:opacity-50 dark:border-zinc-800";
export function MemoryForm({ value, onChange, busy, conflict, onSubmit, onCancel }: { value?: Statement; onChange?: (value: Statement) => void; busy: boolean; conflict: boolean; onSubmit: (value: Statement) => void; onCancel: () => void }) {
  const { t } = useTranslation();
  const [local, setLocal] = useState<Statement>({ kind: "preference", content: "", conditions: { subject: "", applicability: "", effectiveFrom: null }, pinned: false, validUntil: null });
  const draft = value ?? local;
  const update = (next: Statement) => { if (onChange) onChange(next); else setLocal(next); };
  const valid = [[draft.conditions.subject, 256], [draft.conditions.applicability, 2000], [draft.content, 4000]].every(([text, max]) => [...String(text)].length > 0 && [...String(text)].length <= Number(max));
  return <form className="space-y-4 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800" onSubmit={event => {
    event.preventDefault();
    if (!busy && !conflict && valid && memoryAdmissionEnabled) onSubmit(draft);
  }}>
    <h4 className="text-sm font-semibold">{t(value ? "memory.correct" : "memory.create")}</h4>
    <fieldset disabled={busy} className="space-y-3">
      <label className="block space-y-1 text-xs"><span>{t("memory.kind")}</span><select className={control} value={draft.kind} onChange={e => update({ ...draft, kind: e.target.value as Kind })}>{kinds.map(k => <option key={k} value={k} disabled={draft.pinned && k !== "constraint" && k !== "decision"}>{t(`memory.${k}`)}</option>)}</select></label>
      <label className="block space-y-1 text-xs"><span>{t("memory.subject")} (1–256)</span><input required className={control} value={draft.conditions.subject} onChange={e => update({ ...draft, conditions: { ...draft.conditions, subject: e.target.value } })} /></label>
      <label className="block space-y-1 text-xs"><span>{t("memory.applicability")} (1–2000)</span><textarea required className={control} rows={3} value={draft.conditions.applicability} onChange={e => update({ ...draft, conditions: { ...draft.conditions, applicability: e.target.value } })} /></label>
      <label className="block space-y-1 text-xs"><span>{t("memory.content")} (1–4000)</span><textarea required className={control} rows={5} value={draft.content} onChange={e => update({ ...draft, content: e.target.value })} /></label>
      {value && <StatementOptions value={draft} />}
      <p className="text-xs text-zinc-500">{t("memory.characterBounds")}</p>
    </fieldset>
    {!memoryAdmissionEnabled && <p className="text-xs text-zinc-500">{t("memory.admissionPending")}</p>}
    <div className="flex gap-2"><button className={button} disabled={busy || conflict || !valid || !memoryAdmissionEnabled}>{t("memory.save")}</button><button type="button" className={button} disabled={busy} onClick={onCancel}>{t("memory.cancel")}</button></div>
  </form>;
}
export function StatementOptions({ value }: { value: Statement }) {
  const { t } = useTranslation();
  return <dl className="space-y-1 text-xs"><div><dt>{t("memory.effectiveFrom")}</dt><dd>{value.conditions.effectiveFrom ?? "null"}</dd></div><div><dt>{t("memory.pinned")}</dt><dd>{String(value.pinned)}</dd></div><div><dt>{t("memory.validUntil")}</dt><dd>{value.validUntil ?? "null"}</dd></div></dl>;
}
