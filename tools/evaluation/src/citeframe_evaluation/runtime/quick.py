from __future__ import annotations

import json
from time import monotonic
from ai_pdf_api.services.providers import GenerationMessage
from citeframe_evaluation.contracts import (
    CaseExecution,
    EvaluationPackage,
    ObservedClaim,
)
from citeframe_evaluation.diagnostics import (
    DiagnosticCapture,
    OutputFailureDiagnostic,
    classify_quick_payload_failure,
)
from citeframe_evaluation.provider import EvaluationGeneration, RecordedProvider
from ai_pdf_worker.research.executor import ResearchExecutionError
from citeframe_evaluation.runtime.failures import (
    _require_final_usage,
    _safe_failure_code,
)
from citeframe_evaluation.runtime.fixtures import _lease, build_execution


def _quick_messages(
    package: EvaluationPackage, case: dict[str, object]
) -> list[GenerationMessage]:
    quick = package.document["quick"]
    scope = set(case["assetScope"])
    evidence = [item for item in package.evidence.values() if item.asset_id in scope]
    context = "\n\n".join(
        f"[{index}] evidenceId={item.id}\n{item.asset_title}, {item.locator_kind}\n{item.content}"
        for index, item in enumerate(
            sorted(evidence, key=lambda value: value.id), start=1
        )
    )
    return [
        {
            "role": "system",
            "content": f"{quick['systemPrompt']} {quick['evaluationContract']}",
        },
        {
            "role": "user",
            "content": f"Question:\n{case['question']}\n\nAsset evidence context:\n{context}",
        },
    ]


def run_quick_case_with_diagnostics(
    package: EvaluationPackage,
    case: dict[str, object],
    provider: RecordedProvider,
    *,
    diagnostic_capture: DiagnosticCapture | None = None,
) -> tuple[CaseExecution, OutputFailureDiagnostic | None]:
    started = monotonic()
    execution = build_execution(package, case)
    generation = EvaluationGeneration(provider, execution)
    try:
        logical_call_key = f"{case['id']}:quick:0:quick"
        raw = generation.generate(
            _lease(str(case["id"]), "quick"),
            node_key="quick",
            messages=_quick_messages(package, case),
        )
        if diagnostic_capture is not None:
            attempt_number = 1
            for record in reversed(generation.records_since(0)):
                if (
                    record.node_key == "quick"
                    and record.logical_call_key == logical_call_key
                    and record.status == "succeeded"
                ):
                    attempt_number = record.attempt_number
                    break
            diagnostic_capture.record(
                node_key="quick",
                logical_call_key=logical_call_key,
                attempt_number=attempt_number,
                raw_text=raw,
            )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            latest = (
                diagnostic_capture.latest_for("quick") if diagnostic_capture else None
            )
            diagnostic = OutputFailureDiagnostic(
                stage="quick_json_decode",
                rule="json_object",
                path="$",
                node_key="quick",
                logical_call_key=latest.logical_call_key
                if latest
                else f"{case['id']}:quick:0:quick",
                raw_output_sha256=latest.sha256 if latest else None,
                failure_code="quick_invalid_output",
            )
            raise ResearchExecutionError("quick_invalid_output") from error
        allowed_ids = {
            item.id
            for item in package.evidence.values()
            if item.asset_id in set(case["assetScope"])
        }
        if (
            not isinstance(payload, dict)
            or set(payload) != {"answer", "claims", "conflictDetected"}
            or not isinstance(payload.get("answer"), str)
            or not str(payload.get("answer")).strip()
            or not isinstance(payload.get("claims"), list)
            or not isinstance(payload.get("conflictDetected"), bool)
        ):
            diagnostic = classify_quick_payload_failure(payload)
            latest = (
                diagnostic_capture.latest_for("quick") if diagnostic_capture else None
            )
            if latest is not None:
                diagnostic = OutputFailureDiagnostic(
                    stage=diagnostic.stage,
                    rule=diagnostic.rule,
                    path=diagnostic.path,
                    node_key=diagnostic.node_key,
                    logical_call_key=latest.logical_call_key,
                    raw_output_sha256=latest.sha256,
                    failure_code=diagnostic.failure_code,
                )
            raise ResearchExecutionError("quick_invalid_output")
        answer = payload["answer"]
        claims = payload["claims"]
        conflict_detected = payload["conflictDetected"]
        observed_claims: list[ObservedClaim] = []
        for index, claim in enumerate(claims):
            if not isinstance(claim, dict) or set(claim) != {"text", "evidenceIds"}:
                diagnostic = OutputFailureDiagnostic(
                    stage="quick_local_schema",
                    rule="claim_closed_object",
                    path=f"$.claims[{index}]",
                    node_key="quick",
                    logical_call_key=f"{case['id']}:quick:0:quick",
                    raw_output_sha256=(
                        diagnostic_capture.latest_for("quick").sha256
                        if diagnostic_capture and diagnostic_capture.latest_for("quick")
                        else None
                    ),
                    failure_code="quick_invalid_output",
                )
                raise ResearchExecutionError("quick_invalid_output")
            text_value = claim["text"]
            claim_evidence = claim["evidenceIds"]
            if (
                not isinstance(text_value, str)
                or not text_value.strip()
                or not isinstance(claim_evidence, list)
                or not claim_evidence
                or len(claim_evidence) != len(set(claim_evidence))
                or not set(claim_evidence).issubset(allowed_ids)
            ):
                diagnostic = OutputFailureDiagnostic(
                    stage="quick_local_schema",
                    rule="claim_evidence_scope_or_shape",
                    path=f"$.claims[{index}]",
                    node_key="quick",
                    logical_call_key=f"{case['id']}:quick:0:quick",
                    raw_output_sha256=(
                        diagnostic_capture.latest_for("quick").sha256
                        if diagnostic_capture and diagnostic_capture.latest_for("quick")
                        else None
                    ),
                    failure_code="quick_invalid_output",
                )
                raise ResearchExecutionError("quick_invalid_output")
            observed_claims.append(
                ObservedClaim(
                    text_value.strip(), tuple(claim_evidence), conflict_detected
                )
            )
        evidence_ids = tuple(
            dict.fromkeys(
                evidence_id
                for claim in observed_claims
                for evidence_id in claim.evidence_ids
            )
        )
        refusal_markers = (
            "do not contain",
            "insufficient",
            "not supported",
            "cannot determine",
            "no evidence",
        )
        disposition = (
            "refuse"
            if not observed_claims
            and any(marker in answer.casefold() for marker in refusal_markers)
            else "answer"
        )
        records = generation.records_since(0)
        _require_final_usage(records)
        return (
            CaseExecution(
                case_key=str(case["id"]),
                mode="quick",
                output=answer.strip(),
                observed_disposition=disposition,
                evidence_ids=evidence_ids,
                conflict_detected=conflict_detected,
                observed_claims=tuple(observed_claims),
                wall_time_ms=int((monotonic() - started) * 1000),
                calls=records,
            ),
            None,
        )
    except Exception as error:  # noqa: BLE001 - one failed case must remain reportable
        preserved = locals().get("diagnostic")
        diagnostic = (
            preserved if isinstance(preserved, OutputFailureDiagnostic) else None
        )
        if (
            diagnostic is None
            and isinstance(error, ResearchExecutionError)
            and str(error) == "quick_invalid_output"
        ):
            latest = (
                diagnostic_capture.latest_for("quick") if diagnostic_capture else None
            )
            diagnostic = OutputFailureDiagnostic(
                stage="quick_local_schema",
                rule="quick_invalid_output",
                path="$",
                node_key="quick",
                logical_call_key=latest.logical_call_key
                if latest
                else f"{case['id']}:quick:0:quick",
                raw_output_sha256=latest.sha256 if latest else None,
                failure_code="quick_invalid_output",
            )
        return (
            CaseExecution(
                case_key=str(case["id"]),
                mode="quick",
                output="",
                observed_disposition="not_evaluable",
                evidence_ids=(),
                conflict_detected=False,
                observed_claims=(),
                wall_time_ms=int((monotonic() - started) * 1000),
                calls=generation.records_since(0),
                failure_code=_safe_failure_code(error),
            ),
            diagnostic,
        )


def run_quick_case(
    package: EvaluationPackage,
    case: dict[str, object],
    provider: RecordedProvider,
) -> CaseExecution:
    execution, _diagnostic = run_quick_case_with_diagnostics(package, case, provider)
    return execution
