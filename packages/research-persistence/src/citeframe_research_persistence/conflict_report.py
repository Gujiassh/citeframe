"""Render verified investigation revisions without mutating historical claims."""
from .conflict_investigation import investigation_outcome
from .publication_render import canonical_final_report


def investigation_report(db, run_id, *, fact_claims, unresolved_claims):
    outcome = investigation_outcome(db, run_id)
    if outcome is None:
        return canonical_final_report(fact_claims=fact_claims, unresolved_claims=unresolved_claims)
    def clean(text):
        return str(text).replace("<!--", "&lt;!--").replace("-->", "--&gt;").replace("\r", "").replace("\n", " ")
    original_ids = {c["id"] for c in outcome["originalClaims"]}
    unresolved = [c for c in unresolved_claims if not outcome["resolved"] or c.id not in original_ids]
    text = canonical_final_report(fact_claims=fact_claims, unresolved_claims=unresolved).decode()
    lines = [text.rstrip(), "", "## Conflict investigation", "",
        "Status: " + ("resolved" if outcome["resolved"] else "unresolved"),
        "Stop reason: " + clean(outcome["reason"]), clean(outcome["explanation"])]
    for revision in outcome["revisions"]:
        lines += ["", "- " + clean(revision["text"]), "  Original claims: " + ", ".join(revision["originalClaimIds"]),
            "  Evidence: " + ", ".join(revision["evidenceHandleIds"])]
    lines += ["", "### Sources inspected"]
    for source in outcome["evidence"]:
        lines += ["- " + clean(source["asset_id"]) + " (" + source["id"] + "; locator " + source["locator_id"] + ")",
            "  " + clean(source["excerpt"])]
    for item in outcome["inspections"]:
        lines += ["- " + item["evidenceHandleId"] + ": " + "; ".join(k + "=" + clean(item[k] if item[k] is not None else "unknown") for k in ("version", "environment", "time", "conditions"))]
    if outcome["queries"]:
        lines += ["", "### Queries checked", *["- " + clean(q) for q in outcome["queries"]]]
    if outcome["gaps"]:
        lines += ["", "### Important gaps", *["- " + clean(g) for g in outcome["gaps"]],
            "", "These gaps prevent treating this result as a complete operating checklist."]
    return ("\n".join(lines) + "\n").encode()
