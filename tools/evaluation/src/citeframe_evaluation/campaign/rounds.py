from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from citeframe_evaluation.paired import _case_artifact
from citeframe_evaluation.contracts import (
    CaseExecution,
    R803EvaluationError,
    file_sha256,
)
from citeframe_evaluation.diagnostics import (
    DiagnosticCapture,
    OutputFailureDiagnostic,
    secret_scan_text,
    write_raw_output_bundle,
)
from citeframe_evaluation.integrity import verify_checksums_exact, write_checksums
from citeframe_evaluation.provider import RecordedProvider
from citeframe_evaluation.runtime import (
    run_quick_case_with_diagnostics,
    run_research_case_with_diagnostics,
)
from citeframe_evaluation.scoring import (
    assert_quality_failure_diagnostic_bound,
    build_import_report_v2,
    resolve_successful_quality_failure_diagnostic,
    score_case_v2,
)
from citeframe_evaluation.campaign.plan import (
    CampaignPlan,
    ROUND_MANIFEST_SCHEMA_VERSION,
    ROUND_SCHEMA_VERSION,
    _plan_provenance_fields,
)
from citeframe_evaluation.campaign.reporting import (
    _aggregate_mode_metrics,
    _mode_semantic_gates,
    _public_import_report,
)
from citeframe_evaluation.campaign.storage import (
    _write_immutable_json,
    _write_round_start_marker,
)


def _test_provider_attestation(
    plan: CampaignPlan,
    provider: RecordedProvider,
) -> dict[str, object]:
    profile = plan.provider_profile_fingerprint
    matches_profile = (
        provider.provider == profile["provider"] and provider.model == profile["model"]
    )
    return {
        "formalEvidence": False,
        "evidenceClass": "non_formal_test_provider",
        "provider": provider.provider,
        "model": provider.model,
        "matchesFrozenProfile": matches_profile,
        "frozenProfile": profile,
        "allowTestProvider": True,
    }


def _formal_configured_attestation(
    plan: CampaignPlan,
    provider: RecordedProvider,
) -> dict[str, object]:
    """Only the formal campaign path may call this after configured_provider()."""
    profile = plan.provider_profile_fingerprint
    matches_profile = (
        provider.provider == profile["provider"] and provider.model == profile["model"]
    )
    if not matches_profile:
        raise R803EvaluationError("provider_profile_mismatch")
    return {
        "formalEvidence": True,
        "evidenceClass": "formal_configured_provider",
        "provider": provider.provider,
        "model": provider.model,
        "matchesFrozenProfile": True,
        "frozenProfile": profile,
        "allowTestProvider": False,
    }


def run_campaign_round(
    plan: CampaignPlan,
    *,
    round_index: int,
    provider: RecordedProvider,
    output_dir: Path,
    baseline_evaluation_run_id: str | None = None,
    allow_test_provider: bool = False,
) -> dict[str, Any]:
    """Public low-level round API is always explicitly test-only / non-formal.

    Direct callers cannot mint formal configured attestation. Formal evidence is
    only produced by run_or_resume_campaign(provider=None) via the internal
    configured-provider path.
    """
    if not allow_test_provider:
        raise R803EvaluationError("injected_provider_requires_allow_test_provider")
    attestation = _test_provider_attestation(plan, provider)
    return _run_campaign_round_with_attestation(
        plan,
        round_index=round_index,
        provider=provider,
        output_dir=output_dir,
        baseline_evaluation_run_id=baseline_evaluation_run_id,
        attestation=attestation,
    )


def _run_campaign_round_with_attestation(
    plan: CampaignPlan,
    *,
    round_index: int,
    provider: RecordedProvider,
    output_dir: Path,
    attestation: dict[str, object],
    baseline_evaluation_run_id: str | None = None,
) -> dict[str, Any]:
    if output_dir.is_symlink():
        raise R803EvaluationError("round_symlink_forbidden:.")
    if output_dir.exists() and not output_dir.is_dir():
        raise R803EvaluationError("round_directory_invalid_state:not_directory")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise R803EvaluationError("round_directory_not_empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise R803EvaluationError("round_symlink_forbidden:.")
    # Durable start consumes the round index before the first provider call.
    _write_round_start_marker(
        output_dir,
        plan,
        round_index=round_index,
        attestation=attestation,
    )

    package = plan.package
    quick_binding = plan.quick_prompt_binding_sha256
    research_binding = plan.research_prompt_binding_sha256
    captures: list[DiagnosticCapture] = []
    diagnostics: dict[str, dict[str, OutputFailureDiagnostic | None]] = {
        "quick": {},
        "research": {},
    }
    quick_executions: list[CaseExecution] = []
    research_executions: list[CaseExecution] = []
    cases_by_id = {case["id"]: case for case in package.cases}

    quick_started = datetime.now(UTC)
    for case_id in plan.case_order:
        case = cases_by_id[case_id]
        capture = DiagnosticCapture(case_key=case_id, mode="quick")
        execution, diagnostic = run_quick_case_with_diagnostics(
            package,
            case,
            provider,
            diagnostic_capture=capture,
        )
        captures.append(capture)
        diagnostics["quick"][case_id] = diagnostic
        quick_executions.append(execution)
    quick_completed = datetime.now(UTC)

    research_started = datetime.now(UTC)
    for case_id in plan.case_order:
        case = cases_by_id[case_id]
        capture = DiagnosticCapture(case_key=case_id, mode="research")
        execution, diagnostic = run_research_case_with_diagnostics(
            package,
            case,
            provider,
            diagnostic_capture=capture,
        )
        captures.append(capture)
        diagnostics["research"][case_id] = diagnostic
        research_executions.append(execution)
    research_completed = datetime.now(UTC)

    # Preliminarily score successful-transport cases, resolve exact raw provenance for
    # scorer quality failures, then build public reports with resolved diagnostics only.
    captures_by_mode_case: dict[tuple[str, str], DiagnosticCapture] = {}
    for capture in captures:
        captures_by_mode_case[(capture.mode, capture.case_key)] = capture

    quick_by_id = {item.case_key: item for item in quick_executions}
    research_by_id = {item.case_key: item for item in research_executions}

    for case in package.cases:
        case_id = case["id"]
        for mode, execution in (
            ("quick", quick_by_id[case_id]),
            ("research", research_by_id[case_id]),
        ):
            capture = captures_by_mode_case.get((mode, case_id))
            existing = diagnostics[mode].get(case_id)
            # Runtime schema/semantic diagnostics already bound for failed executions.
            if execution.failure_code is not None:
                assert_quality_failure_diagnostic_bound(
                    mode=mode,
                    case_key=case_id,
                    score=score_case_v2(case, execution, diagnostic=existing),
                    diagnostic=existing,
                    capture=capture,
                )
                continue
            prelim = score_case_v2(case, execution, diagnostic=None)
            if not prelim.get("qualityFailure"):
                continue
            try:
                resolved = resolve_successful_quality_failure_diagnostic(
                    prelim,
                    execution,
                    capture,
                )
            except R803EvaluationError as error:
                detail = str(error)
                if detail.startswith("quality_failure_provenance_unresolved"):
                    raise R803EvaluationError(
                        f"quality_failure_provenance_unresolved:{mode}:{case_id}"
                    ) from error
                raise
            if resolved is None:
                raise R803EvaluationError(
                    f"quality_failure_provenance_unresolved:{mode}:{case_id}"
                )
            diagnostics[mode][case_id] = resolved
            assert_quality_failure_diagnostic_bound(
                mode=mode,
                case_key=case_id,
                score=prelim,
                diagnostic=resolved,
                capture=capture,
            )

    quick_report = build_import_report_v2(
        package,
        mode="quick",
        executions=tuple(quick_executions),
        created_at=quick_started,
        completed_at=quick_completed,
        prompt_binding_sha256=quick_binding,
        diagnostics=diagnostics["quick"],
    )
    research_report = build_import_report_v2(
        package,
        mode="research",
        executions=tuple(research_executions),
        created_at=research_started,
        completed_at=research_completed,
        prompt_binding_sha256=research_binding,
        diagnostics=diagnostics["research"],
        baseline_evaluation_run_id=baseline_evaluation_run_id,
    )

    quick_scores = {
        case["id"]: score_case_v2(
            case,
            next(item for item in quick_executions if item.case_key == case["id"]),
            diagnostic=diagnostics["quick"].get(case["id"]),
        )
        for case in package.cases
    }
    research_scores = {
        case["id"]: score_case_v2(
            case,
            next(item for item in research_executions if item.case_key == case["id"]),
            diagnostic=diagnostics["research"].get(case["id"]),
        )
        for case in package.cases
    }
    # Strip private scorer hints before any artifact construction.
    for scores in (quick_scores, research_scores):
        for row in scores.values():
            row.pop("_quality_failure_provenance_hints", None)

    quick_metrics = _aggregate_mode_metrics(list(quick_scores.values()))
    research_metrics = _aggregate_mode_metrics(list(research_scores.values()))
    quick_threshold = _mode_semantic_gates(quick_metrics, plan.threshold)
    research_threshold = _mode_semantic_gates(research_metrics, plan.threshold)

    # Paired v2 semantic gates: engineering failure forces modelQuality=not_evaluable.
    # R700 import engineeringGate is compatibility-only and nested separately.
    paired = {
        "schemaVersion": "r803-paired-quality-report-v2",
        "package": {
            "path": str(package.path.relative_to(package.path.parents[2])),
            "sha256": package.sha256,
            "fixtureIds": sorted(package.assets),
            "caseCount": len(package.cases),
            "thresholdSha256": plan.threshold_sha256,
            "scorerVersion": plan.scorer_version,
            "scorerImplementationSha256": plan.scorer_implementation_sha256,
            "evaluatorClosureSha256": plan.evaluator_closure_sha256,
        },
        "comparisonKeys": package.comparison_keys.as_dict(),
        "comparisonKeysMatch": True,
        "providerAttestation": attestation,
        "promptBindings": {
            "quickPromptBindingSha256": quick_binding,
            "researchPromptBindingSha256": research_binding,
        },
        "sample": {
            "pairedCaseCount": len(package.cases),
            "independentExecutionsPerCaseAndMode": 1,
            "releaseThresholdDefined": True,
            "thresholdSha256": plan.threshold_sha256,
            "campaignRoundIndex": round_index,
        },
        "gates": {
            "quickEngineering": quick_threshold["engineering"],
            "researchEngineering": research_threshold["engineering"],
            "quickModelQuality": quick_threshold["modelQuality"],
            "researchModelQuality": research_threshold["modelQuality"],
            "engineering": (
                "fail"
                if quick_threshold["engineering"] == "fail"
                or research_threshold["engineering"] == "fail"
                else "pass"
            ),
            "modelQuality": (
                "not_evaluable"
                if quick_threshold["engineering"] == "fail"
                or research_threshold["engineering"] == "fail"
                else (
                    "fail"
                    if quick_threshold["modelQuality"] == "fail"
                    or research_threshold["modelQuality"] == "fail"
                    else "pass"
                )
            ),
            "userValue": "not_evaluable",
            "userValueReason": "m404_evidence_absent",
            "productStage": "internal_preview",
        },
        "r700ImportCompatibility": {
            "note": (
                "Public R700 v1 import schema cannot express campaign gate separation. "
                "Its engineeringGate collapses model semantic failures into engineering=fail "
                "and keeps modelQualityGate=not_evaluable. Campaign semantic gates above are authoritative."
            ),
            "quickEngineeringGate": quick_report["evaluation"]["engineeringGate"],
            "researchEngineeringGate": research_report["evaluation"]["engineeringGate"],
            "quickModelQualityGate": quick_report["evaluation"]["modelQualityGate"],
            "researchModelQualityGate": research_report["evaluation"][
                "modelQualityGate"
            ],
        },
        "aggregate": {
            "quick": quick_metrics,
            "research": research_metrics,
            "quickWallTimeMs": quick_report["evaluation"]["wallTimeMs"],
            "researchWallTimeMs": research_report["evaluation"]["wallTimeMs"],
            "quickProviderCalls": quick_report["evaluation"]["providerCalls"],
            "researchProviderCalls": research_report["evaluation"]["providerCalls"],
            "quickCost": quick_report["evaluation"]["cost"],
            "researchCost": research_report["evaluation"]["cost"],
            "researchParallelSpeedup": research_report["evaluation"]["parallelSpeedup"],
        },
        "cases": [
            {
                "caseKey": case["id"],
                "quick": {
                    **_case_artifact(
                        next(
                            item
                            for item in quick_executions
                            if item.case_key == case["id"]
                        ),
                        {
                            **quick_scores[case["id"]],
                            "locatorAccuracy": quick_scores[case["id"]][
                                "locatorAccuracy"
                            ],
                        },
                    ),
                    "score": {
                        key: quick_scores[case["id"]][key]
                        for key in (
                            "claimSupportRate",
                            "evidenceRecall",
                            "evidencePrecision",
                            "evidenceTargetExactness",
                            "locatorAccuracy",
                            "conflictDetectionRate",
                            "refusalCorrectness",
                        )
                    },
                    "diagnostic": quick_scores[case["id"]]["diagnostic"],
                    "qualityFailure": quick_scores[case["id"]]["qualityFailure"],
                    "engineeringFailure": quick_scores[case["id"]][
                        "engineeringFailure"
                    ],
                    "extraClaimCount": quick_scores[case["id"]]["extraClaimCount"],
                    "negatedClaimCount": quick_scores[case["id"]]["negatedClaimCount"],
                    "forbiddenAnswerCount": quick_scores[case["id"]][
                        "forbiddenAnswerCount"
                    ],
                },
                "research": {
                    **_case_artifact(
                        next(
                            item
                            for item in research_executions
                            if item.case_key == case["id"]
                        ),
                        {
                            **research_scores[case["id"]],
                            "locatorAccuracy": research_scores[case["id"]][
                                "locatorAccuracy"
                            ],
                        },
                    ),
                    "score": {
                        key: research_scores[case["id"]][key]
                        for key in (
                            "claimSupportRate",
                            "evidenceRecall",
                            "evidencePrecision",
                            "evidenceTargetExactness",
                            "locatorAccuracy",
                            "conflictDetectionRate",
                            "refusalCorrectness",
                        )
                    },
                    "diagnostic": research_scores[case["id"]]["diagnostic"],
                    "qualityFailure": research_scores[case["id"]]["qualityFailure"],
                    "engineeringFailure": research_scores[case["id"]][
                        "engineeringFailure"
                    ],
                    "extraClaimCount": research_scores[case["id"]]["extraClaimCount"],
                    "negatedClaimCount": research_scores[case["id"]][
                        "negatedClaimCount"
                    ],
                    "forbiddenAnswerCount": research_scores[case["id"]][
                        "forbiddenAnswerCount"
                    ],
                },
            }
            for case in package.cases
        ],
    }

    # Single-pass evidence graph:
    # leaf artifacts -> round-report -> round-manifest -> SHA256SUMS (not self)
    leaf_hashes: dict[str, str] = {}
    leaf_hashes["round-start.json"] = file_sha256(output_dir / "round-start.json")
    leaf_hashes["round-start.sha256.json"] = file_sha256(
        output_dir / "round-start.sha256.json"
    )
    leaf_hashes["quick-evaluation.json"] = _write_immutable_json(
        output_dir / "quick-evaluation.json",
        _public_import_report(quick_report),
    )
    leaf_hashes["research-evaluation.json"] = _write_immutable_json(
        output_dir / "research-evaluation.json",
        _public_import_report(research_report),
    )
    leaf_hashes["paired-quality-report.json"] = _write_immutable_json(
        output_dir / "paired-quality-report.json",
        paired,
    )
    raw_hashes = write_raw_output_bundle(output_dir, captures)
    leaf_hashes.update(raw_hashes)
    for relative in raw_hashes:
        if relative.endswith(".txt"):
            text = (output_dir / relative).read_text(encoding="utf-8")
            if text and secret_scan_text(text):
                raise R803EvaluationError(f"secret_material_in_raw_output:{relative}")

    engineering_fail = (
        quick_threshold["engineering"] == "fail"
        or research_threshold["engineering"] == "fail"
    )
    if engineering_fail:
        model_quality = "not_evaluable"
    elif (
        quick_threshold["modelQuality"] == "fail"
        or research_threshold["modelQuality"] == "fail"
    ):
        model_quality = "fail"
    else:
        model_quality = "pass"
    quality_fail = model_quality == "fail"

    round_report = {
        "schemaVersion": ROUND_SCHEMA_VERSION,
        "roundIndex": round_index,
        **_plan_provenance_fields(plan),
        "providerAttestation": attestation,
        "leafArtifactHashes": dict(sorted(leaf_hashes.items())),
        "gates": {
            "quickEngineering": quick_threshold["engineering"],
            "researchEngineering": research_threshold["engineering"],
            "quickModelQuality": quick_threshold["modelQuality"],
            "researchModelQuality": research_threshold["modelQuality"],
            "engineering": "fail" if engineering_fail else "pass",
            "modelQuality": model_quality,
            "userValue": "not_evaluable",
            "productStage": "internal_preview",
        },
        "thresholdEvaluation": {
            "quick": quick_threshold,
            "research": research_threshold,
        },
        "stop": {
            "qualityFailure": quality_fail,
            "engineeringFailure": engineering_fail,
            "freezeCampaign": quality_fail or engineering_fail,
        },
        "metrics": {
            "quick": quick_metrics,
            "research": research_metrics,
        },
        "cost": {
            "quick": quick_report["evaluation"]["cost"],
            "research": research_report["evaluation"]["cost"],
        },
        "usage": {
            "quickProviderCalls": quick_report["evaluation"]["providerCalls"],
            "researchProviderCalls": research_report["evaluation"]["providerCalls"],
            "quickInputTokens": quick_report["evaluation"]["inputTokens"],
            "quickOutputTokens": quick_report["evaluation"]["outputTokens"],
            "researchInputTokens": research_report["evaluation"]["inputTokens"],
            "researchOutputTokens": research_report["evaluation"]["outputTokens"],
            "quickWallTimeMs": quick_report["evaluation"]["wallTimeMs"],
            "researchWallTimeMs": research_report["evaluation"]["wallTimeMs"],
        },
    }
    round_report_sha256 = _write_immutable_json(
        output_dir / "round-report.json", round_report
    )

    round_manifest = {
        "schemaVersion": ROUND_MANIFEST_SCHEMA_VERSION,
        "roundIndex": round_index,
        **_plan_provenance_fields(plan),
        "roundReportSha256": round_report_sha256,
        "leafArtifactHashes": dict(sorted(leaf_hashes.items())),
        "artifactHashes": dict(
            sorted(
                {
                    **leaf_hashes,
                    "round-report.json": round_report_sha256,
                }.items()
            )
        ),
    }
    round_manifest_sha256 = _write_immutable_json(
        output_dir / "round-manifest.json", round_manifest
    )

    all_hashes = {
        **leaf_hashes,
        "round-report.json": round_report_sha256,
        "round-manifest.json": round_manifest_sha256,
    }
    write_checksums(output_dir, all_hashes)

    return {
        "roundReport": {
            **round_report,
            "roundReportSha256": round_report_sha256,
            "roundManifestSha256": round_manifest_sha256,
        },
        "hashes": all_hashes,
        "quickReport": quick_report,
        "researchReport": research_report,
        "pairedReport": paired,
    }


def _load_existing_round(
    round_dir: Path, plan: CampaignPlan, round_index: int
) -> dict[str, Any]:
    hashes = verify_checksums_exact(round_dir)
    required = {
        "quick-evaluation.json",
        "research-evaluation.json",
        "paired-quality-report.json",
        "round-report.json",
        "round-manifest.json",
        "round-start.json",
        "round-start.sha256.json",
        "raw-outputs/manifest.json",
    }
    missing = sorted(name for name in required if name not in hashes)
    if missing:
        raise R803EvaluationError(f"missing_round_artifacts:{','.join(missing)}")

    manifest = json.loads(
        (round_dir / "round-manifest.json").read_text(encoding="utf-8")
    )
    report = json.loads((round_dir / "round-report.json").read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != ROUND_MANIFEST_SCHEMA_VERSION:
        raise R803EvaluationError("unsupported_round_manifest_schema")
    if report.get("schemaVersion") != ROUND_SCHEMA_VERSION:
        raise R803EvaluationError("unsupported_round_report_schema")
    if (
        manifest.get("roundIndex") != round_index
        or report.get("roundIndex") != round_index
    ):
        raise R803EvaluationError("round_index_mismatch")
    if hashes["round-report.json"] != manifest.get("roundReportSha256"):
        raise R803EvaluationError("round_report_hash_drift")
    if report.get("leafArtifactHashes") != manifest.get("leafArtifactHashes"):
        raise R803EvaluationError("round_leaf_hash_set_mismatch")
    for name, digest in report.get("leafArtifactHashes", {}).items():
        if hashes.get(name) != digest:
            raise R803EvaluationError(f"round_leaf_hash_drift:{name}")
    for name, digest in manifest.get("artifactHashes", {}).items():
        if name == "round-manifest.json":
            continue
        if hashes.get(name) != digest:
            raise R803EvaluationError(f"round_manifest_artifact_drift:{name}")
    for source in (report, manifest):
        if (
            source.get("packageSha256") != plan.package_sha256
            or source.get("thresholdSha256") != plan.threshold_sha256
            or source.get("planSha256") != plan.plan_sha256
            or source.get("scorerVersion") != plan.scorer_version
            or source.get("scorerImplementationSha256")
            != plan.scorer_implementation_sha256
            or source.get("quickPromptBindingSha256")
            != plan.quick_prompt_binding_sha256
            or source.get("researchPromptBindingSha256")
            != plan.research_prompt_binding_sha256
            or source.get("evaluatorClosureSha256") != plan.evaluator_closure_sha256
        ):
            raise R803EvaluationError("round_plan_hash_drift")
    return {
        **report,
        "roundReportSha256": hashes["round-report.json"],
        "roundManifestSha256": hashes["round-manifest.json"],
        "checksumTargets": hashes,
    }
