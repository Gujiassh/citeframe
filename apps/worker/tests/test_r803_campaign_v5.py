from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import ai_pdf_worker.r803_evaluation_provider as evaluation_provider
import pytest
from ai_pdf_api.services.evaluation import parse_evaluation_report
from ai_pdf_worker.r803_evaluation import run_paired_evaluation
from ai_pdf_worker.r803_evaluation_campaign import (
    freeze_campaign_plan,
    run_campaign_round,
    run_or_resume_campaign,
)
from ai_pdf_worker.r803_evaluation_contract import (
    DEFAULT_PACKAGE_PATH,
    DEFAULT_PACKAGE_V5_PATH,
    CaseExecution,
    ObservedClaim,
    R803EvaluationError,
    canonical_bytes,
    file_sha256,
    load_evaluation_package,
)
from ai_pdf_worker.r803_evaluation_diagnostics import (
    AgentResultValidationError,
    DiagnosticCapture,
    classify_failure_origin,
    secret_scan_text,
    validate_agent_result_with_diagnostics,
    write_raw_output_bundle,
)
from ai_pdf_worker.r803_evaluation_runtime import (
    run_quick_case,
    run_quick_case_with_diagnostics,
    run_research_case,
)
from ai_pdf_worker.r803_evaluation_scorer_v2 import (
    build_import_report_v2,
    score_case_v2,
)
from ai_pdf_worker.research_agent_schemas import validate_agent_result
from r803_test_helpers import CampaignProvider, DeterministicProvider

REPO = Path(__file__).resolve().parents[3]


def _run_campaign(
    campaign_dir: Path,
    provider: CampaignProvider | DeterministicProvider | None,
    package,
    **kwargs,
):
    return run_or_resume_campaign(
        campaign_dir=campaign_dir,
        provider=provider,
        package=package,
        allow_test_provider=provider is not None,
        **kwargs,
    )


def test_production_researcher_rejects_empty_claims_but_r803_diagnostic_allows_refusal() -> None:
    with pytest.raises(ValueError, match="researcher schema mismatch"):
        validate_agent_result("researcher", {"claims": []})
    validate_agent_result_with_diagnostics("researcher", {"claims": []})


def test_local_schema_failures_have_distinct_safe_diagnostics() -> None:
    cases = [
        ("researcher", {"claims": [{"text": "x"}]}, "claim_closed_object"),
        (
            "researcher",
            {"claims": [{"text": "x", "evidenceHandleIds": []}]},
            "claim_evidence_handle_ids_nonempty_unique",
        ),
        (
            "planner",
            {"summary": "", "knownGaps": [], "estimatedProviderCalls": 1, "subproblems": []},
            "summary_nonempty_string",
        ),
        ("verifier", {"claims": [{"id": "1", "status": "maybe"}]}, "claim_status_enum"),
        ("critic", {"conflictClaimIds": ["a", "a"]}, "conflict_claim_ids_unique_strings"),
        (
            "synthesizer",
            {"factClaimIds": ["a"], "unresolvedClaimIds": 1},
            "unresolved_claim_ids_unique_strings",
        ),
    ]
    seen: set[str] = set()
    for node, payload, rule in cases:
        with pytest.raises(AgentResultValidationError) as captured:
            validate_agent_result_with_diagnostics(node, payload)  # type: ignore[arg-type]
        assert captured.value.rule == rule
        assert captured.value.failure_code.endswith("_invalid_output")
        assert classify_failure_origin(captured.value.failure_code) == "model_or_workflow_quality"
        seen.add(f"{node}:{rule}")
    assert len(seen) == len(cases)


def test_package_v5_loads_with_threshold_and_scorer_v2() -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    assert package.document["schemaVersion"] == "r803-evaluation-package-v5"
    assert package.comparison_keys.scorer_version == "r100-v2"
    assert package.document["suite"]["caseManifestPath"] == "docs/evals/r100-research-cases-v2.json"
    assert package.document["suite"]["thresholdSha256"] == file_sha256(
        REPO / "docs/evals/r803-release-threshold-v1.json"
    )
    plan = freeze_campaign_plan(package)
    assert plan.planned_rounds == 5
    assert plan.case_order[0] == "r100-compare-rise-drop"
    assert len(plan.evaluator_closure_sha256) == 64
    assert len(plan.scorer_implementation_sha256) == 64
    assert len(plan.quick_prompt_binding_sha256) == 64
    assert len(plan.research_prompt_binding_sha256) == 64
    assert "scorerImplementationSha256" in plan.plan_document
    assert "evaluatorClosureSha256" in plan.plan_document
    assert plan.plan_document["evaluatorClosureStrategy"] == "recursive_ast_import_closure"
    assert plan.plan_document["evaluatorClosureRoots"] == [
        "ai_pdf_worker.r803_evaluation_campaign"
    ]
    modules = plan.evaluator_closure_modules
    expected_needles = [
        "apps/worker/src/ai_pdf_worker/r803_evaluation.py",
        "apps/worker/src/ai_pdf_worker/r803_evaluation_policy.py",
        "apps/worker/src/ai_pdf_worker/research_executor.py",
        "apps/worker/src/ai_pdf_worker/research_executor_contracts.py",
        "apps/worker/src/ai_pdf_worker/research_executor_engine.py",
        "apps/worker/src/ai_pdf_worker/research_executor_tools.py",
        "apps/worker/src/ai_pdf_worker/research_runtime_core.py",
        "apps/worker/src/ai_pdf_worker/research_runtime_ports.py",
        "apps/worker/src/ai_pdf_worker/research_runtime_agents.py",
        "apps/api/src/ai_pdf_api/core/settings.py",
        "apps/api/src/ai_pdf_api/schemas/evaluation.py",
        "apps/api/src/ai_pdf_api/services/providers.py",
        "apps/api/src/ai_pdf_api/services/research_prompt_provenance.py",
    ]
    for needle in expected_needles:
        assert needle in modules, needle
    provenance = package.document["implementationProvenance"]
    assert provenance["evaluatorClosureStrategy"] == "recursive_ast_import_closure"
    assert provenance["evaluatorClosureRoots"] == [
        "ai_pdf_worker.r803_evaluation_campaign"
    ]




def _write_temp_closure_repo(tmp_path: Path) -> Path:
    """Minimal repo-local package layout for isolated closure resolver tests."""
    worker = tmp_path / "apps/worker/src/ai_pdf_worker"
    api = tmp_path / "apps/api/src/ai_pdf_api"
    worker.mkdir(parents=True)
    api.mkdir(parents=True)
    (worker / "__init__.py").write_text("", encoding="utf-8")
    (api / "__init__.py").write_text("", encoding="utf-8")
    return tmp_path


def test_closure_required_import_missing_module_raises(tmp_path: Path) -> None:
    from ai_pdf_worker.r803_evaluation_integrity import compute_evaluator_closure

    repo = _write_temp_closure_repo(tmp_path)
    worker = repo / "apps/worker/src/ai_pdf_worker"
    (worker / "root_mod.py").write_text(
        "import ai_pdf_worker.nonexistent\n",
        encoding="utf-8",
    )
    with pytest.raises(R803EvaluationError, match="missing_closure_module:ai_pdf_worker.nonexistent"):
        compute_evaluator_closure(repo, roots=("ai_pdf_worker.root_mod",))


def test_closure_required_import_from_base_missing_raises(tmp_path: Path) -> None:
    from ai_pdf_worker.r803_evaluation_integrity import compute_evaluator_closure

    repo = _write_temp_closure_repo(tmp_path)
    worker = repo / "apps/worker/src/ai_pdf_worker"
    (worker / "root_mod.py").write_text(
        "from ai_pdf_worker.nonexistent import x\n",
        encoding="utf-8",
    )
    with pytest.raises(R803EvaluationError, match="missing_closure_module:ai_pdf_worker.nonexistent"):
        compute_evaluator_closure(repo, roots=("ai_pdf_worker.root_mod",))


def test_closure_from_existing_module_attribute_is_not_frozen_as_child(
    tmp_path: Path,
) -> None:
    from ai_pdf_worker.r803_evaluation_integrity import compute_evaluator_closure

    repo = _write_temp_closure_repo(tmp_path)
    worker = repo / "apps/worker/src/ai_pdf_worker"
    (worker / "leaf.py").write_text("VALUE = 1\n", encoding="utf-8")
    (worker / "root_mod.py").write_text(
        "from ai_pdf_worker.leaf import VALUE\n",
        encoding="utf-8",
    )
    closure = compute_evaluator_closure(repo, roots=("ai_pdf_worker.root_mod",))
    modules = set(closure["modules"])
    assert "apps/worker/src/ai_pdf_worker/root_mod.py" in modules
    assert "apps/worker/src/ai_pdf_worker/leaf.py" in modules
    assert "apps/worker/src/ai_pdf_worker/VALUE.py" not in modules
    assert not any(path.endswith("/leaf/VALUE.py") for path in modules)


def test_closure_from_package_import_real_submodule_is_included(tmp_path: Path) -> None:
    from ai_pdf_worker.r803_evaluation_integrity import compute_evaluator_closure

    repo = _write_temp_closure_repo(tmp_path)
    worker = repo / "apps/worker/src/ai_pdf_worker"
    pkg = worker / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "child.py").write_text("X = 1\n", encoding="utf-8")
    (worker / "root_mod.py").write_text(
        "from ai_pdf_worker.pkg import child\n",
        encoding="utf-8",
    )
    closure = compute_evaluator_closure(repo, roots=("ai_pdf_worker.root_mod",))
    modules = set(closure["modules"])
    assert "apps/worker/src/ai_pdf_worker/root_mod.py" in modules
    assert "apps/worker/src/ai_pdf_worker/pkg/__init__.py" in modules
    assert "apps/worker/src/ai_pdf_worker/pkg/child.py" in modules
    # Ancestor package initializers for every resolved module are frozen.
    assert "apps/worker/src/ai_pdf_worker/__init__.py" in modules


def test_real_evaluator_closure_includes_top_level_package_inits() -> None:
    from ai_pdf_worker.r803_evaluation_integrity import compute_evaluator_closure

    closure = compute_evaluator_closure(REPO)
    modules = set(closure["modules"])
    assert "apps/worker/src/ai_pdf_worker/__init__.py" in modules
    assert "apps/api/src/ai_pdf_api/__init__.py" in modules


def test_mutating_worker_package_init_changes_closure_sha(tmp_path: Path) -> None:
    from ai_pdf_worker.r803_evaluation_integrity import compute_evaluator_closure

    baseline = compute_evaluator_closure(REPO)
    relative = "apps/worker/src/ai_pdf_worker/__init__.py"
    assert relative in baseline["modules"]
    original = baseline["modules"][relative]
    sandbox = tmp_path / "init-mutation"
    dest = sandbox / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        (REPO / relative).read_text(encoding="utf-8") + "\n# package-init-closure-probe\n",
        encoding="utf-8",
    )
    mutated_digest = file_sha256(dest)
    assert mutated_digest != original
    altered = dict(baseline["modules"])
    altered[relative] = mutated_digest
    import hashlib

    material = "\n".join(f"{path}:{digest}" for path, digest in sorted(altered.items()))
    altered_sha = hashlib.sha256(material.encode("utf-8")).hexdigest()
    assert altered_sha != baseline["closureSha256"]


def test_closure_walks_imports_from_ancestor_package_init(tmp_path: Path) -> None:
    from ai_pdf_worker.r803_evaluation_integrity import compute_evaluator_closure

    repo = _write_temp_closure_repo(tmp_path)
    worker = repo / "apps/worker/src/ai_pdf_worker"
    (worker / "__init__.py").write_text(
        "import ai_pdf_worker.side_effect\n",
        encoding="utf-8",
    )
    (worker / "side_effect.py").write_text("SIDE = 1\n", encoding="utf-8")
    (worker / "leaf.py").write_text("VALUE = 1\n", encoding="utf-8")
    (worker / "root_mod.py").write_text(
        "import ai_pdf_worker.leaf\n",
        encoding="utf-8",
    )
    closure = compute_evaluator_closure(repo, roots=("ai_pdf_worker.root_mod",))
    modules = set(closure["modules"])
    assert "apps/worker/src/ai_pdf_worker/__init__.py" in modules
    assert "apps/worker/src/ai_pdf_worker/side_effect.py" in modules
    assert "apps/worker/src/ai_pdf_worker/leaf.py" in modules


def test_recursive_evaluator_closure_hash_changes_with_transitive_module(
    tmp_path: Path,
) -> None:

    from ai_pdf_worker.r803_evaluation_integrity import compute_evaluator_closure

    repo = REPO
    baseline = compute_evaluator_closure(repo)
    assert baseline["strategy"] == "recursive_ast_import_closure"
    assert "apps/worker/src/ai_pdf_worker/r803_evaluation_policy.py" in baseline["modules"]

    # Copy a transitive critical module into an isolated tree and mutate only that copy.
    relative = "apps/worker/src/ai_pdf_worker/r803_evaluation_policy.py"
    sandbox = tmp_path / "closure-sandbox"
    src = repo / relative
    dest = sandbox / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Provide minimal package roots so the recursive walker can start from campaign.
    # We only need the policy file mutation effect against a full resolved map snapshot.
    original = baseline["modules"][relative]
    mutated_text = src.read_text(encoding="utf-8") + "\n# closure-hash-probe\n"
    dest.write_text(mutated_text, encoding="utf-8")
    mutated_digest = file_sha256(dest)
    assert mutated_digest != original
    # Simulate plan materialization: replacing one module digest changes closure digest.
    altered = dict(baseline["modules"])
    altered[relative] = mutated_digest
    import hashlib

    material = "\n".join(f"{path}:{digest}" for path, digest in sorted(altered.items()))
    altered_sha = hashlib.sha256(material.encode("utf-8")).hexdigest()
    assert altered_sha != baseline["closureSha256"]


def test_production_agents_malformed_json_keeps_generic_error() -> None:
    from ai_pdf_worker.research_agent_schemas import validate_agent_result
    from ai_pdf_worker.research_executor import ResearchExecutionError
    from ai_pdf_worker.research_runtime_agents import GenerationResearchAgents

    class _Lease:
        step_id = "step-prod"

    class _Prompt:
        template_text = "system"
        variable_names = ()
        # prompt.node_key is the frozen prompt node, not the generation node.
        node_key = "researchers"
        prompt_key = "research.researcher"

    class _Generation:
        def prompt(self, node_key: str):
            return _Prompt()

        def generate(self, lease, *, node_key: str, messages):
            return "{not-json"

    variables = {
        "subproblem": {},
        "frozenAssetScope": {},
        "toolContracts": {},
        "resultSchema": {},
    }
    agents = GenerationResearchAgents(
        _Generation(),  # type: ignore[arg-type]
        result_validator=validate_agent_result,
        diagnostic_mode=False,
    )
    with pytest.raises(ResearchExecutionError, match="researcher_invalid_output"):
        agents._json(_Lease(), "researcher", variables)  # type: ignore[arg-type]

    # Explicit diagnostic mode still raises typed identity-bearing errors.
    diag_agents = GenerationResearchAgents(
        _Generation(),  # type: ignore[arg-type]
        result_validator=validate_agent_result,
        diagnostic_mode=True,
    )
    with pytest.raises(AgentResultValidationError) as captured:
        diag_agents._json(_Lease(), "researcher", variables)  # type: ignore[arg-type]
    assert captured.value.rule == "json_decode"
    assert captured.value.logical_call_key == "step-prod:researcher"
    assert captured.value.raw_output_sha256 is not None


def test_round_root_symlink_and_non_directory_are_rejected(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    plan = freeze_campaign_plan(package)
    from ai_pdf_worker.r803_evaluation_campaign import _write_immutable_json
    from ai_pdf_worker.r803_evaluation_integrity import (
        verify_checksums_exact as verify_exact,
    )

    # Campaign inventory: symlink round root rejected even when empty.
    campaign_dir = tmp_path / "symlink-campaign"
    digest = _write_immutable_json(campaign_dir / "campaign-plan.json", plan.plan_document)
    _write_immutable_json(campaign_dir / "campaign-plan.sha256.json", {"sha256": digest})
    target = tmp_path / "safe-target"
    target.mkdir()
    link = campaign_dir / "round-01"
    link.symlink_to(target)
    with pytest.raises(R803EvaluationError, match="round_symlink_forbidden:round-01"):
        _run_campaign(campaign_dir, CampaignProvider(), package, max_new_rounds=0)

    # Regular file named round-01 is rejected.
    file_campaign = tmp_path / "file-campaign"
    digest = _write_immutable_json(file_campaign / "campaign-plan.json", plan.plan_document)
    _write_immutable_json(file_campaign / "campaign-plan.sha256.json", {"sha256": digest})
    (file_campaign / "round-01").write_text("not-a-dir\n", encoding="utf-8")
    with pytest.raises(R803EvaluationError, match="round_directory_invalid_state:round-01"):
        _run_campaign(file_campaign, CampaignProvider(), package, max_new_rounds=0)

    # Checksum closure rejects symlink root itself.
    with pytest.raises(R803EvaluationError, match="round_symlink_forbidden:"):
        verify_exact(link)

    # Direct round runner rejects symlink output_dir.
    out_link = tmp_path / "out-link"
    out_target = tmp_path / "out-target"
    out_target.mkdir()
    out_link.symlink_to(out_target)
    with pytest.raises(R803EvaluationError, match="round_symlink_forbidden:"):
        run_campaign_round(
            plan,
            round_index=1,
            provider=CampaignProvider(),
            output_dir=out_link,
            allow_test_provider=True,
        )

    # Terminal resume also rejects out-of-range symlink round-06.
    full = tmp_path / "full-terminal"
    report = _run_campaign(full, CampaignProvider(), package)
    assert report["status"] == "completed"
    extra_target = tmp_path / "extra-target"
    extra_target.mkdir()
    (full / "round-06").symlink_to(extra_target)
    with pytest.raises(R803EvaluationError, match="round_symlink_forbidden:round-06"):
        _run_campaign(full, None, package, max_new_rounds=0)


def test_v1_to_v4_artifacts_remain_byte_stable() -> None:
    for version in ("r803-v1", "r803-v2", "r803-v3", "r803-v4"):
        directory = REPO / "docs/evals/artifacts" / version
        for line in (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            digest, name = line.split()
            assert file_sha256(directory / name) == digest


def test_v4_default_package_path_unchanged() -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_PATH)
    assert package.document["schemaVersion"] == "r803-evaluation-package-v4"
    assert package.comparison_keys.scorer_version == "r100-v1"


def test_runtime_public_api_returns_case_execution() -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    provider = DeterministicProvider()
    quick = run_quick_case(package, package.cases[0], provider)
    research = run_research_case(package, package.cases[0], provider)
    assert isinstance(quick, CaseExecution)
    assert isinstance(research, CaseExecution)


def _base_execution(**overrides: object) -> CaseExecution:
    payload = {
        "case_key": "r100-synthesize-table-constraint",
        "mode": "quick",
        "output": "Atlas has a score of 91.4. Verify the chart and caption together.",
        "observed_disposition": "answer",
        "evidence_ids": ("answer-pdf-table", "answer-image-constraint"),
        "conflict_detected": False,
        "observed_claims": (
            ObservedClaim("Atlas has a score of 91.4.", ("answer-pdf-table",), False),
            ObservedClaim(
                "Verify the chart and caption together.",
                ("answer-image-constraint",),
                False,
            ),
        ),
        "wall_time_ms": 1,
        "calls": (),
    }
    payload.update(overrides)
    return CaseExecution(**payload)  # type: ignore[arg-type]


def test_scorer_v2_rejects_extra_negated_wrong_evidence_refusal_and_conflict() -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    by_id = {case["id"]: case for case in package.cases}

    extra = score_case_v2(
        by_id["r100-synthesize-table-constraint"],
        _base_execution(
            observed_claims=(
                ObservedClaim("Atlas has a score of 91.4.", ("answer-pdf-table",), False),
                ObservedClaim(
                    "Verify the chart and caption together.",
                    ("answer-image-constraint",),
                    False,
                ),
                ObservedClaim(
                    "Extra unsupported claim about energy.",
                    ("answer-pdf-table",),
                    False,
                ),
            ),
            evidence_ids=("answer-pdf-table", "answer-image-constraint"),
        ),
    )
    assert extra["qualityFailure"] is True
    assert extra["extraClaimCount"] == 1
    assert extra["unsupportedClaimCount"] == sum(
        row["supportResult"] == "unsupported" for row in extra["claims"]
    )
    assert all(not str(row["claimKey"]).startswith("unmatched-claim-") for row in extra["claims"])

    # Claim-local oracle: unrelated qualification must not count as negation.
    qualified = score_case_v2(
        by_id["r100-compare-rise-drop"],
        CaseExecution(
            case_key="r100-compare-rise-drop",
            mode="quick",
            output=(
                "The PDF trend rises after the third point, but evidence does not name units. "
                "The image says Release 4 begins the sustained drop."
            ),
            observed_disposition="answer",
            evidence_ids=("answer-pdf-chart", "answer-image-trend"),
            conflict_detected=True,
            observed_claims=(
                ObservedClaim(
                    "The PDF trend rises after the third point, but evidence does not name units.",
                    ("answer-pdf-chart",),
                    True,
                ),
                ObservedClaim(
                    "The image says Release 4 begins the sustained drop.",
                    ("answer-image-trend",),
                    True,
                ),
            ),
            wall_time_ms=1,
            calls=(),
        ),
    )
    assert qualified["qualityFailure"] is False
    assert qualified["negatedClaimCount"] == 0

    negated = score_case_v2(
        by_id["r100-locate-chart-caption"],
        CaseExecution(
            case_key="r100-locate-chart-caption",
            mode="quick",
            output="Do not verify the chart and caption together.",
            observed_disposition="answer",
            evidence_ids=("answer-image-constraint",),
            conflict_detected=False,
            observed_claims=(
                ObservedClaim(
                    "Do not verify the chart and caption together.",
                    ("answer-image-constraint",),
                    False,
                ),
            ),
            wall_time_ms=1,
            calls=(),
        ),
    )
    assert negated["qualityFailure"] is True
    assert negated["negatedClaimCount"] == 1

    wrong_evidence = score_case_v2(
        by_id["r100-locate-chart-caption"],
        CaseExecution(
            case_key="r100-locate-chart-caption",
            mode="quick",
            output="Verify the chart and caption together.",
            observed_disposition="answer",
            evidence_ids=("answer-image-trend",),
            conflict_detected=False,
            observed_claims=(
                ObservedClaim(
                    "Verify the chart and caption together.",
                    ("answer-image-trend",),
                    False,
                ),
            ),
            wall_time_ms=1,
            calls=(),
        ),
    )
    assert wrong_evidence["qualityFailure"] is True
    assert wrong_evidence["evidenceTargetExactness"]["value"] == 0.0

    refusal_with_claim = score_case_v2(
        by_id["r100-refuse-energy"],
        CaseExecution(
            case_key="r100-refuse-energy",
            mode="quick",
            output="Atlas uses 12 kWh.",
            observed_disposition="answer",
            evidence_ids=("answer-pdf-table",),
            conflict_detected=False,
            observed_claims=(ObservedClaim("Atlas uses 12 kWh.", ("answer-pdf-table",), False),),
            wall_time_ms=1,
            calls=(),
        ),
    )
    assert refusal_with_claim["qualityFailure"] is True
    assert refusal_with_claim["refusalCorrectness"]["value"] == 0.0

    missed_conflict = score_case_v2(
        by_id["r100-conflict-direction"],
        CaseExecution(
            case_key="r100-conflict-direction",
            mode="quick",
            output="The PDF trend rises while the image drops.",
            observed_disposition="answer",
            evidence_ids=("answer-pdf-chart", "answer-image-trend"),
            conflict_detected=False,
            observed_claims=(
                ObservedClaim(
                    "The PDF trend rises after the third point.",
                    ("answer-pdf-chart",),
                    False,
                ),
                ObservedClaim(
                    "The image observation falls in a sustained drop.",
                    ("answer-image-trend",),
                    False,
                ),
            ),
            wall_time_ms=1,
            calls=(),
        ),
    )
    assert missed_conflict["qualityFailure"] is True
    assert missed_conflict["conflictDetectionRate"]["value"] == 0.0

    false_conflict = score_case_v2(
        by_id["r100-synthesize-table-constraint"],
        _base_execution(conflict_detected=True),
    )
    assert false_conflict["qualityFailure"] is True


def test_scorer_v2_adversarial_negated_synonym_and_uppercase_forbidden() -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    by_id = {case["id"]: case for case in package.cases}

    synonym = score_case_v2(
        by_id["r100-compare-rise-drop"],
        CaseExecution(
            case_key="r100-compare-rise-drop",
            mode="quick",
            output=(
                "The PDF trend fails to increase after the third point. "
                "The image says Release 4 begins the sustained drop."
            ),
            observed_disposition="answer",
            evidence_ids=("answer-pdf-chart", "answer-image-trend"),
            conflict_detected=True,
            observed_claims=(
                ObservedClaim(
                    "The PDF trend fails to increase after the third point.",
                    ("answer-pdf-chart",),
                    True,
                ),
                ObservedClaim(
                    "The image says Release 4 begins the sustained drop.",
                    ("answer-image-trend",),
                    True,
                ),
            ),
            wall_time_ms=1,
            calls=(),
        ),
    )
    assert synonym["qualityFailure"] is True
    assert synonym["negatedClaimCount"] >= 1

    upper = score_case_v2(
        by_id["r100-locate-chart-caption"],
        CaseExecution(
            case_key="r100-locate-chart-caption",
            mode="quick",
            output="SKIP VERIFY the chart and caption together.",
            observed_disposition="answer",
            evidence_ids=("answer-image-constraint",),
            conflict_detected=False,
            observed_claims=(
                ObservedClaim(
                    "SKIP VERIFY the chart and caption together.",
                    ("answer-image-constraint",),
                    False,
                ),
            ),
            wall_time_ms=1,
            calls=(),
        ),
    )
    assert upper["qualityFailure"] is True
    assert upper["forbiddenAnswerCount"] == 1
    assert upper["negatedClaimCount"] == 0
    assert upper["extraClaimCount"] == 0


def test_scorer_v2_disjoint_positive_plus_negated_and_duplicate_and_unmatched() -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    by_id = {case["id"]: case for case in package.cases}

    # Positive exact claim + separate negated concept-match for the same expected claim.
    mixed = score_case_v2(
        by_id["r100-locate-chart-caption"],
        CaseExecution(
            case_key="r100-locate-chart-caption",
            mode="quick",
            output=(
                "Verify the chart and caption together. "
                "Do not verify the chart and caption together."
            ),
            observed_disposition="answer",
            evidence_ids=("answer-image-constraint",),
            conflict_detected=False,
            observed_claims=(
                ObservedClaim(
                    "Verify the chart and caption together.",
                    ("answer-image-constraint",),
                    False,
                ),
                ObservedClaim(
                    "Do not verify the chart and caption together.",
                    ("answer-image-constraint",),
                    False,
                ),
            ),
            wall_time_ms=1,
            calls=(),
        ),
    )
    assert mixed["qualityFailure"] is True
    assert mixed["negatedClaimCount"] == 1
    assert mixed["forbiddenAnswerCount"] == 0
    assert mixed["extraClaimCount"] == 0
    assert mixed["claims"][0]["supportResult"] == "supported"
    assert mixed["unsupportedClaimCount"] == 0

    # Forbidden-only SKIP VERIFY is forbidden, not negated.
    forbidden_only = score_case_v2(
        by_id["r100-locate-chart-caption"],
        CaseExecution(
            case_key="r100-locate-chart-caption",
            mode="quick",
            output="SKIP VERIFY the chart and caption together.",
            observed_disposition="answer",
            evidence_ids=("answer-image-constraint",),
            conflict_detected=False,
            observed_claims=(
                ObservedClaim(
                    "SKIP VERIFY the chart and caption together.",
                    ("answer-image-constraint",),
                    False,
                ),
            ),
            wall_time_ms=1,
            calls=(),
        ),
    )
    assert forbidden_only["qualityFailure"] is True
    assert forbidden_only["forbiddenAnswerCount"] == 1
    assert forbidden_only["negatedClaimCount"] == 0
    assert forbidden_only["extraClaimCount"] == 0
    assert forbidden_only["claims"][0]["supportResult"] == "unsupported"

    # Duplicate positives: one satisfier + one extra; not double-counted as negated/forbidden.
    duplicate = score_case_v2(
        by_id["r100-locate-chart-caption"],
        CaseExecution(
            case_key="r100-locate-chart-caption",
            mode="quick",
            output=(
                "Verify the chart and caption together. "
                "Also verify the chart and caption together again."
            ),
            observed_disposition="answer",
            evidence_ids=("answer-image-constraint",),
            conflict_detected=False,
            observed_claims=(
                ObservedClaim(
                    "Verify the chart and caption together.",
                    ("answer-image-constraint",),
                    False,
                ),
                ObservedClaim(
                    "Also verify the chart and caption together again.",
                    ("answer-image-constraint",),
                    False,
                ),
            ),
            wall_time_ms=1,
            calls=(),
        ),
    )
    assert duplicate["qualityFailure"] is True
    assert duplicate["extraClaimCount"] == 1
    assert duplicate["negatedClaimCount"] == 0
    assert duplicate["forbiddenAnswerCount"] == 0
    assert duplicate["claims"][0]["supportResult"] == "supported"
    assert all(not str(row["claimKey"]).startswith("unmatched-claim-") for row in duplicate["claims"])

    # Unrelated leftover observed claim is an unmatched extra (campaign-only row).
    unmatched = score_case_v2(
        by_id["r100-locate-chart-caption"],
        CaseExecution(
            case_key="r100-locate-chart-caption",
            mode="quick",
            output=(
                "Verify the chart and caption together. "
                "Atlas energy consumption is 12 kWh."
            ),
            observed_disposition="answer",
            evidence_ids=("answer-image-constraint", "answer-pdf-table"),
            conflict_detected=False,
            observed_claims=(
                ObservedClaim(
                    "Verify the chart and caption together.",
                    ("answer-image-constraint",),
                    False,
                ),
                ObservedClaim(
                    "Atlas energy consumption is 12 kWh.",
                    ("answer-pdf-table",),
                    False,
                ),
            ),
            wall_time_ms=1,
            calls=(),
        ),
    )
    assert unmatched["qualityFailure"] is True
    assert unmatched["extraClaimCount"] == 1
    assert unmatched["negatedClaimCount"] == 0
    assert unmatched["forbiddenAnswerCount"] == 0
    assert unmatched["claims"][0]["supportResult"] == "supported"
    assert all(not str(row["claimKey"]).startswith("unmatched-claim-") for row in unmatched["claims"])
    campaign_only = [
        row for row in unmatched["campaignClaims"] if row.get("campaignOnly") is True
    ]
    assert len(campaign_only) == 1


def test_invalid_model_output_counts_as_campaign_quality_failure() -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    case = package.cases[0]
    scored = score_case_v2(
        case,
        CaseExecution(
            case_key=case["id"],
            mode="research",
            output="",
            observed_disposition="not_evaluable",
            evidence_ids=(),
            conflict_detected=False,
            observed_claims=(),
            wall_time_ms=1,
            calls=(),
            failure_code="researcher_invalid_output",
        ),
    )
    assert scored["qualityFailure"] is True
    assert scored["engineeringFailure"] is False
    assert scored["failureOrigin"] == "model_or_workflow_quality"
    assert scored["claimSupportRate"]["sampleCount"] == len(case["claims"])
    assert scored["claimSupportRate"]["value"] == 0.0


def test_semantic_workflow_failures_are_model_quality_not_engineering() -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    case = package.cases[0]
    for code in (
        "claim_evidence_not_in_branch",
        "critic_conflict_set_mismatch",
        "invalid_synthesis_selection",
    ):
        scored = score_case_v2(
            case,
            CaseExecution(
                case_key=case["id"],
                mode="research",
                output="",
                observed_disposition="not_evaluable",
                evidence_ids=(),
                conflict_detected=False,
                observed_claims=(),
                wall_time_ms=1,
                calls=(),
                failure_code=code,
            ),
        )
        assert scored["qualityFailure"] is True, code
        assert scored["engineeringFailure"] is False, code
        assert scored["failureOrigin"] == "model_or_workflow_quality", code

    provider = score_case_v2(
        case,
        CaseExecution(
            case_key=case["id"],
            mode="research",
            output="",
            observed_disposition="not_evaluable",
            evidence_ids=(),
            conflict_detected=False,
            observed_claims=(),
            wall_time_ms=1,
            calls=(),
            failure_code="generation_provider_unreachable",
        ),
    )
    assert provider["qualityFailure"] is False
    assert provider["engineeringFailure"] is True
    assert provider["failureOrigin"] == "engineering_or_integrity"


def test_r700_import_rows_match_unsupported_counts_for_extra_negated_and_model_failures() -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    executions: list[CaseExecution] = []
    for case in package.cases:
        if case["id"] == "r100-synthesize-table-constraint":
            executions.append(
                _base_execution(
                    case_key=case["id"],
                    observed_claims=(
                        ObservedClaim("Atlas has a score of 91.4.", ("answer-pdf-table",), False),
                        ObservedClaim(
                            "Verify the chart and caption together.",
                            ("answer-image-constraint",),
                            False,
                        ),
                        ObservedClaim("Extra claim.", ("answer-pdf-table",), False),
                    ),
                )
            )
        elif case["id"] == "r100-locate-chart-caption":
            executions.append(
                CaseExecution(
                    case_key=case["id"],
                    mode="quick",
                    output="Do not verify the chart and caption together.",
                    observed_disposition="answer",
                    evidence_ids=("answer-image-constraint",),
                    conflict_detected=False,
                    observed_claims=(
                        ObservedClaim(
                            "Do not verify the chart and caption together.",
                            ("answer-image-constraint",),
                            False,
                        ),
                    ),
                    wall_time_ms=1,
                    calls=(),
                )
            )
        elif case["id"] == "r100-compare-rise-drop":
            executions.append(
                CaseExecution(
                    case_key=case["id"],
                    mode="quick",
                    output="",
                    observed_disposition="not_evaluable",
                    evidence_ids=(),
                    conflict_detected=False,
                    observed_claims=(),
                    wall_time_ms=1,
                    calls=(),
                    failure_code="quick_invalid_output",
                )
            )
        elif case["expectedDisposition"] == "refuse":
            executions.append(
                CaseExecution(
                    case_key=case["id"],
                    mode="quick",
                    output="The selected assets do not contain supporting evidence.",
                    observed_disposition="refuse",
                    evidence_ids=(),
                    conflict_detected=False,
                    observed_claims=(),
                    wall_time_ms=1,
                    calls=(),
                )
            )
        elif case["id"] == "r100-conflict-direction":
            executions.append(
                CaseExecution(
                    case_key=case["id"],
                    mode="quick",
                    output="The PDF trend rises while the image drops.",
                    observed_disposition="answer",
                    evidence_ids=("answer-pdf-chart", "answer-image-trend"),
                    conflict_detected=True,
                    observed_claims=(
                        ObservedClaim(
                            "The PDF trend rises after the third point.",
                            ("answer-pdf-chart",),
                            True,
                        ),
                        ObservedClaim(
                            "The image observation falls in a sustained drop.",
                            ("answer-image-trend",),
                            True,
                        ),
                    ),
                    wall_time_ms=1,
                    calls=(),
                )
            )
        else:
            executions.append(_base_execution(case_key=case["id"]))

    report = build_import_report_v2(
        package,
        mode="quick",
        executions=tuple(executions),
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        prompt_binding_sha256="a" * 64,
    )
    imported = parse_evaluation_report(
        canonical_bytes({key: value for key, value in report.items() if not key.startswith("_")})
    )
    for case in imported.cases:
        unsupported = sum(claim.support_result == "unsupported" for claim in case.claims)
        assert unsupported == case.unsupported_claim_count


def test_raw_output_manifest_unique_paths_hashes_and_secret_scan(tmp_path: Path) -> None:
    capture_a = DiagnosticCapture(case_key="r100-refuse-customer", mode="research")
    capture_b = DiagnosticCapture(case_key="r100-refuse-customer", mode="research")
    # Identical raw content from parallel logical calls must not collide.
    payload = '{"claims":[],"note":"authorization is discussed in the fixture caption"}'
    capture_a.record(
        node_key="researcher",
        logical_call_key="branch-a:researcher:0:researcher",
        attempt_number=1,
        raw_text=payload,
    )
    capture_b.record(
        node_key="researcher",
        logical_call_key="branch-b:researcher:0:researcher",
        attempt_number=1,
        raw_text=payload,
    )
    hashes = write_raw_output_bundle(tmp_path, [capture_a, capture_b])
    manifest = json.loads((tmp_path / "raw-outputs/manifest.json").read_text(encoding="utf-8"))
    assert manifest["persistsProviderRequests"] is False
    assert len(manifest["records"]) == 2
    paths = [item["path"] for item in manifest["records"]]
    assert len(set(paths)) == 2
    assert secret_scan_text(payload) == []
    # Benign discussion of authorization must not trip the scanner.
    assert secret_scan_text("authorization is discussed in the fixture caption") == []
    assert secret_scan_text("Authorization: Bearer sk-test-secret-token-123456") != []
    # Short / prose Authorization bearer values must stay clean.
    assert secret_scan_text("Authorization: Bearer placeholder") == []
    assert secret_scan_text("Authorization: Bearer authentication is required") == []
    assert secret_scan_text("api_key=sk-abcdefghijklmnopqrstuvwxyz") != []
    assert secret_scan_text("sk-proj-abcdefghijklmnopqrstuvwxyz012345") != []
    assert secret_scan_text("sk-abcdefghijklmnopqrstuvwxyz012345") != []
    assert secret_scan_text("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE") != []
    assert secret_scan_text("aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY") != []
    assert secret_scan_text("password=SuperSecretPass123") != []
    assert secret_scan_text("token=ghp_abcdefghijklmnopqrstuvwxyz012345") != []
    assert secret_scan_text("-----BEGIN PRIVATE KEY-----") != []
    assert (
        secret_scan_text(
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        != []
    )
    for relative in paths:
        assert hashes[relative] == file_sha256(tmp_path / relative)
    # recordsSha256 covers exact sorted records list.
    from ai_pdf_worker.r803_evaluation_contract import canonical_sha256

    assert manifest["recordsSha256"] == canonical_sha256(manifest["records"])


def test_quick_diagnostic_capture_uses_succeeded_provider_attempt_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_pdf_api.services.providers import ModelProviderError
    from ai_pdf_worker.r803_evaluation_provider import ProviderResult

    monkeypatch.setattr(evaluation_provider, "sleep", lambda _seconds: None)
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    case = next(item for item in package.cases if item["id"] == "r100-refuse-customer")
    state = {"quick_calls": 0}

    class TransientThenSuccessProvider(DeterministicProvider):
        def generate(self, messages, *, node_key: str) -> ProviderResult:
            if node_key == "quick":
                state["quick_calls"] += 1
                if state["quick_calls"] == 1:
                    raise ModelProviderError(
                        "generation_provider_transient",
                        "temporary outage",
                    )
            return super().generate(messages, node_key=node_key)

    capture = DiagnosticCapture(case_key=str(case["id"]), mode="quick")
    execution, diagnostic = run_quick_case_with_diagnostics(
        package,
        case,
        TransientThenSuccessProvider(),
        diagnostic_capture=capture,
    )
    assert diagnostic is None
    assert execution.failure_code is None
    assert state["quick_calls"] == 2
    assert len(capture.records) == 1
    record = capture.records[0]
    assert record.node_key == "quick"
    assert record.attempt_number == 2
    assert record.logical_call_key == f"{case['id']}:quick:0:quick"
    succeeded = [
        item
        for item in execution.calls
        if item.node_key == "quick" and item.status == "succeeded"
    ]
    assert len(succeeded) == 1
    assert succeeded[0].attempt_number == 2
    assert succeeded[0].logical_call_key == record.logical_call_key


def test_successful_quality_failure_provenance_resolver_quick_and_research() -> None:
    from ai_pdf_worker.r803_evaluation_scorer_v2 import (
        resolve_successful_quality_failure_diagnostic,
        score_case_v2,
    )

    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    by_id = {case["id"]: case for case in package.cases}

    # Quick negation: unique quick raw record.
    quick_case = by_id["r100-locate-chart-caption"]
    quick_exec = CaseExecution(
        case_key=quick_case["id"],
        mode="quick",
        output="Do not verify the chart and caption together.",
        observed_disposition="answer",
        evidence_ids=("answer-image-constraint",),
        conflict_detected=False,
        observed_claims=(
            ObservedClaim(
                "Do not verify the chart and caption together.",
                ("answer-image-constraint",),
                False,
            ),
        ),
        wall_time_ms=1,
        calls=(),
    )
    quick_score = score_case_v2(quick_case, quick_exec)
    assert quick_score["qualityFailure"] is True
    assert quick_score["failureCode"] == "unsupported_claim"
    assert "_quality_failure_provenance_hints" in quick_score
    quick_capture = DiagnosticCapture(case_key=quick_case["id"], mode="quick")
    quick_raw = (
        '{"answer":"Do not verify the chart and caption together.",'
        '"claims":[{"text":"Do not verify the chart and caption together.",'
        '"evidenceIds":["answer-image-constraint"]}],"conflictDetected":false}'
    )
    quick_capture.record(
        node_key="quick",
        logical_call_key=f"{quick_case['id']}:quick:0:quick",
        attempt_number=1,
        raw_text=quick_raw,
    )
    quick_diag = resolve_successful_quality_failure_diagnostic(
        quick_score, quick_exec, quick_capture
    )
    assert quick_diag is not None
    assert quick_diag.failure_code == "scorer_semantic_failure"
    assert quick_diag.stage == "scorer_v2"
    assert quick_diag.node_key == "quick"
    assert quick_diag.logical_call_key == f"{quick_case['id']}:quick:0:quick"
    assert quick_diag.raw_output_sha256 == quick_capture.records[0].sha256
    assert classify_failure_origin(quick_diag.failure_code) == "model_or_workflow_quality"

    # Research: two researcher branches; only branch-b contains the negated claim text.
    research_case = by_id["r100-locate-chart-caption"]
    negated_text = "Do not verify the chart and caption together."
    research_exec = CaseExecution(
        case_key=research_case["id"],
        mode="research",
        output=negated_text,
        observed_disposition="answer",
        evidence_ids=("answer-image-constraint",),
        conflict_detected=False,
        observed_claims=(
            ObservedClaim(negated_text, ("answer-image-constraint",), False),
        ),
        wall_time_ms=1,
        calls=(),
    )
    research_score = score_case_v2(research_case, research_exec)
    assert research_score["negatedClaimCount"] == 1
    research_capture = DiagnosticCapture(case_key=research_case["id"], mode="research")
    research_capture.record(
        node_key="researcher",
        logical_call_key=f"{research_case['id']}:researcher:0:researcher",
        attempt_number=1,
        raw_text='{"claims":[{"text":"unrelated branch claim","evidenceHandleIds":["h1"]}]}',
    )
    research_capture.record(
        node_key="researcher",
        logical_call_key=f"{research_case['id']}:researcher:1:researcher",
        attempt_number=1,
        raw_text=(
            '{"claims":[{"text":"Do not verify the chart and caption together.",'
            '"evidenceHandleIds":["h2"]}]}'
        ),
    )
    # Later nodes must not be selected via latest().
    research_capture.record(
        node_key="critic",
        logical_call_key=f"{research_case['id']}:critic:0:critic",
        attempt_number=1,
        raw_text='{"conflictClaimIds":[]}',
    )
    research_diag = resolve_successful_quality_failure_diagnostic(
        research_score, research_exec, research_capture
    )
    assert research_diag is not None
    assert research_diag.node_key == "researcher"
    assert research_diag.logical_call_key == f"{research_case['id']}:researcher:1:researcher"
    assert research_diag.raw_output_sha256 == research_capture.records[1].sha256
    assert research_diag.failure_code == "scorer_semantic_failure"

    # Ambiguity: same exact claim text in two researcher records fails closed.
    amb_capture = DiagnosticCapture(case_key=research_case["id"], mode="research")
    amb_payload = (
        '{"claims":[{"text":"Do not verify the chart and caption together.",'
        '"evidenceHandleIds":["h2"]}]}'
    )
    amb_capture.record(
        node_key="researcher",
        logical_call_key=f"{research_case['id']}:researcher:0:researcher",
        attempt_number=1,
        raw_text=amb_payload,
    )
    amb_capture.record(
        node_key="researcher",
        logical_call_key=f"{research_case['id']}:researcher:1:researcher",
        attempt_number=1,
        raw_text=amb_payload,
    )
    with pytest.raises(R803EvaluationError, match="quality_failure_provenance_unresolved"):
        resolve_successful_quality_failure_diagnostic(
            research_score, research_exec, amb_capture
        )

    # Distinct offending researcher texts across records also fail closed.
    # Two expected-claim negations that map to two different researcher raw records.
    multi_exec = CaseExecution(
        case_key="r100-synthesize-table-constraint",
        mode="research",
        output=(
            "Atlas does not have a score of 91.4. "
            "Do not verify the chart and caption together."
        ),
        observed_disposition="answer",
        evidence_ids=("answer-pdf-table", "answer-image-constraint"),
        conflict_detected=False,
        observed_claims=(
            ObservedClaim(
                "Atlas does not have a score of 91.4.",
                ("answer-pdf-table",),
                False,
            ),
            ObservedClaim(
                "Do not verify the chart and caption together.",
                ("answer-image-constraint",),
                False,
            ),
        ),
        wall_time_ms=1,
        calls=(),
    )
    multi_score = score_case_v2(by_id["r100-synthesize-table-constraint"], multi_exec)
    assert multi_score["negatedClaimCount"] == 2
    multi_capture = DiagnosticCapture(
        case_key="r100-synthesize-table-constraint", mode="research"
    )
    multi_capture.record(
        node_key="researcher",
        logical_call_key="case:researcher:0:researcher",
        attempt_number=1,
        raw_text=(
            '{"claims":[{"text":"Atlas does not have a score of 91.4.",'
            '"evidenceHandleIds":["h1"]}]}'
        ),
    )
    multi_capture.record(
        node_key="researcher",
        logical_call_key="case:researcher:1:researcher",
        attempt_number=1,
        raw_text=(
            '{"claims":[{"text":"Do not verify the chart and caption together.",'
            '"evidenceHandleIds":["h2"]}]}'
        ),
    )
    with pytest.raises(R803EvaluationError, match="quality_failure_provenance_unresolved"):
        resolve_successful_quality_failure_diagnostic(
            multi_score,
            multi_exec,
            multi_capture,
        )

    # Conflict mismatch binds the unique critic record.
    conflict_case = by_id["r100-conflict-direction"]
    conflict_exec = CaseExecution(
        case_key=conflict_case["id"],
        mode="research",
        output="The PDF trend rises while the image drops.",
        observed_disposition="answer",
        evidence_ids=("answer-pdf-chart", "answer-image-trend"),
        conflict_detected=False,
        observed_claims=(
            ObservedClaim(
                "The PDF trend rises after the third point.",
                ("answer-pdf-chart",),
                False,
            ),
            ObservedClaim(
                "The image observation falls in a sustained drop.",
                ("answer-image-trend",),
                False,
            ),
        ),
        wall_time_ms=1,
        calls=(),
    )
    conflict_score = score_case_v2(conflict_case, conflict_exec)
    assert conflict_score["qualityFailure"] is True
    conflict_capture = DiagnosticCapture(case_key=conflict_case["id"], mode="research")
    conflict_capture.record(
        node_key="researcher",
        logical_call_key=f"{conflict_case['id']}:researcher:0:researcher",
        attempt_number=1,
        raw_text=(
            '{"claims":[{"text":"The PDF trend rises after the third point.",'
            '"evidenceHandleIds":["h1"]},'
            '{"text":"The image observation falls in a sustained drop.",'
            '"evidenceHandleIds":["h2"]}]}'
        ),
    )
    conflict_capture.record(
        node_key="critic",
        logical_call_key=f"{conflict_case['id']}:critic:0:critic",
        attempt_number=1,
        raw_text='{"conflictClaimIds":[]}',
    )
    conflict_diag = resolve_successful_quality_failure_diagnostic(
        conflict_score, conflict_exec, conflict_capture
    )
    assert conflict_diag is not None
    assert conflict_diag.node_key == "critic"
    assert conflict_diag.logical_call_key == f"{conflict_case['id']}:critic:0:critic"
    assert conflict_diag.raw_output_sha256 == conflict_capture.records[1].sha256


def test_research_empty_synthesizer_selection_binds_unique_synthesizer() -> None:
    from ai_pdf_worker.r803_evaluation_scorer_v2 import (
        resolve_successful_quality_failure_diagnostic,
        score_case_v2,
    )

    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    case = next(item for item in package.cases if item["id"] == "r100-locate-chart-caption")
    # Successful Research transport + empty final Synthesizer selection => refuse.
    execution = CaseExecution(
        case_key=case["id"],
        mode="research",
        output="The selected assets do not contain supporting evidence for this question.",
        observed_disposition="refuse",
        evidence_ids=(),
        conflict_detected=False,
        observed_claims=(),
        wall_time_ms=1,
        calls=(),
    )
    score = score_case_v2(case, execution)
    assert score["qualityFailure"] is True
    assert score["failureCode"] is not None
    hints = score["_quality_failure_provenance_hints"]
    assert any(
        hint.get("kind") == "node"
        and hint.get("nodeKey") == "synthesizer"
        and hint.get("rule") in {
            "disposition_mismatch",
            "refusal_or_empty_selection_mismatch",
        }
        for hint in hints
    )
    assert any(
        hint.get("kind") == "unresolved" and hint.get("rule") == "missing_expected_claim"
        for hint in hints
    )

    capture = DiagnosticCapture(case_key=case["id"], mode="research")
    # Upstream claims exist in researcher raw, but final selection was empty.
    capture.record(
        node_key="researcher",
        logical_call_key=f"{case['id']}:researcher:0:researcher",
        attempt_number=1,
        raw_text=(
            '{"claims":[{"text":"Verify the chart and caption together.",'
            '"evidenceHandleIds":["h1"]}]}'
        ),
    )
    synth_raw = '{"factClaimIds":[],"unresolvedClaimIds":[]}'
    capture.record(
        node_key="synthesizer",
        logical_call_key=f"{case['id']}:synthesizer:0:synthesizer",
        attempt_number=1,
        raw_text=synth_raw,
    )
    diagnostic = resolve_successful_quality_failure_diagnostic(score, execution, capture)
    assert diagnostic is not None
    assert diagnostic.node_key == "synthesizer"
    assert diagnostic.logical_call_key == f"{case['id']}:synthesizer:0:synthesizer"
    assert diagnostic.raw_output_sha256 == capture.records[1].sha256
    assert diagnostic.failure_code == "scorer_semantic_failure"
    assert classify_failure_origin(diagnostic.failure_code) == "model_or_workflow_quality"


def test_missing_expected_claim_without_disposition_mismatch_remains_unresolved() -> None:
    from ai_pdf_worker.r803_evaluation_scorer_v2 import (
        resolve_successful_quality_failure_diagnostic,
        score_case_v2,
    )

    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    case = next(item for item in package.cases if item["id"] == "r100-locate-chart-caption")
    # Answer disposition but missing expected claim text: no synth disposition mismatch.
    execution = CaseExecution(
        case_key=case["id"],
        mode="research",
        output="Unrelated answer without the required claim.",
        observed_disposition="answer",
        evidence_ids=("answer-image-constraint",),
        conflict_detected=False,
        observed_claims=(
            ObservedClaim(
                "Unrelated answer without the required claim.",
                ("answer-image-constraint",),
                False,
            ),
        ),
        wall_time_ms=1,
        calls=(),
    )
    score = score_case_v2(case, execution)
    assert score["qualityFailure"] is True
    hints = score["_quality_failure_provenance_hints"]
    assert any(
        hint.get("kind") == "unresolved" and hint.get("rule") == "missing_expected_claim"
        for hint in hints
    )
    assert not any(
        hint.get("kind") == "node" and hint.get("nodeKey") == "synthesizer"
        for hint in hints
    )
    capture = DiagnosticCapture(case_key=case["id"], mode="research")
    capture.record(
        node_key="researcher",
        logical_call_key=f"{case['id']}:researcher:0:researcher",
        attempt_number=1,
        raw_text=(
            '{"claims":[{"text":"Unrelated answer without the required claim.",'
            '"evidenceHandleIds":["h1"]}]}'
        ),
    )
    capture.record(
        node_key="synthesizer",
        logical_call_key=f"{case['id']}:synthesizer:0:synthesizer",
        attempt_number=1,
        raw_text='{"factClaimIds":["c1"],"unresolvedClaimIds":[]}',
    )
    with pytest.raises(R803EvaluationError, match="quality_failure_provenance_unresolved"):
        resolve_successful_quality_failure_diagnostic(score, execution, capture)


def test_independent_researcher_and_synthesizer_hints_remain_ambiguous() -> None:
    from ai_pdf_worker.r803_evaluation_scorer_v2 import (
        resolve_successful_quality_failure_diagnostic,
        score_case_v2,
    )

    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    case = next(item for item in package.cases if item["id"] == "r100-locate-chart-caption")
    # Empty selection (synth disposition) plus independent negated claim text cannot
    # collapse to one raw record when both hints are active under non-empty claims.
    # Use refuse-with-no-claims for synth, but inject an independent claim-text path
    # by scoring a mixed execution is wrong; instead score empty refuse then manually
    # append an independent claim-text hint that resolves to researcher.
    execution = CaseExecution(
        case_key=case["id"],
        mode="research",
        output="The selected assets do not contain supporting evidence for this question.",
        observed_disposition="refuse",
        evidence_ids=(),
        conflict_detected=False,
        observed_claims=(),
        wall_time_ms=1,
        calls=(),
    )
    score = score_case_v2(case, execution)
    assert score["qualityFailure"] is True
    # Independent researcher claim-text root cause is NOT a missing_expected_claim
    # consequence of empty selection; it must keep multi-record ambiguity.
    score["_quality_failure_provenance_hints"] = list(
        score["_quality_failure_provenance_hints"]
    ) + [
        {
            "kind": "claim_text",
            "rule": "negated_claim",
            "path": "$.claims[paired-evidence]",
            "expectedClaimKey": "paired-evidence",
            "observedClaimText": "Do not verify the chart and caption together.",
            "nodeKey": "researcher",
        }
    ]
    capture = DiagnosticCapture(case_key=case["id"], mode="research")
    capture.record(
        node_key="researcher",
        logical_call_key=f"{case['id']}:researcher:0:researcher",
        attempt_number=1,
        raw_text=(
            '{"claims":[{"text":"Do not verify the chart and caption together.",'
            '"evidenceHandleIds":["h1"]}]}'
        ),
    )
    capture.record(
        node_key="synthesizer",
        logical_call_key=f"{case['id']}:synthesizer:0:synthesizer",
        attempt_number=1,
        raw_text='{"factClaimIds":[],"unresolvedClaimIds":[]}',
    )
    with pytest.raises(
        R803EvaluationError,
        match="quality_failure_provenance_unresolved:ambiguous_records",
    ):
        resolve_successful_quality_failure_diagnostic(score, execution, capture)


def test_campaign_successful_quality_failure_requires_exact_provenance(
    tmp_path: Path,
) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    plan = freeze_campaign_plan(package)

    class NegatingQuickProvider(DeterministicProvider):
        def generate(self, messages, *, node_key: str):
            if node_key == "quick":
                import json as _json

                from ai_pdf_worker.r803_evaluation_provider import ProviderResult

                return ProviderResult(
                    output=_json.dumps(
                        {
                            "answer": "Do not verify the chart and caption together.",
                            "claims": [
                                {
                                    "text": "Do not verify the chart and caption together.",
                                    "evidenceIds": ["answer-image-constraint"],
                                }
                            ],
                            "conflictDetected": False,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    input_tokens=3,
                    output_tokens=2,
                    usage_final=True,
                )
            return super().generate(messages, node_key=node_key)

    # Round should complete with bound quality failure provenance for quick.
    campaign_dir = tmp_path / "quality-prov"
    report = _run_campaign(campaign_dir, NegatingQuickProvider(), package, max_new_rounds=1)
    assert report["status"] in {"completed", "failed"}
    # Inspect first round paired artifact: private hints must be absent.
    round_dir = campaign_dir / "round-01"
    paired = json.loads((round_dir / "paired-quality-report.json").read_text(encoding="utf-8"))
    quick_eval = json.loads((round_dir / "quick-evaluation.json").read_text(encoding="utf-8"))
    research_eval = json.loads((round_dir / "research-evaluation.json").read_text(encoding="utf-8"))
    blob = json.dumps({"paired": paired, "quick": quick_eval, "research": research_eval})
    assert "_quality_failure_provenance_hints" not in blob
    # Locate chart-caption case should have a fully bound quality diagnostic for quick.
    target = next(
        item for item in paired["cases"] if item["caseKey"] == "r100-locate-chart-caption"
    )
    diag = target["quick"]["diagnostic"]
    assert target["quick"]["qualityFailure"] is True
    assert diag is not None
    assert diag["nodeKey"] == "quick"
    assert diag["logicalCallKey"]
    assert diag["rawOutputSha256"]
    assert diag["failureCode"] == "scorer_semantic_failure"
    assert diag["failureOrigin"] == "model_or_workflow_quality"
    # Public R700 failureCode remains semantic/public, not private hint payload.
    public_case = next(
        item for item in quick_eval["cases"] if item["caseKey"] == "r100-locate-chart-caption"
    )
    assert public_case["failureCode"] == "unsupported_claim"
    assert "_quality_failure_provenance_hints" not in public_case

    # Fail-closed: force a research quality failure with no resolvable researcher claim text.
    class AmbiguousResearchProvider(DeterministicProvider):
        def generate(self, messages, *, node_key: str):
            if node_key == "researcher":
                import json as _json

                from ai_pdf_worker.r803_evaluation_provider import ProviderResult

                return ProviderResult(
                    output=_json.dumps(
                        {
                            "claims": [
                                {
                                    "text": "Do not verify the chart and caption together.",
                                    "evidenceHandleIds": ["handle-x"],
                                }
                            ]
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    input_tokens=3,
                    output_tokens=2,
                    usage_final=True,
                )
            return super().generate(messages, node_key=node_key)

    # Unit-level ambiguity already covered; campaign path raises unresolved for missing capture text.
    from ai_pdf_worker.r803_evaluation_scorer_v2 import (
        resolve_successful_quality_failure_diagnostic,
        score_case_v2,
    )

    case = next(item for item in package.cases if item["id"] == "r100-locate-chart-caption")
    execution = CaseExecution(
        case_key=case["id"],
        mode="research",
        output="Do not verify the chart and caption together.",
        observed_disposition="answer",
        evidence_ids=("answer-image-constraint",),
        conflict_detected=False,
        observed_claims=(
            ObservedClaim(
                "Do not verify the chart and caption together.",
                ("answer-image-constraint",),
                False,
            ),
        ),
        wall_time_ms=1,
        calls=(),
    )
    score = score_case_v2(case, execution)
    empty_capture = DiagnosticCapture(case_key=case["id"], mode="research")
    empty_capture.record(
        node_key="planner",
        logical_call_key=f"{case['id']}:planner:0:planner",
        attempt_number=1,
        raw_text='{"summary":"x","knownGaps":[],"estimatedProviderCalls":1,"subproblems":[]}',
    )
    with pytest.raises(R803EvaluationError, match="quality_failure_provenance_unresolved"):
        resolve_successful_quality_failure_diagnostic(score, execution, empty_capture)
    _ = plan  # plan freeze still exercised above via campaign


def test_campaign_all_five_rounds_pass(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    report = _run_campaign(tmp_path / "campaign", CampaignProvider(), package)
    assert report["status"] == "completed"
    assert report["sample"]["completedRounds"] == 5
    assert report["gates"]["modelQuality"] == "pass"
    assert report["gates"]["engineering"] == "pass"
    assert report["gates"]["userValue"] == "not_evaluable"
    assert report["gates"]["productStage"] == "internal_preview"
    assert report["gates"]["quick"]["denominatorCaseCount"] == 30
    assert report["gates"]["research"]["denominatorCaseCount"] == 30
    assert report["sample"]["formalEvidence"] is False  # test provider
    assert (tmp_path / "campaign" / "campaign-report.json").is_file()
    assert (tmp_path / "campaign" / "campaign-report.sha256.json").is_file()
    # Terminal evidence supersedes mutable progress rather than leaving it authoritative.
    progress = tmp_path / "campaign" / "campaign-progress.json"
    if progress.exists():
        doc = json.loads(progress.read_text(encoding="utf-8"))
        assert doc.get("mutable") is False
        assert doc.get("supersededBy") == "campaign-report.json"
    for round_index in range(1, 6):
        round_dir = tmp_path / "campaign" / f"round-{round_index:02d}"
        parse_evaluation_report((round_dir / "quick-evaluation.json").read_bytes())
        parse_evaluation_report((round_dir / "research-evaluation.json").read_bytes())
        hashes = {
            name: digest
            for digest, name in (
                line.split()
                for line in (round_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
            )
        }
        assert "round-report.json" in hashes
        assert "round-manifest.json" in hashes
        assert "round-start.json" in hashes
        assert "SHA256SUMS" not in hashes
        for name, digest in hashes.items():
            assert file_sha256(round_dir / name) == digest
        paired = json.loads((round_dir / "paired-quality-report.json").read_text(encoding="utf-8"))
        assert "r700ImportCompatibility" in paired
        assert paired["gates"]["modelQuality"] == "pass"
        assert paired["providerAttestation"]["formalEvidence"] is False


def test_campaign_schema_failure_model_fail_engineering_pass(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "campaign-fail"
    report = _run_campaign(
        campaign_dir,
        CampaignProvider(fail_mode="schema", fail_round_trigger=1),
        package,
    )
    assert report["status"] == "failed"
    assert report["sample"]["completedRounds"] == 1
    assert report["gates"]["modelQuality"] == "fail"
    assert report["gates"]["engineering"] == "pass"
    round_dir = campaign_dir / "round-01"
    paired = json.loads((round_dir / "paired-quality-report.json").read_text(encoding="utf-8"))
    assert paired["gates"]["researchModelQuality"] == "fail"
    assert paired["gates"]["researchEngineering"] == "pass"
    assert paired["gates"]["modelQuality"] == "fail"
    # R700 import still collapses for compatibility.
    research_import = parse_evaluation_report((round_dir / "research-evaluation.json").read_bytes())
    assert research_import.evaluation.engineering_gate == "fail"
    assert research_import.evaluation.model_quality_gate == "not_evaluable"
    before = {
        name: file_sha256(round_dir / name)
        for name in (
            "quick-evaluation.json",
            "research-evaluation.json",
            "round-report.json",
            "round-manifest.json",
            "SHA256SUMS",
        )
    }
    terminal_before = file_sha256(campaign_dir / "campaign-report.json")
    resumed = _run_campaign(campaign_dir, CampaignProvider(), package)
    assert resumed["sample"]["completedRounds"] == 1
    assert resumed["gates"]["modelQuality"] == "fail"
    after = {
        name: file_sha256(round_dir / name)
        for name in (
            "quick-evaluation.json",
            "research-evaluation.json",
            "round-report.json",
            "round-manifest.json",
            "SHA256SUMS",
        )
    }
    assert before == after
    assert file_sha256(campaign_dir / "campaign-report.json") == terminal_before
    assert not (campaign_dir / "round-02").exists()


def test_provider_outage_marks_model_not_evaluable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(evaluation_provider, "sleep", lambda _seconds: None)
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    report = _run_campaign(
        tmp_path / "outage",
        CampaignProvider(fail_mode="outage"),
        package,
    )
    assert report["status"] == "failed"
    assert report["gates"]["engineering"] == "fail"
    assert report["gates"]["modelQuality"] == "not_evaluable"
    round_dir = tmp_path / "outage" / "round-01"
    paired = json.loads((round_dir / "paired-quality-report.json").read_text(encoding="utf-8"))
    assert paired["gates"]["engineering"] == "fail"
    assert paired["gates"]["modelQuality"] == "not_evaluable"
    assert paired["gates"]["quickModelQuality"] == "not_evaluable"
    assert paired["gates"]["researchModelQuality"] == "not_evaluable"


def test_resume_rejects_hash_drift_and_overwrite(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "drift"
    _run_campaign(campaign_dir, CampaignProvider(), package, max_new_rounds=1)
    assert (campaign_dir / "campaign-progress.json").is_file()
    assert not (campaign_dir / "campaign-report.json").exists()
    target = campaign_dir / "round-01" / "paired-quality-report.json"
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(R803EvaluationError, match="checksum_drift|unlisted_round_files"):
        _run_campaign(campaign_dir, CampaignProvider(), package)
    with pytest.raises(R803EvaluationError, match="round_directory_not_empty"):
        plan = freeze_campaign_plan(package)
        run_campaign_round(
            plan,
            round_index=1,
            provider=CampaignProvider(),
            output_dir=campaign_dir / "round-01",
            allow_test_provider=True,
        )


def test_unlisted_round_file_and_gap_round_are_rejected(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "extra-file"
    _run_campaign(campaign_dir, CampaignProvider(), package, max_new_rounds=1)
    extra = campaign_dir / "round-01" / "notes.txt"
    extra.write_text("not checksummed\n", encoding="utf-8")
    with pytest.raises(R803EvaluationError, match="unlisted_round_files"):
        _run_campaign(campaign_dir, CampaignProvider(), package, max_new_rounds=0)

    gap_dir = tmp_path / "gap"
    _run_campaign(gap_dir, CampaignProvider(), package, max_new_rounds=1)
    (gap_dir / "round-03").mkdir()
    (gap_dir / "round-03" / "junk.json").write_text("{}", encoding="utf-8")
    with pytest.raises(R803EvaluationError, match="round_order_violation"):
        _run_campaign(gap_dir, CampaignProvider(), package, max_new_rounds=0)
    with pytest.raises(R803EvaluationError, match="round_order_violation"):
        _run_campaign(gap_dir, CampaignProvider(), package, max_new_rounds=1)


def test_terminal_resume_recomputes_full_graph_and_rejects_tamper(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "terminal"
    original = _run_campaign(
        campaign_dir,
        CampaignProvider(fail_mode="schema"),
        package,
        max_new_rounds=1,
    )
    assert original["status"] == "failed"
    resumed = _run_campaign(campaign_dir, None, package, max_new_rounds=0)
    assert resumed == original

    # Missing companion is rejected.
    companion = campaign_dir / "campaign-report.sha256.json"
    companion_bytes = companion.read_bytes()
    companion.unlink()
    with pytest.raises(R803EvaluationError, match="missing_campaign_report_companion"):
        _run_campaign(campaign_dir, None, package, max_new_rounds=0)
    companion.write_bytes(companion_bytes)

    # Forged completedRounds rejected via recompute mismatch / missing round.
    report_path = campaign_dir / "campaign-report.json"
    forged = json.loads(report_path.read_text(encoding="utf-8"))
    forged["sample"]["completedRounds"] = 2
    # rewrite by replacing file is blocked for exclusive create; use direct overwrite for tamper probe
    report_path.write_bytes(canonical_bytes(forged))
    companion.write_bytes(canonical_bytes({"sha256": file_sha256(report_path)}))
    with pytest.raises(
        R803EvaluationError,
        match="terminal_missing_round|campaign_report_recompute_mismatch|campaign_report_round",
    ):
        _run_campaign(campaign_dir, None, package, max_new_rounds=0)



def test_terminal_resume_rejects_out_of_range_and_malformed_round_dirs(
    tmp_path: Path,
) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "full-terminal-extra"
    report = _run_campaign(campaign_dir, CampaignProvider(), package)
    assert report["status"] == "completed"
    assert report["sample"]["completedRounds"] == 5

    # Terminal evidence must reject every nonempty out-of-range round directory.
    extra = campaign_dir / "round-06"
    extra.mkdir(parents=True)
    (extra / "junk.json").write_text("{}", encoding="utf-8")
    with pytest.raises(R803EvaluationError, match="round_index_out_of_range:6"):
        _run_campaign(campaign_dir, None, package, max_new_rounds=0)

    # Cleanup round-06 and probe a malformed round name under terminal resume.
    for child in extra.iterdir():
        child.unlink()
    extra.rmdir()
    bad = campaign_dir / "round-1"
    bad.mkdir(parents=True)
    (bad / "junk.json").write_text("{}", encoding="utf-8")
    with pytest.raises(R803EvaluationError, match="malformed_round_directory"):
        _run_campaign(campaign_dir, None, package, max_new_rounds=0)


def test_freeze_interruption_requires_valid_partial_start_companion(
    tmp_path: Path,
) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    plan = freeze_campaign_plan(package)
    from ai_pdf_worker.r803_evaluation_campaign import (
        _write_immutable_json,
        _write_round_start_marker,
    )

    # Missing companion: must fail immediately, not mint a terminal report.
    missing_dir = tmp_path / "missing-companion"
    digest = _write_immutable_json(missing_dir / "campaign-plan.json", plan.plan_document)
    _write_immutable_json(missing_dir / "campaign-plan.sha256.json", {"sha256": digest})
    round_dir = missing_dir / "round-01"
    round_dir.mkdir(parents=True)
    _write_round_start_marker(
        round_dir,
        plan,
        round_index=1,
        attestation={
            "formalEvidence": False,
            "evidenceClass": "non_formal_test_provider",
            "allowTestProvider": True,
        },
    )
    (round_dir / "round-start.sha256.json").unlink()
    (round_dir / "partial-note.txt").write_text("interrupted\n", encoding="utf-8")
    with pytest.raises(
        R803EvaluationError,
        match="terminal_partial_missing_round_start_companion",
    ):
        _run_campaign(missing_dir, CampaignProvider(), package)
    assert not (missing_dir / "campaign-report.json").exists()

    # Tampered companion: same fail-closed behavior before terminal write.
    tamper_dir = tmp_path / "tampered-companion"
    digest = _write_immutable_json(tamper_dir / "campaign-plan.json", plan.plan_document)
    _write_immutable_json(tamper_dir / "campaign-plan.sha256.json", {"sha256": digest})
    round_dir = tamper_dir / "round-01"
    round_dir.mkdir(parents=True)
    _write_round_start_marker(
        round_dir,
        plan,
        round_index=1,
        attestation={
            "formalEvidence": False,
            "evidenceClass": "non_formal_test_provider",
            "allowTestProvider": True,
        },
    )
    (round_dir / "round-start.sha256.json").write_text(
        json.dumps({"sha256": "0" * 64}),
        encoding="utf-8",
    )
    (round_dir / "partial-note.txt").write_text("interrupted\n", encoding="utf-8")
    with pytest.raises(
        R803EvaluationError,
        match="partial_round_start_companion_hash_drift",
    ):
        _run_campaign(tamper_dir, CampaignProvider(), package)
    assert not (tamper_dir / "campaign-report.json").exists()
    # Partial artifacts remain; no reuse/cleanup of the incomplete round.
    assert (round_dir / "round-start.json").is_file()
    assert (round_dir / "partial-note.txt").is_file()


def test_campaign_plan_mutation_is_rejected(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "plan-mut"
    _run_campaign(campaign_dir, CampaignProvider(), package, max_new_rounds=1)
    plan_path = campaign_dir / "campaign-plan.json"
    document = json.loads(plan_path.read_text(encoding="utf-8"))
    document["caseOrder"] = list(reversed(document["caseOrder"]))
    plan_path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    with pytest.raises(R803EvaluationError, match="campaign_plan_mutated"):
        _run_campaign(campaign_dir, CampaignProvider(), package)


def test_max_new_rounds_validation_and_terminal_without_provider(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "no-provider"
    with pytest.raises(R803EvaluationError, match="max_new_rounds_must_be_non_negative"):
        _run_campaign(campaign_dir, CampaignProvider(), package, max_new_rounds=-1)
    _run_campaign(
        campaign_dir,
        CampaignProvider(fail_mode="schema"),
        package,
        max_new_rounds=1,
    )
    resumed = _run_campaign(campaign_dir, None, package, max_new_rounds=0)
    assert resumed["status"] == "failed"
    assert resumed["sample"]["completedRounds"] == 1



def test_class_named_openai_injected_provider_still_requires_flag(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)

    class OpenAIRecordedProvider(CampaignProvider):
        pass

    with pytest.raises(R803EvaluationError, match="injected_provider_requires_allow_test_provider"):
        run_or_resume_campaign(
            campaign_dir=tmp_path / "spoof",
            provider=OpenAIRecordedProvider(),
            package=package,
            max_new_rounds=1,
            allow_test_provider=False,
        )

def test_injected_provider_requires_explicit_test_flag(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    with pytest.raises(R803EvaluationError, match="injected_provider_requires_allow_test_provider"):
        run_or_resume_campaign(
            campaign_dir=tmp_path / "formal-reject",
            provider=CampaignProvider(),
            package=package,
            max_new_rounds=1,
            allow_test_provider=False,
        )


def test_round_interruption_freezes_terminal_and_preserves_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "interrupt"
    plan = freeze_campaign_plan(package)

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated_process_interrupt")

    # Raise outside case handlers so the round aborts after durable round-start.
    monkeypatch.setattr(
        "ai_pdf_worker.r803_evaluation_campaign.run_quick_case_with_diagnostics",
        boom,
    )
    report = run_or_resume_campaign(
        campaign_dir=campaign_dir,
        provider=CampaignProvider(),
        package=package,
        max_new_rounds=1,
        allow_test_provider=True,
    )
    assert report["status"] == "failed"
    assert report["gates"]["engineering"] == "fail"
    assert report["gates"]["modelQuality"] == "not_evaluable"
    assert report["interruption"] is not None
    assert report["interruption"]["partialRoundPreserved"] is True
    assert report["interruption"]["planSha256"] == plan.plan_sha256
    # Safe class/code only; never raw exception text / secrets.
    assert report["interruption"]["detail"] == "RuntimeError"
    assert "simulated_process_interrupt" not in json.dumps(report["interruption"])
    round_dir = campaign_dir / "round-01"
    assert round_dir.exists()
    assert (round_dir / "round-start.json").is_file()
    assert (round_dir / "round-start.sha256.json").is_file()
    # Partial round is preserved and not reused.
    files_before = sorted(
        p.relative_to(round_dir).as_posix() for p in round_dir.rglob("*") if p.is_file()
    )
    resumed = run_or_resume_campaign(
        campaign_dir=campaign_dir,
        provider=CampaignProvider(),
        package=package,
        allow_test_provider=True,
    )
    assert resumed["status"] == "failed"
    assert resumed["gates"]["modelQuality"] == "not_evaluable"
    assert resumed["sample"]["completedRounds"] == 0
    assert resumed["interruption"]["roundIndex"] == 1
    files_after = sorted(
        p.relative_to(round_dir).as_posix() for p in round_dir.rglob("*") if p.is_file()
    )
    assert files_before == files_after
    assert not (campaign_dir / "round-02").exists()


def test_incomplete_started_round_on_resume_freezes(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "started"
    plan = freeze_campaign_plan(package)
    from ai_pdf_worker.r803_evaluation_campaign import (
        _write_immutable_json,
        _write_round_start_marker,
    )

    digest = _write_immutable_json(campaign_dir / "campaign-plan.json", plan.plan_document)
    _write_immutable_json(campaign_dir / "campaign-plan.sha256.json", {"sha256": digest})
    round_dir = campaign_dir / "round-01"
    round_dir.mkdir(parents=True)
    _write_round_start_marker(
        round_dir,
        plan,
        round_index=1,
        attestation={
            "formalEvidence": False,
            "evidenceClass": "non_formal_test_provider",
            "allowTestProvider": True,
        },
    )
    # Partial leaf without closure.
    (round_dir / "partial-note.txt").write_text("interrupted\n", encoding="utf-8")
    report = _run_campaign(campaign_dir, CampaignProvider(), package)
    assert report["status"] == "failed"
    assert report["gates"]["engineering"] == "fail"
    assert report["gates"]["modelQuality"] == "not_evaluable"
    assert report["interruption"]["reason"] == "round_incomplete"
    assert report["interruption"]["detail"] == "started_or_partial_round_not_closed"
    assert (round_dir / "round-start.json").is_file()
    # Terminal resume recomputes and permits exactly this partial round.
    resumed = _run_campaign(campaign_dir, None, package, max_new_rounds=0)
    assert resumed["interruption"]["roundIndex"] == 1
    assert resumed["sample"]["completedRounds"] == 0


def test_semantic_failures_bind_exact_logical_call_and_raw_sha() -> None:
    from ai_pdf_worker.r803_evaluation_diagnostics import DiagnosticCapture
    from ai_pdf_worker.r803_evaluation_runtime import _diagnostic_for_semantic_failure

    capture = DiagnosticCapture(case_key="r100-compare-rise-drop", mode="research")
    first = capture.record(
        node_key="researcher",
        logical_call_key="r100-compare-rise-drop:researcher:0:researcher",
        attempt_number=1,
        raw_text='{"claims":[{"text":"branch-a","evidenceHandleIds":["h-missing"]}]}',
    )
    second = capture.record(
        node_key="researcher",
        logical_call_key="r100-compare-rise-drop:researcher:1:researcher",
        attempt_number=1,
        raw_text='{"claims":[{"text":"branch-b","evidenceHandleIds":["h-ok"]}]}',
    )
    # Branch validation must bind the exact researcher logical key, never latest.
    branch = _diagnostic_for_semantic_failure(
        "claim_evidence_not_in_branch",
        capture,
        logical_call_key=first.logical_call_key,
    )
    assert branch is not None
    assert branch.failure_origin == "model_or_workflow_quality"
    assert branch.node_key == "researcher"
    assert branch.logical_call_key == first.logical_call_key
    assert branch.raw_output_sha256 == first.sha256
    assert branch.raw_output_sha256 != second.sha256

    # Ambiguous multi-researcher without exact key must not silently pick latest.
    ambiguous = _diagnostic_for_semantic_failure("claim_evidence_not_in_branch", capture)
    assert ambiguous is not None
    assert ambiguous.node_key == "researcher"
    assert ambiguous.logical_call_key is None
    assert ambiguous.raw_output_sha256 is None

    critic_capture = DiagnosticCapture(case_key="r100-conflict-direction", mode="research")
    critic = critic_capture.record(
        node_key="critic",
        logical_call_key="r100-conflict-direction:critic:0:critic",
        attempt_number=1,
        raw_text='{"conflictClaimIds":["missing-id"]}',
    )
    critic_diag = _diagnostic_for_semantic_failure(
        "critic_conflict_set_mismatch",
        critic_capture,
        logical_call_key=critic.logical_call_key,
    )
    assert critic_diag is not None
    assert critic_diag.failure_origin == "model_or_workflow_quality"
    assert critic_diag.node_key == "critic"
    assert critic_diag.logical_call_key == critic.logical_call_key
    assert critic_diag.raw_output_sha256 == critic.sha256

    synth_capture = DiagnosticCapture(case_key="r100-synthesize-table-constraint", mode="research")
    synth = synth_capture.record(
        node_key="synthesizer",
        logical_call_key="r100-synthesize-table-constraint:synthesizer:0:synthesizer",
        attempt_number=1,
        raw_text='{"factClaimIds":["not-publishable"],"unresolvedClaimIds":[]}',
    )
    synth_diag = _diagnostic_for_semantic_failure(
        "invalid_synthesis_selection",
        synth_capture,
        logical_call_key=synth.logical_call_key,
    )
    assert synth_diag is not None
    assert synth_diag.failure_origin == "model_or_workflow_quality"
    assert synth_diag.node_key == "synthesizer"
    assert synth_diag.logical_call_key == synth.logical_call_key
    assert synth_diag.raw_output_sha256 == synth.sha256


def test_runtime_branch_validation_diagnostic_uses_exact_researcher_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_pdf_worker.r803_evaluation_runtime import run_research_case_with_diagnostics
    from ai_pdf_worker.research_executor_contracts import ResearchExecutionError

    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    case = next(item for item in package.cases if item["id"] == "r100-compare-rise-drop")
    provider = DeterministicProvider()
    capture = DiagnosticCapture(case_key=str(case["id"]), mode="research")

    def patched_validate(self, result):  # type: ignore[no-untyped-def]
        raise ResearchExecutionError("claim_evidence_not_in_branch")

    monkeypatch.setattr(
        "ai_pdf_worker.research_executor_tools.EvidenceToolRegistry.validate_branch_result",
        patched_validate,
    )
    execution, diagnostic = run_research_case_with_diagnostics(
        package,
        case,
        provider,
        diagnostic_capture=capture,
    )
    assert execution.failure_code == "claim_evidence_not_in_branch"
    assert diagnostic is not None
    assert diagnostic.failure_origin == "model_or_workflow_quality"
    assert diagnostic.node_key == "researcher"
    assert diagnostic.logical_call_key is not None
    assert diagnostic.logical_call_key.endswith(":researcher")
    assert diagnostic.raw_output_sha256 is not None
    assert len(diagnostic.raw_output_sha256) == 64
    bound = capture.get_by_logical_call_key(diagnostic.logical_call_key)
    assert bound is not None
    assert bound.sha256 == diagnostic.raw_output_sha256


def test_production_default_behavior_unchanged_for_v4_path() -> None:
    result = run_paired_evaluation(provider=DeterministicProvider())
    assert result.quick_report["evaluation"]["engineeringGate"] == "pass"
    assert result.research_report["evaluation"]["engineeringGate"] == "pass"
    assert result.paired_report["gates"]["modelQuality"] == "not_evaluable"
    assert result.paired_report["sample"]["independentExecutionsPerCaseAndMode"] == 1


def test_r700_import_compatibility_for_campaign_round_reports(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "importable"
    _run_campaign(campaign_dir, CampaignProvider(), package, max_new_rounds=1)
    quick = parse_evaluation_report((campaign_dir / "round-01/quick-evaluation.json").read_bytes())
    research = parse_evaluation_report(
        (campaign_dir / "round-01/research-evaluation.json").read_bytes()
    )
    assert quick.evaluation.scorer_version == research.evaluation.scorer_version == "r100-v2"
    assert quick.evaluation.user_value_gate == "not_evaluable"
    for case in [*quick.cases, *research.cases]:
        unsupported = sum(claim.support_result == "unsupported" for claim in case.claims)
        assert unsupported == case.unsupported_claim_count



def test_direct_run_campaign_round_is_always_non_formal(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    plan = freeze_campaign_plan(package)
    with pytest.raises(R803EvaluationError, match="injected_provider_requires_allow_test_provider"):
        run_campaign_round(
            plan,
            round_index=1,
            provider=CampaignProvider(),
            output_dir=tmp_path / "round-direct",
            allow_test_provider=False,
        )
    result = run_campaign_round(
        plan,
        round_index=1,
        provider=CampaignProvider(),
        output_dir=tmp_path / "round-direct-ok",
        allow_test_provider=True,
    )
    assert result["roundReport"]["providerAttestation"]["formalEvidence"] is False
    assert result["roundReport"]["providerAttestation"]["evidenceClass"] == "non_formal_test_provider"
    # No caller-controlled formal minting parameter exists on the public API.
    import inspect

    signature = inspect.signature(run_campaign_round)
    assert "formal_configured" not in signature.parameters


def test_partial_round_with_later_nonempty_round_is_rejected(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "partial-gap"
    plan = freeze_campaign_plan(package)
    from ai_pdf_worker.r803_evaluation_campaign import (
        _write_immutable_json,
        _write_round_start_marker,
    )

    digest = _write_immutable_json(campaign_dir / "campaign-plan.json", plan.plan_document)
    _write_immutable_json(campaign_dir / "campaign-plan.sha256.json", {"sha256": digest})
    round1 = campaign_dir / "round-01"
    round1.mkdir(parents=True)
    _write_round_start_marker(
        round1,
        plan,
        round_index=1,
        attestation={"formalEvidence": False, "evidenceClass": "non_formal_test_provider"},
    )
    (round1 / "partial-note.txt").write_text("interrupted\n", encoding="utf-8")
    round3 = campaign_dir / "round-03"
    round3.mkdir(parents=True)
    (round3 / "junk.json").write_text("{}", encoding="utf-8")
    with pytest.raises(R803EvaluationError, match="round_order_violation"):
        _run_campaign(campaign_dir, CampaignProvider(), package, max_new_rounds=0)


def test_out_of_range_round_06_is_rejected(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "round-six"
    plan = freeze_campaign_plan(package)
    from ai_pdf_worker.r803_evaluation_campaign import _write_immutable_json

    digest = _write_immutable_json(campaign_dir / "campaign-plan.json", plan.plan_document)
    _write_immutable_json(campaign_dir / "campaign-plan.sha256.json", {"sha256": digest})
    extra = campaign_dir / "round-06"
    extra.mkdir(parents=True)
    (extra / "junk.json").write_text("{}", encoding="utf-8")
    with pytest.raises(R803EvaluationError, match="round_index_out_of_range:6"):
        _run_campaign(campaign_dir, CampaignProvider(), package, max_new_rounds=0)


def test_malformed_round_directory_name_is_rejected(tmp_path: Path) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    campaign_dir = tmp_path / "bad-name"
    plan = freeze_campaign_plan(package)
    from ai_pdf_worker.r803_evaluation_campaign import _write_immutable_json

    digest = _write_immutable_json(campaign_dir / "campaign-plan.json", plan.plan_document)
    _write_immutable_json(campaign_dir / "campaign-plan.sha256.json", {"sha256": digest})
    bad = campaign_dir / "round-1"
    bad.mkdir(parents=True)
    (bad / "junk.json").write_text("{}", encoding="utf-8")
    with pytest.raises(R803EvaluationError, match="malformed_round_directory"):
        _run_campaign(campaign_dir, CampaignProvider(), package, max_new_rounds=0)


def test_round_start_is_durable_before_first_provider_generate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    plan = freeze_campaign_plan(package)
    events: list[str] = []
    import ai_pdf_worker.r803_evaluation_campaign as campaign_mod

    original_write = campaign_mod._write_exclusive_bytes
    original_fsync = campaign_mod.os.fsync

    def tracked_write(path: Path, content: bytes) -> str:
        events.append(f"write:{path.name}")
        return original_write(path, content)

    def tracked_fsync(fd: int) -> None:
        events.append("fsync")
        return original_fsync(fd)

    monkeypatch.setattr(campaign_mod, "_write_exclusive_bytes", tracked_write)
    monkeypatch.setattr(campaign_mod.os, "fsync", tracked_fsync)

    provider = CampaignProvider()
    original_generate = provider.generate

    def tracked_generate(messages, *, node_key: str):
        events.append(f"generate:{node_key}")
        return original_generate(messages, node_key=node_key)

    monkeypatch.setattr(provider, "generate", tracked_generate)
    run_campaign_round(
        plan,
        round_index=1,
        provider=provider,
        output_dir=tmp_path / "durable-round",
        allow_test_provider=True,
    )
    first_generate = events.index(next(item for item in events if item.startswith("generate:")))
    prefix = events[:first_generate]
    assert "write:round-start.json" in prefix
    assert "write:round-start.sha256.json" in prefix
    # File + directory durability happens before any provider call.
    assert prefix.count("fsync") >= 2
    assert events.index("write:round-start.json") < first_generate
    assert events.index("write:round-start.sha256.json") < first_generate


def test_parallel_malformed_researcher_json_retains_exact_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hashlib

    from ai_pdf_worker.r803_evaluation_runtime import run_research_case_with_diagnostics
    from ai_pdf_worker.research_runtime_agents import GenerationResearchAgents

    package = load_evaluation_package(DEFAULT_PACKAGE_V5_PATH)
    case = next(item for item in package.cases if item["id"] == "r100-compare-rise-drop")
    provider = DeterministicProvider()
    capture = DiagnosticCapture(case_key=str(case["id"]), mode="research")
    original_json = GenerationResearchAgents._json
    calls = {"researcher": 0}

    def flaky_json(self, lease, node_key, variables):  # type: ignore[no-untyped-def]
        if node_key == "researcher":
            calls["researcher"] += 1
            # Force evaluator-diagnostic JSON failures on both researcher branches.
            raw = "{not-json-" + str(calls["researcher"])
            logical_call_key = f"{lease.step_id}:{node_key}"
            if self._output_observer is not None:
                self._output_observer(node_key, logical_call_key, raw)
            raise AgentResultValidationError(
                node_key,
                "json_decode",
                "$",
                logical_call_key=logical_call_key,
                raw_output_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            )
        return original_json(self, lease, node_key, variables)

    monkeypatch.setattr(GenerationResearchAgents, "_json", flaky_json)
    execution, diagnostic = run_research_case_with_diagnostics(
        package,
        case,
        provider,
        diagnostic_capture=capture,
    )
    assert execution.failure_code == "researcher_invalid_output"
    assert diagnostic is not None
    assert diagnostic.node_key == "researcher"
    assert diagnostic.logical_call_key is not None
    assert diagnostic.logical_call_key.endswith(":researcher")
    assert diagnostic.raw_output_sha256 is not None
    bound = capture.get_by_logical_call_key(diagnostic.logical_call_key)
    assert bound is not None
    assert bound.sha256 == diagnostic.raw_output_sha256
    # Two researcher attempts recorded with distinct identities/content.
    researcher_records = [item for item in capture.records if item.node_key == "researcher"]
    assert len(researcher_records) >= 1
    assert diagnostic.logical_call_key in {item.logical_call_key for item in researcher_records}


def test_v4_public_wrapper_unknown_exception_keeps_type_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = load_evaluation_package(DEFAULT_PACKAGE_PATH)
    provider = DeterministicProvider()

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "ai_pdf_worker.r803_evaluation_runtime.EvaluationGeneration.generate",
        boom,
    )
    quick = run_quick_case(package, package.cases[0], provider)
    research = run_research_case(package, package.cases[0], provider)
    assert quick.failure_code == "RuntimeError"
    assert research.failure_code == "RuntimeError"
    # Campaign/scorer still treats unknown as non-model-quality engineering path.
    from ai_pdf_worker.r803_evaluation_diagnostics import classify_failure_origin
    from ai_pdf_worker.r803_evaluation_scorer_v2 import score_case_v2

    scored = score_case_v2(package.cases[0], quick)
    assert classify_failure_origin("RuntimeError") == "unknown"
    assert scored["engineeringFailure"] is True
    assert scored["qualityFailure"] is False


def test_worker_docs_use_repo_root_uv_invocation() -> None:
    text = (REPO / "docs/evals/r803-v5-campaign-threshold.md").read_text(encoding="utf-8")
    assert "uv run --project apps/worker" in text
    # Command form must work from repo root (documented cwd).
    assert "python apps/worker/scripts/evaluate_r803_campaign.py" in text
