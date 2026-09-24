"""Bounded branch-local retrieval using ledgered generation and evidence ports."""
from __future__ import annotations
from uuid import NAMESPACE_URL, uuid5
import json
from citeframe_contracts import BranchResult, DraftClaim, ResearchExecutionError
from citeframe_research_persistence.autonomy import MAX_SUPPLEMENTAL_SEARCHES
from ai_pdf_worker.research.schemas import validate_adaptive_agent_result, validate_researcher_claim_evidence_scope


def research_adaptively(subproblem, tools, lease, *, top_k, result_schema, generate_json, checkpoint):
    query = subproblem.question
    seen_queries: set[str] = set()
    evidence = {}
    loaded = {}
    evidence_keys: set[tuple] = set()
    claims = {}
    for turn in range(MAX_SUPPLEMENTAL_SEARCHES + 1):
        normalized = " ".join(query.split()).casefold()
        if normalized in seen_queries:
            break
        seen_queries.add(normalized)
        found = tools.search(query=query, asset_ids=subproblem.asset_ids, top_k=top_k)
        fresh = []
        for item in found:
            # Each search clones locators, so snapshot fingerprints change even for identical excerpts.
            content_key = (item.asset_id, item.representation_id, item.processing_generation,
                           item.index_version, item.parser_version, item.excerpt)
            if content_key not in evidence_keys:
                evidence_keys.add(content_key)
                evidence[item.id] = item
                fresh.append(item.id)
        if fresh:
            for item in tools.load(evidence_handles=tuple(fresh)):
                loaded[item.evidence_handle] = item
        elif turn > 0:
            break
        request = {
            "subproblem": {"question": subproblem.question, "assetIds": list(subproblem.asset_ids)},
            "frozenAssetScope": {"assetIds": list(subproblem.asset_ids)},
            "toolContracts": {
                "retrievalQuery": query,
                "allowedTools": ["evidence.search.v1", "evidence.load.v1"],
                "remainingSearches": MAX_SUPPLEMENTAL_SEARCHES - turn,
                "previousQueries": sorted(seen_queries),
                "evidence": [{"evidenceHandle": item.evidence_handle, "content": item.content,
                              "assetId": item.asset_id, "locatorId": item.locator_id,
                              "contentSha256": item.content_sha256} for item in loaded.values()],
            },
            "resultSchema": result_schema,
        }
        payload = checkpoint(lease, turn, request)
        replayed = payload is not None
        if not replayed:
            payload = generate_json(lease, "researcher", request)
        try:
            validate_adaptive_agent_result("researcher", payload)
            validate_researcher_claim_evidence_scope(payload["claims"],
                branch_evidence_handle_ids=list(evidence), allow_empty=True)
        except (KeyError, ValueError, TypeError) as error:
            raise ResearchExecutionError("researcher_invalid_output") from error
        if not replayed:
            checkpoint(lease, turn, request, payload)
        for row in payload["claims"]:
            key = (row["text"].strip(), tuple(sorted(row["evidenceHandleIds"])))
            if key not in claims:
                claims[key] = DraftClaim(str(uuid5(NAMESPACE_URL, json.dumps([lease.step_id, key], ensure_ascii=False))), row["text"], tuple(row["evidenceHandleIds"]))
        query = payload["nextQuery"]
        if query is None:
            break
    return BranchResult(subproblem.branch_key, tuple(claims.values()), tuple(evidence.values()))
