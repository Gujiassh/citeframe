from __future__ import annotations

from collections.abc import Sequence

from citeframe_persistence.models import ResearchClaim


def canonical_final_report(
    *,
    fact_claims: Sequence[ResearchClaim],
    unresolved_claims: Sequence[ResearchClaim],
) -> bytes:
    """Render the frozen v1 final-report bytes."""

    def append_claim(lines: list[str], claim: ResearchClaim, section: str) -> None:
        statement = (
            claim.statement_text.replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("<!--", "&lt;!--")
            .replace("-->", "--&gt;")
            .strip()
        )
        rendered = statement.replace("\n", "\n  ")
        lines.extend(
            (
                f"<!-- citeframe:claim id={claim.id} section={section} -->",
                f"- {rendered}",
            )
        )

    lines = ["# Citeframe Research Report", "", "## Findings"]
    if fact_claims:
        for claim in fact_claims:
            append_claim(lines, claim, "fact")
    else:
        lines.append("- No supported findings.")
    if unresolved_claims:
        lines.extend(("", "## Unresolved Evidence Conflicts"))
        for claim in unresolved_claims:
            append_claim(lines, claim, "unresolved")
    return ("\n".join(lines) + "\n").encode("utf-8")
