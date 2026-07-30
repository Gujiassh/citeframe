from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ai_pdf_worker.r803_evaluation_contract import (
    R803EvaluationError,
    canonical_bytes,
    canonical_sha256,
)
from ai_pdf_worker.r803_evaluation_integrity import sanitize_logical_call_filename

DIAGNOSTICS_VERSION = "r803-raw-output-diagnostics-v1"
SAFE_DIAGNOSTIC_SCOPE = "frozen_non_confidential_synthetic_fixtures_only"

FailureOrigin = Literal["model_or_workflow_quality", "engineering_or_integrity", "unknown"]

# Explicit provenance: model-selected semantic failures after successful transport.
_MODEL_OR_WORKFLOW_CODES = frozenset(
    {
        "quick_invalid_output",
        "planner_invalid_output",
        "researcher_invalid_output",
        "verifier_invalid_output",
        "critic_invalid_output",
        "synthesizer_invalid_output",
        "claim_evidence_not_in_branch",
        "claim_requires_evidence",
        "duplicate_claim_evidence",
        "duplicate_claim_id",
        "duplicate_branch_evidence",
        "unproven_branch_evidence",
        "researcher_branch_mismatch",
        "verifier_claim_set_mismatch",
        "verifier_mutated_claim",
        "verifier_status_invalid",
        "verifier_evidence_scope_mismatch",
        "critic_conflict_set_mismatch",
        "invalid_synthesis_selection",
        "invalid_research_plan",
        "invalid_claim",
        "scorer_semantic_failure",
    }
)

_ENGINEERING_PREFIXES = (
    "generation_",
    "provider_",
)
_ENGINEERING_CODES = frozenset(
    {
        "provider_usage_unavailable",
        "evaluation_internal_error",
        "research_execution_error",
        "no_evidence_found",
        "researcher_lease_required",
        "planner_lease_required",
        "verifier_lease_required",
        "critic_lease_required",
        "synthesizer_lease_required",
        "campaign_interrupted",
        "round_incomplete",
        "evaluator_integrity_failure",
    }
)


@dataclass(frozen=True)
class RawOutputRecord:
    node_key: str
    logical_call_key: str
    attempt_number: int
    case_key: str
    mode: Literal["quick", "research"]
    raw_text: str
    sha256: str


@dataclass(frozen=True)
class OutputFailureDiagnostic:
    stage: str
    rule: str
    path: str
    node_key: str | None
    logical_call_key: str | None
    raw_output_sha256: str | None
    failure_code: str
    failure_origin: FailureOrigin = "unknown"


class DiagnosticCapture:
    """Evaluator-only raw-output capture for the frozen synthetic package."""

    def __init__(
        self,
        *,
        case_key: str,
        mode: Literal["quick", "research"],
        scope: str = SAFE_DIAGNOSTIC_SCOPE,
    ) -> None:
        if scope != SAFE_DIAGNOSTIC_SCOPE:
            raise R803EvaluationError("diagnostic_scope_not_approved")
        self.case_key = case_key
        self.mode = mode
        self.scope = scope
        self._lock = threading.RLock()
        self._records: list[RawOutputRecord] = []
        self._by_logical_key: dict[str, RawOutputRecord] = {}

    def record(
        self,
        *,
        node_key: str,
        logical_call_key: str,
        attempt_number: int,
        raw_text: str,
    ) -> RawOutputRecord:
        findings = secret_scan_text(raw_text)
        if findings:
            raise R803EvaluationError(f"raw_output_contains_forbidden_material:{','.join(findings)}")
        digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        record = RawOutputRecord(
            node_key=node_key,
            logical_call_key=logical_call_key,
            attempt_number=attempt_number,
            case_key=self.case_key,
            mode=self.mode,
            raw_text=raw_text,
            sha256=digest,
        )
        with self._lock:
            self._records.append(record)
            self._by_logical_key[logical_call_key] = record
        return record

    @property
    def records(self) -> tuple[RawOutputRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def get_by_logical_call_key(self, logical_call_key: str) -> RawOutputRecord | None:
        with self._lock:
            return self._by_logical_key.get(logical_call_key)

    def latest_for(self, node_key: str | None = None) -> RawOutputRecord | None:
        with self._lock:
            for item in reversed(self._records):
                if node_key is None or item.node_key == node_key:
                    return item
        return None


class AgentResultValidationError(ValueError):
    def __init__(
        self,
        node_key: str,
        rule: str,
        path: str,
        *,
        logical_call_key: str | None = None,
        raw_output_sha256: str | None = None,
    ) -> None:
        self.node_key = node_key
        self.rule = rule
        self.path = path
        self.logical_call_key = logical_call_key
        self.raw_output_sha256 = raw_output_sha256
        self.failure_code = f"{node_key}_invalid_output"
        self.failure_origin: FailureOrigin = "model_or_workflow_quality"
        super().__init__(self.failure_code)


def classify_failure_origin(failure_code: str | None) -> FailureOrigin:
    if not failure_code:
        return "unknown"
    code = str(failure_code)
    # Explicit model/workflow codes and agent-node *_invalid_output suffixes stay
    # model-origin unless the same code is also engineering-listed.
    if code in _MODEL_OR_WORKFLOW_CODES or code.endswith("_invalid_output"):
        if code in _ENGINEERING_CODES:
            return "engineering_or_integrity"
        return "model_or_workflow_quality"
    if code in _ENGINEERING_CODES or any(code.startswith(prefix) for prefix in _ENGINEERING_PREFIXES):
        return "engineering_or_integrity"
    return "unknown"


def with_failure_origin(diagnostic: OutputFailureDiagnostic) -> OutputFailureDiagnostic:
    origin = classify_failure_origin(diagnostic.failure_code)
    if diagnostic.failure_origin == origin:
        return diagnostic
    return OutputFailureDiagnostic(
        stage=diagnostic.stage,
        rule=diagnostic.rule,
        path=diagnostic.path,
        node_key=diagnostic.node_key,
        logical_call_key=diagnostic.logical_call_key,
        raw_output_sha256=diagnostic.raw_output_sha256,
        failure_code=diagnostic.failure_code,
        failure_origin=origin,
    )


def _raise_validation(
    node_key: str,
    rule: str,
    path: str,
    *,
    logical_call_key: str | None = None,
    raw_output_sha256: str | None = None,
) -> None:
    raise AgentResultValidationError(
        node_key,
        rule,
        path,
        logical_call_key=logical_call_key,
        raw_output_sha256=raw_output_sha256,
    )


def validate_agent_result_with_diagnostics(
    node_key: str,
    value: dict[str, Any],
    *,
    logical_call_key: str | None = None,
    raw_output_sha256: str | None = None,
) -> None:
    from ai_pdf_worker.research_agent_schemas import _string_list

    def fail(rule: str, path: str) -> None:
        _raise_validation(
            node_key,
            rule,
            path,
            logical_call_key=logical_call_key,
            raw_output_sha256=raw_output_sha256,
        )

    if node_key == "planner":
        if set(value) != {"summary", "knownGaps", "estimatedProviderCalls", "subproblems"}:
            fail("closed_object_keys", "$")
        subproblems = value["subproblems"]
        if not isinstance(value["summary"], str) or not value["summary"]:
            fail("summary_nonempty_string", "$.summary")
        if not _string_list(value["knownGaps"], unique=False):
            fail("known_gaps_string_array", "$.knownGaps")
        if type(value["estimatedProviderCalls"]) is not int or value["estimatedProviderCalls"] < 1:
            fail("estimated_provider_calls_positive_int", "$.estimatedProviderCalls")
        if not isinstance(subproblems, list) or not 1 <= len(subproblems) <= 16:
            fail("subproblems_length", "$.subproblems")
        for index, item in enumerate(subproblems):
            if (
                not isinstance(item, dict)
                or set(item) != {"question", "assetIds", "expectedEvidence"}
            ):
                fail("subproblem_closed_object", f"$.subproblems[{index}]")
            if not isinstance(item["question"], str) or not 1 <= len(item["question"]) <= 4000:
                fail("subproblem_question_bounds", f"$.subproblems[{index}].question")
            if not _string_list(item["assetIds"], maximum=100):
                fail("subproblem_asset_ids", f"$.subproblems[{index}].assetIds")
            if not _string_list(item["expectedEvidence"], maximum=20):
                fail("subproblem_expected_evidence", f"$.subproblems[{index}].expectedEvidence")
        return

    if node_key == "researcher":
        if set(value) != {"claims"}:
            fail("closed_object_keys", "$")
        if not isinstance(value["claims"], list):
            fail("claims_array", "$.claims")
        for index, item in enumerate(value["claims"]):
            if not isinstance(item, dict) or set(item) != {"text", "evidenceHandleIds"}:
                fail("claim_closed_object", f"$.claims[{index}]")
            if not isinstance(item["text"], str) or not 1 <= len(item["text"]) <= 12000:
                fail("claim_text_bounds", f"$.claims[{index}].text")
            if not _string_list(item["evidenceHandleIds"], minimum=1):
                fail(
                    "claim_evidence_handle_ids_nonempty_unique",
                    f"$.claims[{index}].evidenceHandleIds",
                )
        return

    if node_key == "verifier":
        if set(value) != {"claims"}:
            fail("closed_object_keys", "$")
        if not isinstance(value["claims"], list):
            fail("claims_array", "$.claims")
        for index, item in enumerate(value["claims"]):
            if not isinstance(item, dict) or set(item) != {"id", "status"}:
                fail("claim_closed_object", f"$.claims[{index}]")
            if not isinstance(item["id"], str):
                fail("claim_id_string", f"$.claims[{index}].id")
            if item["status"] not in {"supported", "unsupported"}:
                fail("claim_status_enum", f"$.claims[{index}].status")
        return

    if node_key == "critic":
        if set(value) != {"conflictClaimIds"}:
            fail("closed_object_keys", "$")
        if not _string_list(value["conflictClaimIds"]):
            fail("conflict_claim_ids_unique_strings", "$.conflictClaimIds")
        return

    if node_key == "synthesizer":
        if set(value) != {"factClaimIds", "unresolvedClaimIds"}:
            fail("closed_object_keys", "$")
        if not _string_list(value["factClaimIds"]):
            fail("fact_claim_ids_unique_strings", "$.factClaimIds")
        if not _string_list(value["unresolvedClaimIds"]):
            fail("unresolved_claim_ids_unique_strings", "$.unresolvedClaimIds")
        return

    fail("unknown_node", "$")


def classify_quick_payload_failure(payload: object) -> OutputFailureDiagnostic:
    if not isinstance(payload, dict):
        return with_failure_origin(
            OutputFailureDiagnostic(
                stage="quick_local_schema",
                rule="root_object",
                path="$",
                node_key="quick",
                logical_call_key=None,
                raw_output_sha256=None,
                failure_code="quick_invalid_output",
            )
        )
    if set(payload) != {"answer", "claims", "conflictDetected"}:
        return with_failure_origin(
            OutputFailureDiagnostic(
                stage="quick_local_schema",
                rule="closed_object_keys",
                path="$",
                node_key="quick",
                logical_call_key=None,
                raw_output_sha256=None,
                failure_code="quick_invalid_output",
            )
        )
    if not isinstance(payload.get("answer"), str) or not str(payload.get("answer")).strip():
        return with_failure_origin(
            OutputFailureDiagnostic(
                stage="quick_local_schema",
                rule="answer_nonempty_string",
                path="$.answer",
                node_key="quick",
                logical_call_key=None,
                raw_output_sha256=None,
                failure_code="quick_invalid_output",
            )
        )
    if not isinstance(payload.get("claims"), list):
        return with_failure_origin(
            OutputFailureDiagnostic(
                stage="quick_local_schema",
                rule="claims_array",
                path="$.claims",
                node_key="quick",
                logical_call_key=None,
                raw_output_sha256=None,
                failure_code="quick_invalid_output",
            )
        )
    if not isinstance(payload.get("conflictDetected"), bool):
        return with_failure_origin(
            OutputFailureDiagnostic(
                stage="quick_local_schema",
                rule="conflict_detected_bool",
                path="$.conflictDetected",
                node_key="quick",
                logical_call_key=None,
                raw_output_sha256=None,
                failure_code="quick_invalid_output",
            )
        )
    return with_failure_origin(
        OutputFailureDiagnostic(
            stage="quick_local_schema",
            rule="quick_invalid_output",
            path="$",
            node_key="quick",
            logical_call_key=None,
            raw_output_sha256=None,
            failure_code="quick_invalid_output",
        )
    )


def secret_scan_text(text: str) -> list[str]:
    """Scan for credential-shaped material only (not benign words like 'authorization')."""
    findings: list[str] = []
    patterns = {
        "authorization_bearer_token": (
            # Credential-shaped token length >= 16; short placeholders stay clean.
            r"(?i)\bauthorization\s*[:=]\s*bearer\s+[A-Za-z0-9\-\._~\+\/]{16,}=*"
        ),
        "api_key_assignment": (
            r"(?i)\b(?:api[_-]?key|openai_api_key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,}"
        ),
        "bearer_token_assignment": r"(?i)\bbearer\s+[A-Za-z0-9\-\._~\+\/]{16,}=*",
        # Bare OpenAI-style secrets without an assignment keyword.
        "openai_sk_token": r"(?i)\bsk-(?:proj-)?[A-Za-z0-9]{16,}\b",
        "aws_access_key_id": r"(?i)\b(?:aws_)?access_key_id\s*[:=]\s*['\"]?AKIA[0-9A-Z]{16}\b",
        "aws_secret_access_key": (
            r"(?i)\b(?:aws_)?secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{30,}"
        ),
        "password_assignment": (
            r"(?i)\b(?:password|passwd|pwd)\s*[:=]\s*['\"]?[^\s'\"]{8,}"
        ),
        "secret_assignment": r"(?i)\bsecret\s*[:=]\s*['\"]?[A-Za-z0-9_\-/.+=]{8,}",
        "token_assignment": r"(?i)\btoken\s*[:=]\s*['\"]?[A-Za-z0-9_\-/.+=]{12,}",
        "private_key_pem": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "github_token": r"(?i)\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b",
        "jwt_like_token": (
            r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"
        ),
        "request_headers_block": r"(?i)\brequest[_-]?headers\s*[:=]\s*\{",
        "hidden_reasoning": r"(?i)\bhidden_reasoning\b",
    }
    for name, pattern in patterns.items():
        if re.search(pattern, text):
            findings.append(name)
    return findings


def write_raw_output_bundle(
    output_dir: Path,
    captures: list[DiagnosticCapture],
) -> dict[str, str]:
    raw_dir = output_dir / "raw-outputs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    manifest_records: list[dict[str, object]] = []
    used_names: set[str] = set()
    for capture in captures:
        for record in capture.records:
            safe_call = sanitize_logical_call_filename(record.logical_call_key)
            relative = (
                f"raw-outputs/{capture.mode}/{capture.case_key}/"
                f"{safe_call}-a{record.attempt_number}-{record.sha256[:12]}.txt"
            )
            if relative in used_names:
                # Exact logical-call identity + attempt + content digest should be unique.
                raise R803EvaluationError(f"duplicate_raw_output_path:{relative}")
            used_names.add(relative)
            path = output_dir / relative
            if ".." in Path(relative).parts:
                raise R803EvaluationError(f"unsafe_raw_output_path:{relative}")
            path.parent.mkdir(parents=True, exist_ok=True)
            content = record.raw_text.encode("utf-8")
            with path.open("xb") as target:
                target.write(content)
            digest = hashlib.sha256(content).hexdigest()
            if digest != record.sha256:
                raise R803EvaluationError("raw_output_hash_mismatch")
            findings = secret_scan_text(record.raw_text)
            if findings:
                raise R803EvaluationError(f"secret_material_in_raw_output:{relative}")
            hashes[relative] = digest
            manifest_records.append(
                {
                    "caseKey": record.case_key,
                    "mode": record.mode,
                    "nodeKey": record.node_key,
                    "logicalCallKey": record.logical_call_key,
                    "attemptNumber": record.attempt_number,
                    "path": relative,
                    "sha256": digest,
                }
            )
    sorted_records = sorted(
        manifest_records,
        key=lambda item: (
            str(item["mode"]),
            str(item["caseKey"]),
            str(item["logicalCallKey"]),
            int(item["attemptNumber"]),
            str(item["path"]),
        ),
    )
    manifest = {
        "schemaVersion": DIAGNOSTICS_VERSION,
        "scope": SAFE_DIAGNOSTIC_SCOPE,
        "persistsProviderRequests": False,
        "persistsHeaders": False,
        "persistsApiKeysOrSecrets": False,
        "persistsHiddenReasoning": False,
        "records": sorted_records,
        # Hash the exact sorted records persisted in the manifest.
        "recordsSha256": canonical_sha256(sorted_records),
    }
    manifest_path = raw_dir / "manifest.json"
    content = canonical_bytes(manifest)
    with manifest_path.open("xb") as target:
        target.write(content)
    hashes["raw-outputs/manifest.json"] = hashlib.sha256(content).hexdigest()
    return hashes
