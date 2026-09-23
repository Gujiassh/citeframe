from __future__ import annotations

from pathlib import Path
from typing import Any
from citeframe_evaluation.paired import configured_provider
from citeframe_evaluation.contracts import EvaluationPackage, R803EvaluationError
from citeframe_evaluation.provider import RecordedProvider
from citeframe_evaluation.campaign.plan import (
    _verify_campaign_plan_file,
    freeze_campaign_plan,
)
from citeframe_evaluation.campaign.recovery import (
    _freeze_interruption,
    _load_terminal_campaign_report,
    _scan_existing_rounds,
)
from citeframe_evaluation.campaign.reporting import build_campaign_report
from citeframe_evaluation.campaign.rounds import (
    _formal_configured_attestation,
    _run_campaign_round_with_attestation,
    run_campaign_round,
)
from citeframe_evaluation.campaign.storage import (
    _validate_round_inventory,
    _write_immutable_json,
    _write_progress_snapshot,
    _write_terminal_campaign_report,
)


def run_or_resume_campaign(
    *,
    campaign_dir: Path,
    provider: RecordedProvider | None = None,
    package: EvaluationPackage | None = None,
    max_new_rounds: int | None = None,
    baseline_evaluation_run_id: str | None = None,
    allow_test_provider: bool = False,
) -> dict[str, Any]:
    if max_new_rounds is not None and max_new_rounds < 0:
        raise R803EvaluationError("max_new_rounds_must_be_non_negative")

    plan = freeze_campaign_plan(package)
    campaign_dir.mkdir(parents=True, exist_ok=True)
    plan_path = campaign_dir / "campaign-plan.json"
    if plan_path.exists():
        _verify_campaign_plan_file(plan_path, plan)
    else:
        digest = _write_immutable_json(plan_path, plan.plan_document)
        _write_immutable_json(
            campaign_dir / "campaign-plan.sha256.json", {"sha256": digest}
        )

    terminal = _load_terminal_campaign_report(campaign_dir, plan)
    if terminal is not None:
        return terminal

    # Verify existing evidence first; do not configure/instantiate a provider yet.
    rounds, incomplete = _scan_existing_rounds(campaign_dir, plan)
    if incomplete is not None:
        return _freeze_interruption(
            campaign_dir,
            plan,
            rounds,
            round_index=int(incomplete["roundIndex"]),
            reason=str(incomplete["reason"]),
            detail=str(incomplete["detail"]),
        )

    campaign_report = build_campaign_report(
        plan, campaign_dir=campaign_dir, rounds=rounds
    )
    if campaign_report["status"] in {"completed", "failed"}:
        _write_terminal_campaign_report(campaign_dir, campaign_report)
        return campaign_report

    remaining_new = plan.planned_rounds if max_new_rounds is None else max_new_rounds
    if remaining_new == 0 or (rounds and rounds[-1]["stop"]["freezeCampaign"]):
        _write_progress_snapshot(campaign_dir, campaign_report)
        return campaign_report

    # Provider only immediately before a new formal/test round.
    # Formal evidence: only provider=None may call configured_provider().
    # Any explicit provider argument requires allow_test_provider=True and is non-formal.
    if provider is not None:
        if not allow_test_provider:
            raise R803EvaluationError("injected_provider_requires_allow_test_provider")
        active_provider = provider
        formal_attestation = None
    else:
        if allow_test_provider:
            raise R803EvaluationError("allow_test_provider_requires_injected_provider")
        active_provider = configured_provider(plan.package)
        formal_attestation = _formal_configured_attestation(plan, active_provider)

    next_round_index = len(rounds) + 1
    while next_round_index <= plan.planned_rounds and remaining_new > 0:
        if rounds and rounds[-1]["stop"]["freezeCampaign"]:
            break
        # Re-validate inventory each iteration before any new work.
        _validate_round_inventory(campaign_dir, plan)
        for later in range(next_round_index + 1, plan.planned_rounds + 1):
            later_dir = campaign_dir / f"round-{later:02d}"
            if later_dir.exists() and any(later_dir.iterdir()):
                raise R803EvaluationError("round_order_violation")
        round_dir = campaign_dir / f"round-{next_round_index:02d}"
        try:
            if formal_attestation is not None:
                result = _run_campaign_round_with_attestation(
                    plan,
                    round_index=next_round_index,
                    provider=active_provider,
                    output_dir=round_dir,
                    baseline_evaluation_run_id=baseline_evaluation_run_id,
                    attestation=formal_attestation,
                )
            else:
                result = run_campaign_round(
                    plan,
                    round_index=next_round_index,
                    provider=active_provider,
                    output_dir=round_dir,
                    baseline_evaluation_run_id=baseline_evaluation_run_id,
                    allow_test_provider=True,
                )
        except Exception as error:  # noqa: BLE001 - freeze incomplete formal round
            # Do not delete/replace the partial round; freeze terminal engineering fail.
            return _freeze_interruption(
                campaign_dir,
                plan,
                rounds,
                round_index=next_round_index,
                reason="round_execution_exception",
                detail="round_execution_exception",
                error=error,
            )
        report = result["roundReport"]
        rounds.append(report)
        remaining_new -= 1
        next_round_index += 1
        if report["stop"]["freezeCampaign"]:
            break

    campaign_report = build_campaign_report(
        plan, campaign_dir=campaign_dir, rounds=rounds
    )
    if campaign_report["status"] in {"completed", "failed"}:
        _write_terminal_campaign_report(campaign_dir, campaign_report)
    else:
        _write_progress_snapshot(campaign_dir, campaign_report)
    return campaign_report
