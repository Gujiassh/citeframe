from __future__ import annotations

import re
from typing import Any

from ai_pdf_worker.r803_evaluation_contract import (
    CaseExecution,
    EvaluationPackage,
    R803EvaluationError,
    _ratio,
    aggregate_ratio,
)
from ai_pdf_worker.r803_evaluation_diagnostics import (
    DiagnosticCapture,
    OutputFailureDiagnostic,
    RawOutputRecord,
    classify_failure_origin,
    with_failure_origin,
)

SCORER_VERSION = "r100-v2"


def _concepts_match(output: str, required: list[list[str]]) -> bool:
    lowered = output.casefold()
    return all(any(term.casefold() in lowered for term in group) for group in required)


def _matches_any(text: str, patterns: list[str] | None) -> bool:
    if not patterns:
        return False
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _classify_concept_match(text: str, expected_claim: dict[str, Any]) -> str:
    """Disjoint category for one concept-matched observed claim.

    Precedence is intentional and exclusive:
    1. claim-local negationPatterns -> negated
    2. else claim-local forbiddenPatterns -> forbidden
    3. else valid positive assertion (or no positiveAssertionPatterns required) -> positive
    4. else unmatched (concept-only noise under this expected claim)
    """
    if _matches_any(text, expected_claim.get("negationPatterns")):
        return "negated"
    if _matches_any(text, expected_claim.get("forbiddenPatterns")):
        return "forbidden"
    positive_patterns = expected_claim.get("positiveAssertionPatterns")
    if not positive_patterns or _matches_any(text, positive_patterns):
        return "positive"
    return "unmatched"


def _unavailable(reason: str) -> dict[str, object]:
    return _ratio(None, 0, reason)


def _public_claim_rows(claim_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """R700-compatible claim rows: only expected claim keys, no synthetic extras."""
    return [
        row
        for row in claim_rows
        if not str(row.get("claimKey", "")).startswith("extra-claim-")
        and not str(row.get("claimKey", "")).startswith("unmatched-claim-")
    ]


def score_case_v2(
    case: dict[str, Any],
    execution: CaseExecution,
    *,
    diagnostic: OutputFailureDiagnostic | None = None,
) -> dict[str, Any]:
    base = {
        "caseKey": case["id"],
        "caseType": case["caseType"],
        "expectedDisposition": case["expectedDisposition"],
        "observedDisposition": execution.observed_disposition,
        "wallTimeMs": execution.wall_time_ms,
        "providerCalls": execution.provider_calls,
        "cost": {"currency": "USD", "amountMicros": 0},
        "humanInterventionCount": 0,
        "humanWaitMs": 0,
        "claims": [],
        "scorerVersion": SCORER_VERSION,
        "diagnostic": None
        if diagnostic is None
        else {
            "stage": diagnostic.stage,
            "rule": diagnostic.rule,
            "path": diagnostic.path,
            "nodeKey": diagnostic.node_key,
            "logicalCallKey": diagnostic.logical_call_key,
            "rawOutputSha256": diagnostic.raw_output_sha256,
            "failureCode": diagnostic.failure_code,
            "failureOrigin": classify_failure_origin(diagnostic.failure_code),
        },
        "extraClaimCount": 0,
        "negatedClaimCount": 0,
        "forbiddenAnswerCount": 0,
        "qualityFailure": False,
        "engineeringFailure": False,
    }

    if execution.failure_code is not None:
        origin = classify_failure_origin(execution.failure_code)
        # Explicit provenance only: model/workflow semantic failures stay in quality
        # denominators; provider/evaluator integrity failures are engineering and make
        # model quality not_evaluable at campaign gates.
        model_quality_failure = origin == "model_or_workflow_quality"
        engineering_failure = not model_quality_failure
        reason = (
            "model_or_workflow_quality_failure"
            if model_quality_failure
            else "engineering_or_integrity_failure"
        )
        failed_metric = _ratio(0.0, 1) if model_quality_failure else _unavailable(reason)
        claim_rows: list[dict[str, object]] = []
        if model_quality_failure and case["claims"]:
            for expected_claim in case["claims"]:
                claim_rows.append(
                    {
                        "claimKey": expected_claim["id"],
                        "supportResult": "unsupported",
                        "locatorResult": "inaccurate",
                        "conflictResult": "missed" if case["expectedConflict"] else "none",
                        "expectedEvidenceCount": len(expected_claim["supportedBy"]),
                        "observedEvidenceCount": 0,
                        "failureCode": "unsupported_claim",
                    }
                )
        public_claims = _public_claim_rows(claim_rows)
        unsupported = sum(row["supportResult"] == "unsupported" for row in public_claims)
        return {
            **base,
            "observedDisposition": (
                execution.observed_disposition
                if model_quality_failure
                else "not_evaluable"
            ),
            "claimSupportRate": (
                failed_metric if not public_claims else _ratio(0.0, len(public_claims))
            ),
            "evidenceRecall": failed_metric,
            "evidencePrecision": failed_metric,
            "evidenceTargetExactness": failed_metric,
            "locatorAccuracy": failed_metric,
            "conflictDetectionRate": failed_metric,
            "refusalCorrectness": (
                failed_metric
                if case["expectedDisposition"] == "refuse"
                else _unavailable("not_refusal_case")
            ),
            "unsupportedClaimCount": unsupported,
            "failureCode": (
                "insufficient_evidence"
                if model_quality_failure and not case["claims"]
                else "unsupported_claim"
            )
            if model_quality_failure
            else "scorer_error",
            "claims": public_claims,
            "campaignClaims": claim_rows,
            "qualityFailure": model_quality_failure,
            "engineeringFailure": engineering_failure,
            "campaignFailureClass": (
                "model_quality_failure"
                if model_quality_failure
                else "engineering_or_integrity_failure"
            ),
            "executionFailureCode": execution.failure_code,
            "failureOrigin": origin,
        }

    expected_claims = list(case["claims"])
    observed_claims = list(execution.observed_claims)
    used_observed: set[int] = set()
    claim_rows = []
    extra_claim_count = 0
    negated_claim_count = 0
    claim_local_forbidden_count = 0
    claim_local_forbidden_texts: list[str] = []
    case_failure: str | None = None
    provenance_hints: list[dict[str, object]] = []

    # Observed-claim categorization is disjoint and exclusive per observed claim:
    # each concept-matched claim is exactly one of {negated, forbidden, positive, unmatched}.
    # Exactly one positive may satisfy an expected claim; additional positives are extras.
    # A positive plus a separate negated concept-match yields a scored expected claim and
    # negatedClaimCount += 1 (negated is not an extra). Forbidden-only concept-matches
    # contribute to forbiddenAnswerCount, not negatedClaimCount.
    for expected_claim in expected_claims:
        matches = [
            (index, item)
            for index, item in enumerate(observed_claims)
            if index not in used_observed
            and _concepts_match(item.text, expected_claim["requiredConcepts"])
        ]
        if not matches:
            case_failure = case_failure or "unsupported_claim"
            provenance_hints.append(
                {
                    "kind": "unresolved",
                    "rule": "missing_expected_claim",
                    "path": f"$.claims[{expected_claim['id']}]",
                    "expectedClaimKey": expected_claim["id"],
                    "observedClaimText": None,
                    "nodeKey": None,
                }
            )
            claim_rows.append(
                {
                    "claimKey": expected_claim["id"],
                    "supportResult": "unsupported",
                    "locatorResult": "inaccurate",
                    "conflictResult": "missed" if case["expectedConflict"] else "none",
                    "expectedEvidenceCount": len(expected_claim["supportedBy"]),
                    "observedEvidenceCount": 0,
                    "failureCode": "unsupported_claim",
                }
            )
            continue

        positives: list[tuple[int, Any]] = []
        for index, item in matches:
            used_observed.add(index)
            category = _classify_concept_match(item.text, expected_claim)
            if category == "negated":
                negated_claim_count += 1
                case_failure = case_failure or "unsupported_claim"
                provenance_hints.append(
                    {
                        "kind": "claim_text",
                        "rule": "negated_claim",
                        "path": f"$.claims[{expected_claim['id']}]",
                        "expectedClaimKey": expected_claim["id"],
                        "observedClaimText": item.text,
                        "nodeKey": "researcher",
                    }
                )
            elif category == "forbidden":
                claim_local_forbidden_count += 1
                claim_local_forbidden_texts.append(item.text)
                case_failure = case_failure or "unsupported_claim"
                provenance_hints.append(
                    {
                        "kind": "claim_text",
                        "rule": "forbidden_claim",
                        "path": f"$.claims[{expected_claim['id']}]",
                        "expectedClaimKey": expected_claim["id"],
                        "observedClaimText": item.text,
                        "nodeKey": "researcher",
                    }
                )
            elif category == "positive":
                positives.append((index, item))
            else:
                # Concept-only noise under this expected claim: one extra, not a satisfier.
                extra_claim_count += 1
                case_failure = case_failure or "unsupported_claim"
                provenance_hints.append(
                    {
                        "kind": "claim_text",
                        "rule": "concept_unmatched_extra",
                        "path": f"$.claims[{expected_claim['id']}]",
                        "expectedClaimKey": expected_claim["id"],
                        "observedClaimText": item.text,
                        "nodeKey": "researcher",
                    }
                )

        if not positives:
            # No valid positive assertion; expected claim remains unsupported.
            # Prefer evidence count from the first concept match for diagnostics.
            claim_rows.append(
                {
                    "claimKey": expected_claim["id"],
                    "supportResult": "unsupported",
                    "locatorResult": "inaccurate",
                    "conflictResult": "missed" if case["expectedConflict"] else "none",
                    "expectedEvidenceCount": len(expected_claim["supportedBy"]),
                    "observedEvidenceCount": len(matches[0][1].evidence_ids),
                    "failureCode": "unsupported_claim",
                }
            )
            continue

        # First positive satisfies the expected claim; any additional positives are extras.
        if len(positives) > 1:
            extra_claim_count += len(positives) - 1
            case_failure = case_failure or "unsupported_claim"
            for _extra_index, extra_item in positives[1:]:
                provenance_hints.append(
                    {
                        "kind": "claim_text",
                        "rule": "duplicate_positive_extra",
                        "path": f"$.claims[{expected_claim['id']}]",
                        "expectedClaimKey": expected_claim["id"],
                        "observedClaimText": extra_item.text,
                        "nodeKey": "researcher",
                    }
                )

        _index, observed = positives[0]
        observed_evidence = set(observed.evidence_ids)
        expected_evidence = set(expected_claim["supportedBy"])
        supported = expected_evidence == observed_evidence
        if not supported:
            if expected_evidence.issubset(observed_evidence):
                case_failure = case_failure or "locator_inaccurate"
                failure_code = "locator_inaccurate"
            elif observed_evidence.issubset(expected_evidence):
                case_failure = case_failure or "evidence_missing"
                failure_code = "evidence_missing"
            else:
                case_failure = case_failure or "unsupported_claim"
                failure_code = "unsupported_claim"
            provenance_hints.append(
                {
                    "kind": "claim_text",
                    "rule": failure_code,
                    "path": f"$.claims[{expected_claim['id']}].evidenceIds",
                    "expectedClaimKey": expected_claim["id"],
                    "observedClaimText": observed.text,
                    "nodeKey": "researcher",
                }
            )
        else:
            failure_code = None
        claim_rows.append(
            {
                "claimKey": expected_claim["id"],
                "supportResult": "supported" if supported else "unsupported",
                "locatorResult": "accurate" if supported else "inaccurate",
                "conflictResult": (
                    "detected"
                    if case["expectedConflict"] and observed.conflicted
                    else "missed"
                    if case["expectedConflict"]
                    else "none"
                ),
                "expectedEvidenceCount": len(expected_evidence),
                "observedEvidenceCount": len(observed_evidence),
                "failureCode": failure_code,
            }
        )

    unmatched = [item for index, item in enumerate(observed_claims) if index not in used_observed]
    if unmatched:
        extra_claim_count += len(unmatched)
        case_failure = case_failure or "unsupported_claim"
        for offset, item in enumerate(unmatched):
            provenance_hints.append(
                {
                    "kind": "claim_text",
                    "rule": "unmatched_extra_claim",
                    "path": f"$.observedClaims[{offset + 1}]",
                    "expectedClaimKey": None,
                    "observedClaimText": item.text,
                    "nodeKey": "researcher",
                }
            )
            claim_rows.append(
                {
                    "claimKey": f"unmatched-claim-{offset + 1}",
                    "supportResult": "unsupported",
                    "locatorResult": "inaccurate",
                    "conflictResult": "none",
                    "expectedEvidenceCount": 0,
                    "observedEvidenceCount": len(item.evidence_ids),
                    "failureCode": "unsupported_claim",
                    "campaignOnly": True,
                }
            )

    expected_evidence = set(case["expectedEvidenceCaseIds"])
    observed_evidence = set(execution.evidence_ids)
    evidence_recall = (
        len(expected_evidence & observed_evidence) / len(expected_evidence)
        if expected_evidence
        else 1.0
    )
    evidence_precision = (
        len(expected_evidence & observed_evidence) / len(observed_evidence)
        if observed_evidence
        else (1.0 if not expected_evidence else 0.0)
    )
    evidence_target_exact = expected_evidence == observed_evidence
    if not evidence_target_exact and case_failure is None:
        case_failure = "locator_inaccurate" if observed_evidence else "evidence_missing"
        provenance_hints.append(
            {
                "kind": "unresolved",
                "rule": case_failure,
                "path": "$.evidenceIds",
                "expectedClaimKey": None,
                "observedClaimText": None,
                "nodeKey": None,
            }
        )

    conflict_correct = execution.conflict_detected is bool(case["expectedConflict"])
    if not conflict_correct:
        case_failure = case_failure or (
            "conflict_missed" if case["expectedConflict"] else "unsupported_claim"
        )
        provenance_hints.append(
            {
                "kind": "node",
                "rule": "conflict_mismatch",
                "path": "$.conflictDetected",
                "expectedClaimKey": None,
                "observedClaimText": None,
                "nodeKey": "critic" if execution.mode == "research" else "quick",
            }
        )

    case_forbidden_patterns = list(case.get("forbiddenAnswerPatterns") or [])
    case_level_forbidden = any(
        re.search(pattern, execution.output, flags=re.IGNORECASE)
        for pattern in case_forbidden_patterns
    )
    # forbiddenAnswerCount = claim-local forbidden occurrences
    # + optional case-level output forbidden unit when not already represented by a
    # claim-local forbidden claim whose text itself matches a case-level pattern.
    forbidden_answer_count = claim_local_forbidden_count
    if case_level_forbidden:
        already_counted = any(
            _matches_any(text, case_forbidden_patterns)
            for text in claim_local_forbidden_texts
        )
        if not already_counted:
            forbidden_answer_count += 1
            # Case-level forbidden without a claim-local forbidden text has no exact
            # researcher claim binding; research fails closed via unresolved unless
            # disposition/empty-selection also points at synthesizer below.
            if not claim_local_forbidden_texts:
                if execution.mode == "quick":
                    provenance_hints.append(
                        {
                            "kind": "node",
                            "rule": "case_forbidden_answer",
                            "path": "$.output",
                            "expectedClaimKey": None,
                            "observedClaimText": None,
                            "nodeKey": "quick",
                        }
                    )
                else:
                    provenance_hints.append(
                        {
                            "kind": "unresolved",
                            "rule": "case_forbidden_answer",
                            "path": "$.output",
                            "expectedClaimKey": None,
                            "observedClaimText": None,
                            "nodeKey": None,
                        }
                    )
    is_refusal_case = case["expectedDisposition"] == "refuse"
    refusal_correct = (
        execution.observed_disposition == "refuse"
        and not observed_claims
        and not case_level_forbidden
        and not execution.conflict_detected
    )
    if is_refusal_case and not refusal_correct:
        case_failure = case_failure or (
            "insufficient_evidence"
            if observed_claims or execution.observed_disposition != "refuse"
            else "unsupported_claim"
        )
        provenance_hints.append(
            {
                "kind": "node",
                "rule": "refusal_or_empty_selection_mismatch",
                "path": "$.disposition",
                "expectedClaimKey": None,
                "observedClaimText": None,
                "nodeKey": "synthesizer" if execution.mode == "research" else "quick",
            }
        )

    if case["expectedDisposition"] == "answer" and execution.observed_disposition != "answer":
        case_failure = case_failure or "unsupported_claim"
        provenance_hints.append(
            {
                "kind": "node",
                "rule": "disposition_mismatch",
                "path": "$.disposition",
                "expectedClaimKey": None,
                "observedClaimText": None,
                "nodeKey": "synthesizer" if execution.mode == "research" else "quick",
            }
        )

    public_claims = _public_claim_rows(claim_rows)
    unsupported_claim_count = sum(row["supportResult"] == "unsupported" for row in public_claims)
    claim_support = (
        _ratio(
            sum(row["supportResult"] == "supported" for row in public_claims) / len(public_claims),
            len(public_claims),
        )
        if public_claims
        else _ratio(1.0 if is_refusal_case and refusal_correct else 0.0, 1)
    )
    quality_failure = (
        case_failure is not None
        or extra_claim_count > 0
        or negated_claim_count > 0
        or forbidden_answer_count > 0
    )
    if quality_failure and case_failure is None:
        case_failure = "unsupported_claim"

    return {
        **base,
        "claimSupportRate": claim_support,
        "evidenceRecall": _ratio(evidence_recall, 1),
        "evidencePrecision": _ratio(evidence_precision, 1),
        "evidenceTargetExactness": _ratio(float(evidence_target_exact), 1),
        # R700 import compatibility: exact Evidence-ID set equality only.
        "locatorAccuracy": _ratio(float(evidence_target_exact), 1),
        "conflictDetectionRate": _ratio(float(conflict_correct), 1),
        "refusalCorrectness": (
            _ratio(float(refusal_correct), 1)
            if is_refusal_case
            else _unavailable("not_refusal_case")
        ),
        "unsupportedClaimCount": unsupported_claim_count,
        "extraClaimCount": extra_claim_count,
        "negatedClaimCount": negated_claim_count,
        "forbiddenAnswerCount": forbidden_answer_count,
        "failureCode": case_failure,
        "claims": public_claims,
        "campaignClaims": claim_rows,
        "qualityFailure": quality_failure,
        "engineeringFailure": False,
        "campaignFailureClass": "model_quality_failure" if quality_failure else None,
        "executionFailureCode": None,
        # Private evaluator-only provenance hints. Never serialize into R700/public
        # paired artifacts; underscore prefix marks internal use only.
        "_quality_failure_provenance_hints": provenance_hints if quality_failure else [],
    }


def _researcher_claim_texts(raw_text: str) -> set[str] | None:
    """Structurally parse Researcher JSON for exact claims[].text values."""
    import json

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    claims = payload.get("claims")
    if not isinstance(claims, list):
        return None
    texts: set[str] = set()
    for item in claims:
        if not isinstance(item, dict):
            return None
        text = item.get("text")
        if not isinstance(text, str):
            return None
        texts.add(text)
    return texts


def _records_for_node(capture: DiagnosticCapture, node_key: str) -> list[RawOutputRecord]:
    return [item for item in capture.records if item.node_key == node_key]


def _resolve_hint_record(
    hint: dict[str, object],
    capture: DiagnosticCapture,
    *,
    mode: str,
) -> RawOutputRecord:
    kind = str(hint.get("kind") or "")
    if kind == "unresolved":
        raise R803EvaluationError("quality_failure_provenance_unresolved:unresolved_hint")
    if kind == "node":
        node_key = str(hint.get("nodeKey") or "")
        matches = _records_for_node(capture, node_key)
        if len(matches) != 1:
            raise R803EvaluationError(
                f"quality_failure_provenance_unresolved:node:{node_key}:count={len(matches)}"
            )
        return matches[0]
    if kind == "claim_text":
        observed_text = hint.get("observedClaimText")
        if not isinstance(observed_text, str) or not observed_text:
            raise R803EvaluationError("quality_failure_provenance_unresolved:empty_claim_text")
        if mode == "quick":
            matches = _records_for_node(capture, "quick")
            if len(matches) != 1:
                raise R803EvaluationError(
                    f"quality_failure_provenance_unresolved:quick:count={len(matches)}"
                )
            return matches[0]
        # Research: exact structural claims[].text match across researcher raw records.
        hits: list[RawOutputRecord] = []
        for record in _records_for_node(capture, "researcher"):
            texts = _researcher_claim_texts(record.raw_text)
            if texts is None:
                continue
            if observed_text in texts:
                hits.append(record)
        if len(hits) != 1:
            raise R803EvaluationError(
                "quality_failure_provenance_unresolved:"
                f"claim_text:matches={len(hits)}"
            )
        return hits[0]
    raise R803EvaluationError(f"quality_failure_provenance_unresolved:unknown_hint_kind:{kind}")


def _normalize_research_empty_selection_hints(
    hints: list[dict[str, object]],
    execution: CaseExecution,
) -> list[dict[str, object]]:
    """Subsume empty-selection downstream unresolved hints under Synthesizer.

    When a successful Research execution ends with an empty Synthesizer selection
    (no observed claims) and the scorer already emitted a Synthesizer
    disposition/refusal mismatch node hint, ``missing_expected_claim`` unresolved
    hints are causal consequences of that empty final selection and must not
    block binding the unique Synthesizer raw record.

    Does not broadly ignore unresolved hints: missing claims without this exact
    Research empty-selection disposition condition still fail closed. Independent
    claim-text / critic hints are preserved so multi-record ambiguity remains.
    """
    if execution.mode != "research":
        return hints
    # Final empty selection: successful transport produced no selected claims.
    if execution.observed_claims:
        return hints
    synth_rules = frozenset(
        {
            "disposition_mismatch",
            "refusal_or_empty_selection_mismatch",
        }
    )
    has_synth_disposition = any(
        hint.get("kind") == "node"
        and hint.get("nodeKey") == "synthesizer"
        and str(hint.get("rule") or "") in synth_rules
        for hint in hints
    )
    if not has_synth_disposition:
        return hints

    # Only empty-selection downstream consequences are subsumed.
    subsumed_unresolved_rules = frozenset(
        {
            "missing_expected_claim",
            # Empty selection yields empty evidence set; pure evidence-target
            # unresolved is a downstream consequence, not an independent root cause.
            "evidence_missing",
            "locator_inaccurate",
        }
    )
    normalized: list[dict[str, object]] = []
    for hint in hints:
        if (
            hint.get("kind") == "unresolved"
            and str(hint.get("rule") or "") in subsumed_unresolved_rules
        ):
            continue
        normalized.append(hint)
    return normalized


def resolve_successful_quality_failure_diagnostic(
    score: dict[str, Any],
    execution: CaseExecution,
    capture: DiagnosticCapture | None,
) -> OutputFailureDiagnostic | None:
    """Bind exact raw provenance for successful-transport scorer quality failures.

    Returns None when there is no successful-transport quality failure to resolve
    (no quality failure, or execution already failed before scoring semantics).
    Raises R803EvaluationError when a quality failure cannot be bound to exactly
    one raw capture record.
    """
    if execution.failure_code is not None:
        return None
    if not score.get("qualityFailure"):
        return None
    if capture is None:
        raise R803EvaluationError("quality_failure_provenance_unresolved:missing_capture")

    hints = list(score.get("_quality_failure_provenance_hints") or [])
    if not hints:
        raise R803EvaluationError("quality_failure_provenance_unresolved:empty_hints")
    hints = _normalize_research_empty_selection_hints(hints, execution)
    if not hints:
        raise R803EvaluationError("quality_failure_provenance_unresolved:empty_hints")

    if execution.mode == "quick":
        quick_records = _records_for_node(capture, "quick")
        if len(quick_records) != 1:
            raise R803EvaluationError(
                f"quality_failure_provenance_unresolved:quick:count={len(quick_records)}"
            )
        bound = quick_records[0]
        primary = hints[0]
        return with_failure_origin(
            OutputFailureDiagnostic(
                stage="scorer_v2",
                rule=str(primary.get("rule") or "scorer_semantic_failure"),
                path=str(primary.get("path") or "$"),
                node_key="quick",
                logical_call_key=bound.logical_call_key,
                raw_output_sha256=bound.sha256,
                failure_code="scorer_semantic_failure",
            )
        )

    resolved_records: list[RawOutputRecord] = []
    for hint in hints:
        resolved_records.append(
            _resolve_hint_record(hint, capture, mode=execution.mode)
        )
    identities = {(item.logical_call_key, item.sha256) for item in resolved_records}
    if len(identities) != 1:
        raise R803EvaluationError(
            f"quality_failure_provenance_unresolved:ambiguous_records:{len(identities)}"
        )
    bound = resolved_records[0]
    primary = hints[0]
    return with_failure_origin(
        OutputFailureDiagnostic(
            stage="scorer_v2",
            rule=str(primary.get("rule") or "scorer_semantic_failure"),
            path=str(primary.get("path") or "$"),
            node_key=bound.node_key,
            logical_call_key=bound.logical_call_key,
            raw_output_sha256=bound.sha256,
            failure_code="scorer_semantic_failure",
        )
    )


def assert_quality_failure_diagnostic_bound(
    *,
    mode: str,
    case_key: str,
    score: dict[str, Any],
    diagnostic: OutputFailureDiagnostic | None,
    capture: DiagnosticCapture | None,
) -> None:
    """Fail closed when a model-quality failure lacks exact raw provenance."""
    if not score.get("qualityFailure"):
        return
    if diagnostic is None:
        raise R803EvaluationError(
            f"quality_failure_provenance_unresolved:{mode}:{case_key}"
        )
    origin = classify_failure_origin(diagnostic.failure_code)
    if origin != "model_or_workflow_quality":
        return
    if (
        not diagnostic.node_key
        or not diagnostic.logical_call_key
        or not diagnostic.raw_output_sha256
    ):
        raise R803EvaluationError(
            f"quality_failure_provenance_unresolved:{mode}:{case_key}"
        )
    if capture is None:
        raise R803EvaluationError(
            f"quality_failure_provenance_unresolved:{mode}:{case_key}"
        )
    matches = [
        item
        for item in capture.records
        if item.logical_call_key == diagnostic.logical_call_key
        and item.sha256 == diagnostic.raw_output_sha256
        and item.node_key == diagnostic.node_key
    ]
    if len(matches) != 1:
        raise R803EvaluationError(
            f"quality_failure_provenance_unresolved:{mode}:{case_key}"
        )



def build_import_report_v2(
    package: EvaluationPackage,
    *,
    mode: str,
    executions: tuple[CaseExecution, ...],
    created_at,
    completed_at,
    prompt_binding_sha256: str,
    diagnostics: dict[str, OutputFailureDiagnostic | None] | None = None,
    baseline_evaluation_run_id: str | None = None,
) -> dict[str, Any]:
    from datetime import datetime

    from ai_pdf_api.schemas.evaluation import EvaluationImportReport

    from ai_pdf_worker.r803_evaluation_contract import ProviderCallRecord

    if package.comparison_keys.scorer_version != SCORER_VERSION:
        raise R803EvaluationError("scorer_version_mismatch")
    by_id = {item.case_key: item for item in executions}
    if set(by_id) != {case["id"] for case in package.cases}:
        raise R803EvaluationError("execution_case_set_mismatch")
    diagnostics = diagnostics or {}
    scored = [
        score_case_v2(case, by_id[case["id"]], diagnostic=diagnostics.get(case["id"]))
        for case in package.cases
    ]
    model_quality_failures = [row for row in scored if row["qualityFailure"]]
    engineering_failures = [row for row in scored if row["engineeringFailure"]]
    failed = bool(model_quality_failures or engineering_failures)
    input_tokens = sum(item.input_tokens for item in executions)
    output_tokens = sum(item.output_tokens for item in executions)
    provider_calls = sum(item.provider_calls for item in executions)
    pricing = package.document["providerProfile"]["pricingVersion"]
    if pricing != "research-pricing-v1":
        raise R803EvaluationError("unsupported_pricing_version")
    cost_micros = (input_tokens * 2_500_000 + output_tokens * 15_000_000 + 999_999) // 1_000_000
    for row in scored:
        execution = by_id[row["caseKey"]]
        case_cost = (
            execution.input_tokens * 2_500_000 + execution.output_tokens * 15_000_000 + 999_999
        ) // 1_000_000
        row["cost"]["amountMicros"] = case_cost
    grouped_calls: dict[str, list[ProviderCallRecord]] = {}
    for execution in executions:
        for call in execution.calls:
            grouped_calls.setdefault(call.logical_call_key, []).append(call)
    retry_count = sum(max(0, len(calls) - 1) for calls in grouped_calls.values())
    retried_calls = [calls for calls in grouped_calls.values() if len(calls) > 1]
    recovered_calls = sum(calls[-1].status == "succeeded" for calls in retried_calls)
    retry_rate = (
        _ratio(retry_count / provider_calls, provider_calls)
        if provider_calls
        else _unavailable("no_provider_calls")
    )
    recovery_rate = (
        _ratio(recovered_calls / len(retried_calls), len(retried_calls))
        if retried_calls
        else _unavailable("no_recovery_scenarios")
    )
    parallel_values = [item.parallel_speedup for item in executions if item.parallel_speedup is not None]
    keys = package.comparison_keys
    # R700 import contract: failed runs must set engineeringGate=fail and keep
    # model/user gates not_evaluable. Campaign-level model quality is decided
    # outside this import report.
    if failed:
        # Public R700 v1 report cannot express campaign gate separation. Any failed
        # case remains engineeringGate=fail + modelQualityGate=not_evaluable here;
        # campaign semantic gates live only in paired/round/campaign v2 evidence.
        if model_quality_failures and any(
            classify_failure_origin(by_id[row["caseKey"]].failure_code)
            == "model_or_workflow_quality"
            for row in model_quality_failures
        ):
            failure = {
                "code": "schema_violation",
                "message": "One or more evaluation cases failed the frozen semantic quality contract.",
            }
        elif engineering_failures and all(
            str(by_id[row["caseKey"]].failure_code or "").startswith("generation_")
            for row in engineering_failures
        ):
            failure = {
                "code": "provider_error",
                "message": "One or more evaluation cases failed at the generation provider.",
            }
        else:
            failure = {
                "code": "evaluation_internal_error",
                "message": "One or more evaluation cases failed the frozen campaign contract.",
            }
        model_quality_gate = "not_evaluable"
        engineering_gate = "fail"
        status = "failed"
    else:
        failure = None
        model_quality_gate = "not_evaluable"
        engineering_gate = "pass"
        status = "completed"

    report = {
        "schemaVersion": "citeframe-evaluation-report-v1",
        "suite": {
            "suiteKey": package.document["suite"]["suiteKey"],
            "version": package.document["suite"]["version"],
            "title": package.document["suite"]["title"],
            "fixtureManifestSha256": keys.fixture_manifest_sha256,
            "scorerVersion": keys.scorer_version,
            "caseCount": len(package.cases),
        },
        "evaluation": {
            "mode": mode,
            "status": status,
            "researchRunId": None,
            "baselineEvaluationRunId": baseline_evaluation_run_id if mode == "research" else None,
            **keys.as_dict(),
            "workflowVersionId": package.document["research"]["workflowVersionId"]
            if mode == "research"
            else None,
            "promptBindingSha256": prompt_binding_sha256,
            "sourceArtifact": None,
            "modelQualityEvidenceKind": "provider_backed",
            "userValueEvidenceRef": None,
            "wallTimeMs": int((completed_at - created_at).total_seconds() * 1000),
            "providerCalls": provider_calls,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "cost": {"currency": "USD", "amountMicros": cost_micros},
            "parallelSpeedup": sum(parallel_values) / len(parallel_values) if parallel_values else None,
            "retryRate": retry_rate,
            "recoveryRate": recovery_rate,
            "claimSupportRate": aggregate_ratio(scored, "claimSupportRate"),
            "evidenceRecall": aggregate_ratio(scored, "evidenceRecall"),
            "evidencePrecision": aggregate_ratio(scored, "evidencePrecision"),
            "locatorAccuracy": aggregate_ratio(scored, "locatorAccuracy"),
            "conflictDetectionRate": aggregate_ratio(scored, "conflictDetectionRate"),
            "refusalCorrectness": aggregate_ratio(scored, "refusalCorrectness"),
            "engineeringGate": engineering_gate,
            "modelQualityGate": model_quality_gate,
            "userValueGate": "not_evaluable",
            "failure": failure,
            "createdAt": created_at.isoformat() if isinstance(created_at, datetime) else created_at,
            "completedAt": completed_at.isoformat() if isinstance(completed_at, datetime) else completed_at,
        },
        "cases": [
            {
                key: value
                for key, value in row.items()
                if key
                in {
                    "caseKey",
                    "caseType",
                    "expectedDisposition",
                    "observedDisposition",
                    "claimSupportRate",
                    "evidenceRecall",
                    "evidencePrecision",
                    "locatorAccuracy",
                    "conflictDetectionRate",
                    "refusalCorrectness",
                    "wallTimeMs",
                    "providerCalls",
                    "cost",
                    "unsupportedClaimCount",
                    "humanInterventionCount",
                    "humanWaitMs",
                    "failureCode",
                    "claims",
                }
            }
            for row in scored
        ],
    }
    EvaluationImportReport.model_validate(report)
    report["_scorerCases"] = scored
    report["_campaignQualityFailureCount"] = len(model_quality_failures)
    report["_campaignEngineeringFailureCount"] = len(engineering_failures)
    return report
