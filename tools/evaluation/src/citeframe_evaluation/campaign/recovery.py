from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from citeframe_evaluation.contracts import (
    R803EvaluationError,
    canonical_sha256,
    file_sha256,
)
from citeframe_evaluation.campaign.plan import (
    CAMPAIGN_SCHEMA_VERSION,
    CampaignPlan,
    ROUND_START_SCHEMA_VERSION,
)
from citeframe_evaluation.campaign.reporting import build_campaign_report
from citeframe_evaluation.campaign.rounds import _load_existing_round
from citeframe_evaluation.campaign.storage import (
    _partial_round_file_hashes,
    _round_is_complete,
    _round_is_started,
    _validate_round_inventory,
    _write_terminal_campaign_report,
)


_SAFE_INTERRUPTION_DETAILS = frozenset(
    {
        "started_or_partial_round_not_closed",
        "round_execution_exception",
        "RuntimeError",
        "R803EvaluationError",
        "OSError",
        "ValueError",
        "TypeError",
        "KeyError",
        "FileExistsError",
        "FileNotFoundError",
        "PermissionError",
        "TimeoutError",
        "JSONDecodeError",
        "AgentResultValidationError",
        "ModelProviderError",
        "ResearchExecutionError",
        "Exception",
    }
)


def _safe_interruption_detail(reason: str, error: BaseException | None = None) -> str:
    """Store only allowlisted class/code tokens; never raw exception text."""
    if error is None:
        token = reason
        if token in _SAFE_INTERRUPTION_DETAILS:
            return token
        return "round_execution_exception"
    if type(error) is R803EvaluationError:
        return error.safe_code or "R803EvaluationError"
    if isinstance(error, R803EvaluationError):
        return "R803EvaluationError"
    name = type(error).__name__
    if name in _SAFE_INTERRUPTION_DETAILS:
        return name
    return "Exception"


def _verify_partial_interrupted_round(
    round_dir: Path,
    plan: CampaignPlan,
    *,
    round_index: int,
    interruption: dict[str, Any],
) -> None:
    if int(interruption.get("roundIndex", -1)) != round_index:
        raise R803EvaluationError("interruption_round_index_mismatch")
    if not round_dir.is_dir() or not any(round_dir.iterdir()):
        raise R803EvaluationError(f"terminal_missing_partial_round:{round_index}")
    if _round_is_complete(round_dir):
        raise R803EvaluationError(
            f"terminal_partial_round_unexpectedly_complete:{round_index}"
        )
    start_path = round_dir / "round-start.json"
    companion = round_dir / "round-start.sha256.json"
    if not start_path.is_file():
        raise R803EvaluationError(f"terminal_partial_missing_round_start:{round_index}")
    if not companion.is_file():
        raise R803EvaluationError(
            f"terminal_partial_missing_round_start_companion:{round_index}"
        )
    start = json.loads(start_path.read_text(encoding="utf-8"))
    if start.get("schemaVersion") != ROUND_START_SCHEMA_VERSION:
        raise R803EvaluationError("unsupported_round_start_schema")
    if int(start.get("roundIndex", -1)) != round_index:
        raise R803EvaluationError("partial_round_start_index_mismatch")
    if (
        start.get("packageSha256") != plan.package_sha256
        or start.get("thresholdSha256") != plan.threshold_sha256
        or start.get("planSha256") != plan.plan_sha256
        or start.get("scorerVersion") != plan.scorer_version
        or start.get("scorerImplementationSha256") != plan.scorer_implementation_sha256
        or start.get("quickPromptBindingSha256") != plan.quick_prompt_binding_sha256
        or start.get("researchPromptBindingSha256")
        != plan.research_prompt_binding_sha256
        or start.get("evaluatorClosureSha256") != plan.evaluator_closure_sha256
    ):
        raise R803EvaluationError("partial_round_start_plan_hash_drift")
    companion_doc = json.loads(companion.read_text(encoding="utf-8"))
    if companion_doc.get("sha256") != file_sha256(start_path):
        raise R803EvaluationError("partial_round_start_companion_hash_drift")

    stored_hashes = interruption.get("partialRoundFileHashes")
    if not isinstance(stored_hashes, dict) or not stored_hashes:
        raise R803EvaluationError("interruption_partial_file_hashes_missing")
    if not all(
        isinstance(name, str) and isinstance(digest, str) and len(digest) == 64
        for name, digest in stored_hashes.items()
    ):
        raise R803EvaluationError("interruption_partial_file_hashes_invalid")
    actual_hashes = _partial_round_file_hashes(round_dir)
    if set(actual_hashes) != set(stored_hashes):
        raise R803EvaluationError("partial_round_file_set_drift")
    for name, digest in actual_hashes.items():
        if stored_hashes.get(name) != digest:
            raise R803EvaluationError(f"partial_round_file_hash_drift:{name}")
    closure_sha256 = canonical_sha256(actual_hashes)
    if interruption.get("partialRoundClosureSha256") != closure_sha256:
        raise R803EvaluationError("partial_round_closure_hash_drift")

    # Interruption provenance must match the frozen plan.
    for key in (
        "packageSha256",
        "thresholdSha256",
        "planSha256",
        "scorerVersion",
        "scorerImplementationSha256",
        "quickPromptBindingSha256",
        "researchPromptBindingSha256",
        "evaluatorClosureSha256",
    ):
        expected = {
            "packageSha256": plan.package_sha256,
            "thresholdSha256": plan.threshold_sha256,
            "planSha256": plan.plan_sha256,
            "scorerVersion": plan.scorer_version,
            "scorerImplementationSha256": plan.scorer_implementation_sha256,
            "quickPromptBindingSha256": plan.quick_prompt_binding_sha256,
            "researchPromptBindingSha256": plan.research_prompt_binding_sha256,
            "evaluatorClosureSha256": plan.evaluator_closure_sha256,
        }[key]
        if interruption.get(key) != expected:
            raise R803EvaluationError(f"interruption_plan_hash_drift:{key}")
    if interruption.get("partialRoundPreserved") is not True:
        raise R803EvaluationError("interruption_partial_not_preserved")


def _recompute_and_verify_terminal(
    campaign_dir: Path,
    plan: CampaignPlan,
    stored: dict[str, Any],
) -> dict[str, Any]:
    companion = campaign_dir / "campaign-report.sha256.json"
    if not companion.is_file():
        raise R803EvaluationError("missing_campaign_report_companion")
    companion_doc = json.loads(companion.read_text(encoding="utf-8"))
    report_path = campaign_dir / "campaign-report.json"
    if companion_doc.get("sha256") != file_sha256(report_path):
        raise R803EvaluationError("campaign_report_companion_hash_drift")

    claimed = int(stored.get("sample", {}).get("completedRounds", -1))
    if claimed < 0:
        raise R803EvaluationError("campaign_report_completed_rounds_invalid")

    interruption = stored.get("interruption")
    allowed_partial: int | None = None
    if interruption is not None:
        if not isinstance(interruption, dict):
            raise R803EvaluationError("invalid_interruption_record")
        allowed_partial = int(interruption.get("roundIndex", -1))
        if allowed_partial < 1 or allowed_partial > plan.planned_rounds:
            raise R803EvaluationError("interruption_round_index_invalid")
        if allowed_partial != claimed + 1:
            raise R803EvaluationError("interruption_round_not_contiguous")

    # Validate the full global inventory first so out-of-range/malformed
    # nonempty directories (e.g. round-06) reject terminal resume.
    discovered = _validate_round_inventory(campaign_dir, plan)
    expected_indexes = list(range(1, claimed + 1))
    if allowed_partial is not None:
        expected_indexes.append(allowed_partial)
    actual_indexes = [index for index, _path in discovered]
    if actual_indexes != expected_indexes:
        unexpected = [
            index for index in actual_indexes if index not in expected_indexes
        ]
        if unexpected:
            raise R803EvaluationError(f"terminal_extra_round_directory:{unexpected[0]}")
        missing = [index for index in expected_indexes if index not in actual_indexes]
        if missing:
            raise R803EvaluationError(f"terminal_missing_round:{missing[0]}")
        raise R803EvaluationError("terminal_round_inventory_mismatch")

    rounds: list[dict[str, Any]] = []
    for round_index in range(1, claimed + 1):
        round_dir = campaign_dir / f"round-{round_index:02d}"
        if not round_dir.exists():
            raise R803EvaluationError(f"terminal_missing_round:{round_index}")
        rounds.append(_load_existing_round(round_dir, plan, round_index))

    if allowed_partial is not None:
        assert interruption is not None  # for type checkers
        partial_dir = campaign_dir / f"round-{allowed_partial:02d}"
        _verify_partial_interrupted_round(
            partial_dir,
            plan,
            round_index=allowed_partial,
            interruption=interruption,
        )

    recomputed = build_campaign_report(
        plan,
        campaign_dir=campaign_dir,
        rounds=rounds,
        interruption=interruption,
    )
    # Canonical equality against stored terminal report body.
    if recomputed != stored:
        raise R803EvaluationError("campaign_report_recompute_mismatch")
    if len(stored.get("rounds", [])) != claimed:
        raise R803EvaluationError("campaign_report_round_entry_count_mismatch")
    for index, item in enumerate(stored.get("rounds", []), start=1):
        if item.get("roundIndex") != index:
            raise R803EvaluationError("campaign_report_round_entry_order_mismatch")
        if item.get("roundReportSha256") != rounds[index - 1].get("roundReportSha256"):
            raise R803EvaluationError("campaign_report_round_hash_mismatch")
    return stored


def _load_terminal_campaign_report(
    campaign_dir: Path, plan: CampaignPlan
) -> dict[str, Any] | None:
    report_path = campaign_dir / "campaign-report.json"
    if not report_path.is_file():
        return None
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schemaVersion") != CAMPAIGN_SCHEMA_VERSION:
        raise R803EvaluationError("unsupported_campaign_report_schema")
    if report.get("status") not in {"completed", "failed"}:
        raise R803EvaluationError("campaign_report_not_terminal")
    package = report.get("package") or {}
    if (
        package.get("sha256") != plan.package_sha256
        or package.get("thresholdSha256") != plan.threshold_sha256
        or package.get("planSha256") != plan.plan_sha256
        or package.get("scorerVersion") != plan.scorer_version
        or package.get("scorerImplementationSha256")
        != plan.scorer_implementation_sha256
        or package.get("quickPromptBindingSha256") != plan.quick_prompt_binding_sha256
        or package.get("researchPromptBindingSha256")
        != plan.research_prompt_binding_sha256
        or package.get("evaluatorClosureSha256") != plan.evaluator_closure_sha256
    ):
        raise R803EvaluationError("campaign_report_plan_hash_drift")
    return _recompute_and_verify_terminal(campaign_dir, plan, report)


def _freeze_interruption(
    campaign_dir: Path,
    plan: CampaignPlan,
    rounds: list[dict[str, Any]],
    *,
    round_index: int,
    reason: str,
    detail: str,
    error: BaseException | None = None,
) -> dict[str, Any]:
    safe_detail = _safe_interruption_detail(detail if error is None else reason, error)
    partial_dir = campaign_dir / f"round-{round_index:02d}"
    partial_hashes = _partial_round_file_hashes(partial_dir)
    interruption = {
        "roundIndex": round_index,
        "reason": reason,
        "detail": safe_detail,
        "partialRoundPreserved": True,
        "partialRoundFileHashes": partial_hashes,
        "partialRoundClosureSha256": canonical_sha256(partial_hashes),
        "packageSha256": plan.package_sha256,
        "thresholdSha256": plan.threshold_sha256,
        "planSha256": plan.plan_sha256,
        "scorerVersion": plan.scorer_version,
        "scorerImplementationSha256": plan.scorer_implementation_sha256,
        "quickPromptBindingSha256": plan.quick_prompt_binding_sha256,
        "researchPromptBindingSha256": plan.research_prompt_binding_sha256,
        "evaluatorClosureSha256": plan.evaluator_closure_sha256,
        "recordedAt": datetime.now(UTC).isoformat(),
    }
    # Fail closed before minting terminal evidence: existing incomplete rounds must
    # already carry a plan-matching start marker + companion. Exception-path freezes
    # after run_campaign_round wrote the marker; resume freezes of pre-existing
    # partials must not emit a terminal that only fails on next resume.
    _verify_partial_interrupted_round(
        partial_dir,
        plan,
        round_index=round_index,
        interruption=interruption,
    )
    report = build_campaign_report(
        plan,
        campaign_dir=campaign_dir,
        rounds=rounds,
        interruption=interruption,
    )
    _write_terminal_campaign_report(campaign_dir, report)
    return report


def _scan_existing_rounds(
    campaign_dir: Path,
    plan: CampaignPlan,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Load contiguous complete rounds; freeze on incomplete started round.

    Global nonempty round inventory is validated first so gaps, out-of-range
    directories (e.g. round-06), and post-partial leftovers are rejected before
    any interruption freeze or provider configuration.
    """
    discovered = _validate_round_inventory(campaign_dir, plan)
    rounds: list[dict[str, Any]] = []
    for position, (round_index, round_dir) in enumerate(discovered):
        if _round_is_complete(round_dir):
            report = _load_existing_round(round_dir, plan, round_index)
            rounds.append(report)
            if report["stop"]["freezeCampaign"]:
                # No nonempty later rounds after a freeze (inventory already contiguous,
                # so any later entry is a violation).
                if position + 1 < len(discovered):
                    later_index = discovered[position + 1][0]
                    raise R803EvaluationError(
                        f"round_order_violation:after_freeze_{later_index}"
                    )
                break
            continue
        # Started but incomplete: freeze terminal engineering fail; never reuse.
        if _round_is_started(round_dir):
            if position + 1 < len(discovered):
                later_index = discovered[position + 1][0]
                raise R803EvaluationError(
                    f"round_order_violation:after_partial_{later_index}"
                )
            return rounds, {
                "roundIndex": round_index,
                "reason": "round_incomplete",
                "detail": "started_or_partial_round_not_closed",
            }
        raise R803EvaluationError(f"round_directory_invalid_state:{round_index}")
    return rounds, None
