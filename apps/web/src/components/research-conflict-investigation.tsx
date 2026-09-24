"use client";

import { useState } from "react";
import type { ConflictInvestigation } from "@/lib/research/types";
import { useTranslation } from "@/lib/i18n-context";

const labels = {
  zh: { title: "冲突调查", running: "调查中", resolved: "已解决", unresolved: "仍未解决", cancelled: "已取消", failed: "调查失败", original: "原始结论", revisions: "核验后的修正", sources: "来源与条件", queries: "已补查", gaps: "重要缺口", unknown: "未知", warning: "存在关键缺口，不能将结果当作完整操作清单。", version: "版本", environment: "环境", time: "时间", conditions: "适用条件", lineage: "原始结论 ID" },
  en: { title: "Conflict investigation", running: "Investigating", resolved: "Resolved", unresolved: "Unresolved", cancelled: "Cancelled", failed: "Investigation failed", original: "Original claims", revisions: "Verified corrections", sources: "Sources and conditions", queries: "Queries checked", gaps: "Important gaps", unknown: "Unknown", warning: "Important gaps prevent using this result as a complete operating checklist.", version: "Version", environment: "Environment", time: "Time", conditions: "Conditions", lineage: "Original claim IDs" },
};

export function ResearchConflictInvestigation({ investigation }: { investigation: ConflictInvestigation | null | undefined }) {
  const { locale } = useTranslation();
  const copy = labels[locale];
  const [sourcesOpen, setSourcesOpen] = useState(false);
  if (!investigation) return null;
  return (
    <section className="border-t border-border py-5" aria-label={copy.title}>
      <h4 className="text-xs font-semibold">{copy.title} · {copy[investigation.status]}</h4>
      {investigation.explanation ? <p className="mt-2 text-xs">{investigation.explanation}</p> : null}
      {investigation.reason ? <code className="text-xs text-zinc-500">{investigation.reason}</code> : null}
      <details className="mt-3 text-xs">
        <summary>{copy.original}</summary>
        <ul className="mt-2 space-y-2">{investigation.originalClaims.map(claim => <li key={claim.id} id={`conflict-${claim.id}`}>{claim.text}<span className="block font-mono text-zinc-500">{claim.id}</span></li>)}</ul>
      </details>
      {investigation.revisions.length ? <div className="mt-3 text-xs">
        <h5 className="font-medium">{copy.revisions}</h5>
        <ul className="mt-2 space-y-2">{investigation.revisions.map(claim => <li key={claim.id}>
          <p>{claim.text}</p><p className="text-zinc-500">{copy.lineage}: {claim.originalClaimIds.join(", ")}</p>
          <p>{claim.evidenceHandleIds.map(id => <a className="mr-2 underline" key={id} onClick={() => setSourcesOpen(true)} href={`#investigation-source-${id}`}>{id}</a>)}</p>
        </li>)}</ul>
      </div> : null}
      <details className="mt-3 text-xs" open={sourcesOpen} onToggle={event => setSourcesOpen(event.currentTarget.open)}>
        <summary>{copy.sources}</summary>
        <ul className="mt-2 space-y-3">{investigation.sources.map(source => {
          const conditions = investigation.inspections.find(item => item.evidenceHandleId === source.id);
          return <li key={source.id} id={`investigation-source-${source.id}`}>
            <p className="break-all font-mono">{source.assetId} / {source.locatorId}</p>
            <blockquote className="my-1 border-l-2 border-border pl-2">{source.excerpt}</blockquote>
            <dl>{(["version", "environment", "time", "conditions"] as const).map(key => <div key={key}><dt className="inline font-medium">{copy[key]}: </dt><dd className="inline">{conditions?.[key] ?? copy.unknown}</dd></div>)}</dl>
          </li>;
        })}</ul>
      </details>
      {investigation.queries.length ? <details className="mt-3 text-xs"><summary>{copy.queries}</summary><ul>{investigation.queries.map((q, i) => <li key={i}>{q}</li>)}</ul></details> : null}
      {investigation.gaps.length ? <div className="mt-3 text-xs text-amber-800 dark:text-amber-200"><h5 className="font-medium">{copy.gaps}</h5><ul className="list-disc pl-4">{investigation.gaps.map((gap, i) => <li key={i}>{gap}</li>)}</ul><p className="mt-2">{copy.warning}</p></div> : null}
    </section>
  );
}
