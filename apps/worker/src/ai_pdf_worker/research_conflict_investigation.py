"""Bounded gate orchestration; all external operations have durable replay records."""
from dataclasses import asdict
from uuid import NAMESPACE_URL, uuid5
from citeframe_contracts import DraftClaim, EvidenceHandle, ResearchExecutionError, VerifiedClaim
from citeframe_research_persistence.conflict_contract import validate_investigation


class UnknownOperation(Exception):
    pass


def investigate(*, execution, state, agents, lease, tools, checkpoint):
    conflicts = set(state["conflicts"])
    originals = [c for c in state["verified_claims"] if c.id in conflicts]
    unchanged = [c for c in state["verified_claims"] if c.id not in conflicts and c.verification_status == "supported"]
    claims = [{"id":c.id, "text":c.text, "evidenceHandleIds":list(c.evidence_handle_ids)} for c in originals]
    handles = {e.id:e for b in state["branch_results"] for e in b.evidence}
    required = {h for c in originals for h in c.evidence_handle_ids}
    if not required.issubset(handles) or {c.id for c in originals} != conflicts:
        raise ResearchExecutionError("investigation_original_sources_missing")
    evidence = {h:handles[h] for h in sorted(required)}
    operation = 0
    inspections, gaps, revisions, searches = [], [], [], []
    reason = "round_limit"
    explanation = "The investigation round limit was reached."
    resolved = False

    def perform(phase, request, invoke):
        nonlocal operation
        index = operation
        operation += 1
        stored = checkpoint(lease, index, phase, request)
        if stored["status"] == "succeeded":
            return stored["result"]
        if stored["status"] == "outcome_unknown":
            raise UnknownOperation()
        try:
            result = invoke()
        except Exception as error:
            code = getattr(error, "code", None) or getattr(error, "reason_code", None) or str(error)
            if code in {"research_budget_limit", "research_budget_exceeded"}:
                result = {"stopped":"budget_exhausted"}
            else:
                raise
        checkpoint(lease, index, phase, request, result)
        return result

    def key(e):
        return (e.asset_id, e.representation_id, e.processing_generation, e.index_version, e.parser_version, e.excerpt)

    try:
        for turn in range(3):
            payload = {"claims":claims, "evidence":[asdict(e) for e in evidence.values()],
                "remainingSearches":2-len(searches), "previousInspections":inspections, "gaps":gaps}
            result = perform("inspect", payload, lambda: agents.investigator(payload, lease))
            if result.get("stopped"):
                reason = result["stopped"]; break
            validate_investigation(result, claims=claims, evidence=[asdict(e) for e in evidence.values()])
            inspections, gaps = result["inspections"], result["gaps"]
            explanation = result["reason"]
            revisions = [{**v, "id":str(uuid5(NAMESPACE_URL, f"{lease.step_id}:{turn}:{i}"))}
                         for i,v in enumerate(result["revisions"])]
            if revisions:
                drafts = [DraftClaim(v["id"], v["text"], tuple(v["evidenceHandleIds"])) for v in revisions]
                def verify():
                    rows = list(agents.verifier(drafts, list(evidence.values()), lease))
                    return {"claims":[asdict(c) for c in rows]}
                verified = perform("verify", {"revisions":revisions, "evidence":[asdict(e) for e in evidence.values()]}, verify)
                if verified.get("stopped"):
                    reason=verified["stopped"]; break
                rows = [VerifiedClaim(**v) for v in verified["claims"]]
                by_id = {c.id:c for c in rows}
                if len(rows) != len(drafts) or set(by_id) != {c.id for c in drafts}:
                    raise ResearchExecutionError("investigation_verifier_claim_set_mismatch")
                for draft in drafts:
                    c=by_id[draft.id]
                    if c.text != draft.text or tuple(c.evidence_handle_ids) != draft.evidence_handle_ids or c.verification_status not in {"supported","unsupported"} or c.conflict_status != "none":
                        raise ResearchExecutionError("investigation_verifier_mutated_claim")
                if all(c.verification_status == "supported" for c in rows):
                    check_claims = [*unchanged, *rows]
                    critique = perform("critic", {"claims":[asdict(c) for c in check_claims]},
                        lambda:{"conflictClaimIds":list(agents.critic(check_claims, lease))})
                    if critique.get("stopped"):
                        reason=critique["stopped"]; break
                    ids=critique["conflictClaimIds"]
                    if len(ids)!=len(set(ids)) or not set(ids).issubset({c.id for c in check_claims}):
                        raise ResearchExecutionError("investigation_critic_scope_invalid")
                    if not ids:
                        resolved=True;reason="source_backed_revision";break
                    reason="persistent_contradiction"
                else:
                    reason="revision_unsupported"
            else:
                reason="insufficient_evidence"
            query=result["nextQuery"]
            if query is None:
                break
            normalized=" ".join(query.split()).casefold()
            if normalized in searches:
                reason="duplicate_query";break
            if len(searches)>=2:
                reason="round_limit";break
            searches.append(normalized)
            request={"query":query, "assetIds":[a.asset_id for a in execution.frozen_assets], "topK":execution.retrieval_top_k}
            def search():
                search_tools = tools(len(searches))
                found=search_tools.search(query=query, asset_ids=request["assetIds"], top_k=request["topK"])
                if found:
                    search_tools.load(evidence_handles=tuple(e.id for e in found))
                return {"evidence":[asdict(e) for e in found]}
            found=perform("search", request, search)
            if found.get("stopped"):
                reason=found["stopped"];break
            existing={key(e) for e in evidence.values()}
            fresh=[EvidenceHandle(**v) for v in found["evidence"] if key(EvidenceHandle(**v)) not in existing]
            if not fresh:
                reason="no_new_evidence";break
            evidence.update({e.id:e for e in fresh})
    except UnknownOperation:
        reason="operation_outcome_unknown"
        explanation="A previous attempt stopped before its external operation result was checkpointed; it was not dispatched again."
    outcome={"resolved":resolved, "reason":reason, "explanation":explanation,
        "originalClaims":claims, "inspections":inspections, "queries":searches, "gaps":gaps,
        "revisions":revisions if resolved else [], "evidence":[asdict(e) for e in evidence.values()]}
    if not resolved and not gaps:
        outcome["gaps"]=["The cited sources do not establish a verified, mutually consistent correction; do not treat this result as a complete operating checklist."]
    # The final record is persisted before the existing atomic gate completion.
    saved=checkpoint(lease, operation, "finish", {"conflictClaimIds":sorted(conflicts)})
    if saved["status"] == "succeeded":
        if saved["result"] != outcome:
            raise ResearchExecutionError("investigation_terminal_replay_changed")
    else:
        checkpoint(lease, operation, "finish", {"conflictClaimIds":sorted(conflicts)}, outcome)
    return outcome
