import { useTranslation } from "@/lib/i18n-context";
import type { InstructionSource } from "@/lib/memory/types";
export function MemorySource({ source }: { source: InstructionSource }) {
  const { t } = useTranslation();
  return (
    <section aria-label={t("memory.originalSource")} className="space-y-2 border-t border-zinc-200 pt-4 text-xs dark:border-zinc-800">
      <h5 className="font-semibold">{t("memory.originalSource")} · {t("memory.version")} {source.sourceRef.sourceVersion}</h5>
      <p className="whitespace-pre-wrap break-words">{source.content}</p>
      <dl className="space-y-1 break-all text-zinc-500">
        <div><dt>{t("memory.sourceActor")}</dt><dd>{source.provenance.actorUserId} · {source.provenance.role} · {source.provenance.actorAttribution}</dd></div>
        <div><dt>{t("memory.sourceKind")}</dt><dd>{source.contentKind} · {source.provenance.confirmation}</dd></div>
        <div><dt>{t("memory.sourceRelation")}</dt><dd>{source.branchRelation}</dd></div>
        <div><dt>SHA-256</dt><dd className="font-mono">{source.sourceRef.contentSha256}</dd></div>
      </dl>
      <p className="text-zinc-500">{source.occurredAt}</p>
    </section>
  );
}
