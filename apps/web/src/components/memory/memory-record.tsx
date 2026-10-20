import { useTranslation } from "@/lib/i18n-context";
import type { Memory } from "@/lib/memory/types";
export function MemoryRecord({ memory }: { memory: Memory }) {
  const { t } = useTranslation();
  return <div className="space-y-2 break-words text-xs">
    <p className="text-zinc-500">{t(`memory.${memory.displayStatus}`)} · {t("memory.version")} {memory.version}</p>
    {memory.contentAvailable ? <>
      <dl className="space-y-2">
        <div><dt className="text-zinc-500">{t("memory.kind")}</dt><dd>{t(`memory.${memory.kind}`)}</dd></div>
        <div><dt className="text-zinc-500">{t("memory.subject")}</dt><dd className="whitespace-pre-wrap">{memory.conditions.subject}</dd></div>
        <div><dt className="text-zinc-500">{t("memory.applicability")}</dt><dd className="whitespace-pre-wrap">{memory.conditions.applicability}</dd></div>
        <div><dt className="text-zinc-500">{t("memory.content")}</dt><dd className="whitespace-pre-wrap">{memory.content}</dd></div>
      </dl>
      <p className="text-zinc-500">{memory.updatedAt}</p>
    </> : <p>{t(memory.reason === "erased" ? "memory.erased" : "memory.sourceUnavailable")}</p>}
  </div>;
}
