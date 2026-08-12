#!/usr/bin/env bash
# V5-D D003 mixed acceptance entrypoint skeleton.
#
# Reuses existing isolated runners without changing business API/Worker/Web
# contracts, backup manifest keys, or restore preflight rules.
#
# Default mode is static-only (cheap, no live Compose). Live lanes optionally
# invoke:
#   - run-v5b-document-acceptance.sh  (Document modality + browser restore)
#   - run-r800-acceptance.sh          (Research engineering + restore)
#
# D-G6: mixed seed/snapshot/verify CLIs live under apps/worker/scripts/
# (v5d_mixed_deployment_seed.py + v5d_mixed_restore_acceptance.py). Mode
# mixed-live records state + optional before/after snapshots without changing
# backup/restore contracts. Never claims realModelQualityPassed or userValuePassed.

set -euo pipefail
umask 077

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)

usage() {
  cat <<'EOF'
Usage: run-v5d-mixed-acceptance.sh --output-dir PATH [--mode MODE]

Modes:
  static-only   Static harness/preflight checks only (default; no live Compose)
  document      Run isolated V5-B Document deployment acceptance into <out>/document
  research      Run isolated R800 Research deployment acceptance into <out>/research
  both          Run document then research sequentially into subdirectories
  mixed-live    Validate mixed seed/restore CLI presence + optional live state/snapshots
  skeleton      Write artifact/report skeleton only (no child runners, no static suite)

Does not modify backup/restore contracts. mixed-live uses worker CLIs:
  apps/worker/scripts/v5d_mixed_deployment_seed.py
  apps/worker/scripts/v5d_mixed_restore_acceptance.py
Optional env: V5D_MIXED_STATE_PATH, V5D_MIXED_BEFORE_SNAPSHOT,
V5D_MIXED_AFTER_SNAPSHOT, V5D_MIXED_VERIFICATION.
EOF
}

OUTPUT_DIR=""
MODE="static-only"
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR=${2:-}
      shift 2
      ;;
    --mode)
      MODE=${2:-}
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf 'unknown_option option=%s\n' "$1" >&2
      exit 2
      ;;
  esac
done

case "$MODE" in
  static-only|document|research|both|mixed-live|skeleton) ;;
  *)
    printf 'v5d_mixed_invalid_mode mode=%s expected=static-only|document|research|both|mixed-live|skeleton\n' "$MODE" >&2
    exit 2
    ;;
esac

if [[ -z "$OUTPUT_DIR" ]]; then
  usage >&2
  exit 2
fi
OUTPUT_DIR=$(realpath -m "$OUTPUT_DIR")
if [[ -e "$OUTPUT_DIR" ]]; then
  printf 'v5d_mixed_output_exists path=%s\n' "$OUTPUT_DIR" >&2
  exit 1
fi
mkdir -m 700 -p "$OUTPUT_DIR"

SOURCE_SHA="unknown"
if git -C "$REPO_ROOT" rev-parse HEAD >/dev/null 2>&1; then
  SOURCE_SHA=$(git -C "$REPO_ROOT" rev-parse HEAD)
fi

SCRIPTS=(
  backup-deployment.sh
  restore-deployment.sh
  compose-common.sh
  test-backup-restore.sh
  run-v5b-document-acceptance.sh
  run-r800-acceptance.sh
  run-v5d-mixed-acceptance.sh
)

COMPOSE_FILES=(
  compose.deploy.yml
  compose.v5b.yml
  compose.r800.yml
  compose.m403.yml
)

FIXTURES=(
  docs/fixtures/document-modality/mixed-workspace.manifest.json
  docs/fixtures/document-modality/markdown-note.md
  docs/fixtures/evidence-contract/pdf-coordinate-fixture.pdf
  docs/fixtures/evidence-contract/image-coordinate-fixture.png
)

STATIC_STATUS=0
DOCUMENT_STATUS="skipped"
RESEARCH_STATUS="skipped"

require_path() {
  local path=$1
  if [[ ! -e "$REPO_ROOT/$path" ]]; then
    printf 'v5d_mixed_required_path_missing path=%s\n' "$path" >&2
    return 1
  fi
}

run_static_checks() {
  local failed=0
  local bash_n_ok=true
  local backup_unit_ok=true
  local fixtures_ok=true
  local compose_ok=true
  local contract_ok=true
  local mixed_runner_absent_ok=true
  local details=()

  printf 'v5d_mixed_static_start output=%s\n' "$OUTPUT_DIR"

  for script in "${SCRIPTS[@]}"; do
    if ! bash -n "$SCRIPT_DIR/$script" >"$OUTPUT_DIR/bash-n-$script.log" 2>&1; then
      bash_n_ok=false
      failed=1
      details+=("bash_n_failed:$script")
    fi
  done

  for compose in "${COMPOSE_FILES[@]}"; do
    if ! require_path "infra/docker/$compose"; then
      compose_ok=false
      failed=1
      details+=("compose_missing:$compose")
    fi
  done

  for fixture in "${FIXTURES[@]}"; do
    if ! require_path "$fixture"; then
      fixtures_ok=false
      failed=1
      details+=("fixture_missing:$fixture")
    fi
  done

  # Contract guard: backup/restore must keep document-modality-v1 keys unchanged.
  if ! grep -q 'BACKUP_CONTRACT=document-modality-v1' "$SCRIPT_DIR/backup-deployment.sh"; then
    contract_ok=false
    failed=1
    details+=("backup_contract_key_missing")
  fi
  if ! grep -q 'expected=document-modality-v1' "$SCRIPT_DIR/restore-deployment.sh"; then
    contract_ok=false
    failed=1
    details+=("restore_contract_guard_missing")
  fi
  if ! grep -q 'FORMAT_VERSION=2' "$SCRIPT_DIR/backup-deployment.sh"; then
    contract_ok=false
    failed=1
    details+=("backup_format_version_missing")
  fi

  # Worker health rule from accepted V5-B runner must remain documented in harness.
  if ! grep -q 'service == "worker" and entry.get("health") is None' \
    "$SCRIPT_DIR/run-v5b-document-acceptance.sh"; then
    contract_ok=false
    failed=1
    details+=("worker_health_null_rule_missing")
  fi

  # Mixed seed/snapshot CLIs and production-start e2e must exist for D-G4/D-G6 wiring.
  if [[ ! -f "$REPO_ROOT/apps/worker/scripts/v5d_mixed_deployment_seed.py" ]]; then
    mixed_runner_absent_ok=false
    failed=1
    details+=("mixed_seed_cli_missing")
  fi
  if [[ ! -f "$REPO_ROOT/apps/worker/scripts/v5d_mixed_restore_acceptance.py" ]]; then
    mixed_runner_absent_ok=false
    failed=1
    details+=("mixed_restore_cli_missing")
  fi
  if [[ ! -f "$REPO_ROOT/apps/web/e2e/v5d-mixed-production-start.spec.ts" ]]; then
    mixed_runner_absent_ok=false
    failed=1
    details+=("mixed_production_start_e2e_missing")
  fi

  set +e
  "$SCRIPT_DIR/test-backup-restore.sh" >"$OUTPUT_DIR/test-backup-restore.log" 2>&1
  local backup_unit_status=$?
  set -e
  if [[ "$backup_unit_status" -ne 0 ]]; then
    backup_unit_ok=false
    failed=1
    details+=("backup_restore_unit_failed:exit=$backup_unit_status")
  fi

  # Reuse surface: child runners must still call shared backup/restore.
  for runner in run-v5b-document-acceptance.sh run-r800-acceptance.sh; do
    if ! grep -q 'backup-deployment.sh' "$SCRIPT_DIR/$runner" \
      || ! grep -q 'restore-deployment.sh' "$SCRIPT_DIR/$runner"; then
      contract_ok=false
      failed=1
      details+=("runner_missing_backup_restore:$runner")
    fi
  done

  python3 - "$OUTPUT_DIR" "$bash_n_ok" "$backup_unit_ok" "$fixtures_ok" \
    "$compose_ok" "$contract_ok" "$mixed_runner_absent_ok" "$failed" \
    "${details[@]}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
flags = {
    "bashSyntax": sys.argv[2] == "true",
    "backupRestoreUnit": sys.argv[3] == "true",
    "fixturesPresent": sys.argv[4] == "true",
    "composeProfilesPresent": sys.argv[5] == "true",
    "backupRestoreContractUnchanged": sys.argv[6] == "true",
    "noPrematureLiveMixedClaim": sys.argv[7] == "true",
}
failed = int(sys.argv[8])
details = list(sys.argv[9:])
payload = {
    "schemaVersion": "v5d-mixed-static-checks-v1",
    "passed": failed == 0 and all(flags.values()),
    "checks": flags,
    "details": details,
}
(root / "static-checks.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
print(json.dumps(payload, sort_keys=True))
PY
  STATIC_STATUS=$failed
  return "$failed"
}

write_gap_analysis() {
  python3 - "$OUTPUT_DIR" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
gaps = [
    {
        "id": "G-MIXED-LIVE-SEED",
        "severity": "high",
        "summary": "Mixed seed/snapshot/verify CLIs exist; full isolated Compose live run still optional",
        "evidence": [
            "apps/worker/scripts/v5d_mixed_deployment_seed.py",
            "apps/worker/scripts/v5d_mixed_restore_acceptance.py",
            "apps/web/e2e/v5d-mixed-production-start.spec.ts",
        ],
        "blockerFor": ["D-G6 until mixed-live evidence recorded"],
        "owner": "D-API-WORKER seed/snapshot; D-OPS wire; D-WEB production-start e2e",
        "status": "partial-cli-ready",
    },
    {
        "id": "G-MIXED-BROWSER",
        "severity": "medium",
        "summary": "Production-start mixed Playwright exists; harness records when live evidence is supplied",
        "evidence": [
            "apps/web/e2e/v5d-mixed-production-start.spec.ts",
            "apps/web/e2e/v5d-mixed-workspace-primary.spec.ts (mocked engineering)",
        ],
        "blockerFor": ["D-G4 production-start until standalone+live run"],
        "owner": "D-WEB for e2e; D-OPS for harness wiring",
        "status": "partial-cli-ready",
    },
    {
        "id": "G-RESTART-LIVE",
        "severity": "medium",
        "summary": "No dedicated live Compose API/Worker/Web restart harness under infra",
        "evidence": [
            "D-G5 restart/reclaim/delete covered primarily by API/Worker unit/integration tests",
            "backup-deployment.sh stops writers only for backup window, not restart oracle",
        ],
        "blockerFor": ["D-G5 live restart evidence if unit tests insufficient"],
        "owner": "D-API-WORKER tests first; D-OPS only if live compose restart required",
        "status": "open",
    },
    {
        "id": "G-COMPOSE-V5D",
        "severity": "low",
        "summary": "No compose.v5d.yml; v5b and r800 overrides are sufficient provider-stub overlays",
        "evidence": [
            "infra/docker/compose.v5b.yml",
            "infra/docker/compose.r800.yml",
        ],
        "blockerFor": [],
        "owner": "D-OPS",
        "status": "accepted-reuse",
        "decision": "Reuse existing overrides; do not fork deploy contracts for V5-D",
    },
    {
        "id": "G-BACKUP-CONTRACT",
        "severity": "info",
        "summary": "Backup contract remains document-modality-v1; full pg_dump covers PDF/Image core tables",
        "evidence": [
            "infra/scripts/backup-deployment.sh BACKUP_CONTRACT=document-modality-v1",
            "infra/scripts/restore-deployment.sh strict key checks",
        ],
        "blockerFor": [],
        "owner": "D-OPS",
        "status": "pass-no-change",
    },
]
(root / "gap-analysis.json").write_text(json.dumps({
    "schemaVersion": "v5d-mixed-gap-analysis-v1",
    "gaps": gaps,
}, indent=2, sort_keys=True) + "\n")
print(json.dumps(gaps))
PY
}

write_report() {
  local mode=$1
  local static_status=$2
  local document_status=$3
  local research_status=$4
  local overall_status=$5
  python3 - "$OUTPUT_DIR" "$mode" "$SOURCE_SHA" "$RUN_ID" \
    "$static_status" "$document_status" "$research_status" "$overall_status" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
mode = sys.argv[2]
source_sha = sys.argv[3]
run_id = sys.argv[4]
static_status = int(sys.argv[5])
document_status = sys.argv[6]
research_status = sys.argv[7]
overall = sys.argv[8]

static = {}
static_path = root / "static-checks.json"
if static_path.exists():
    static = json.loads(static_path.read_text())
gaps = []
gap_path = root / "gap-analysis.json"
if gap_path.exists():
    gaps = json.loads(gap_path.read_text()).get("gaps", [])

def lane_status(raw: str) -> str:
    if raw == "skipped":
        return "skipped"
    if raw == "0":
        return "pass"
    if raw.isdigit():
        return "fail"
    return raw

document_lane = lane_status(document_status)
research_lane = lane_status(research_status)
static_lane = "pass" if static_status == 0 and static.get("passed", mode == "skeleton") else (
    "skipped" if mode == "skeleton" and not static else "fail"
)
if mode == "skeleton" and not static:
    static_lane = "skipped"

mixed_live = "blocked"
if mode == "mixed-live":
    mixed_live = "pass" if overall in {"mixed-live-pass", "mixed-live-pass-static-fail"} else "fail"
elif any(g.get("id") == "G-MIXED-LIVE-SEED" and g.get("status") == "partial-cli-ready" for g in gaps):
    mixed_live = "partial-cli-ready"

report = {
    "schemaVersion": "v5d-mixed-deployment-acceptance-v1",
    "runId": run_id,
    "mode": mode,
    "sourceSha": source_sha,
    "reuse": {
        "documentRunner": "infra/scripts/run-v5b-document-acceptance.sh",
        "researchRunner": "infra/scripts/run-r800-acceptance.sh",
        "backup": "infra/scripts/backup-deployment.sh",
        "restore": "infra/scripts/restore-deployment.sh",
        "composeBase": "infra/docker/compose.deploy.yml",
        "composeDocumentOverride": "infra/docker/compose.v5b.yml",
        "composeResearchOverride": "infra/docker/compose.r800.yml",
        "mixedFixtureManifest": "docs/fixtures/document-modality/mixed-workspace.manifest.json",
    },
    "lanes": {
        "static": {
            "status": static_lane,
            "exitCode": static_status if mode != "skeleton" else None,
            "artifact": "static-checks.json" if static else None,
        },
        "document": {
            "status": document_lane,
            "exitCode": int(document_status) if document_status.isdigit() else None,
            "artifactDir": "document" if document_lane != "skipped" else None,
            "scope": "Markdown Document only; not mixed PDF/Image/Document",
        },
        "research": {
            "status": research_lane,
            "exitCode": int(research_status) if research_status.isdigit() else None,
            "artifactDir": "research" if research_lane != "skipped" else None,
            "scope": "Research engineering restore; scripted provider only",
        },
        "mixedPdfImageDocumentLive": {
            "status": mixed_live,
            "reason": (
                "mixed_live_evidence_recorded"
                if mixed_live == "pass"
                else (
                    "mixed_seed_snapshot_cli_ready_awaiting_full_compose_or_evidence"
                    if mixed_live == "partial-cli-ready"
                    else "no_mixed_seed_snapshot_verify_cli"
                )
            ),
        },
    },
    "gates": {
        "D-G5": {
            "status": "partial",
            "note": "infra provides backup window stop/start only; restart/reclaim/delete oracles remain API/Worker tests",
        },
        "D-G6": {
            "status": "partial" if document_lane == "pass" or research_lane == "pass" else "blocked",
            "note": "document and research isolated restore may pass individually; mixed three-modality identity remains blocked",
        },
    },
    "engineeringGate": overall,
    "modelQualityGate": "not_evaluable",
    "modelQualityReason": "scripted_provider_is_engineering_evidence_only",
    "userValueGate": "not_evaluable",
    "userValueReason": "no_real_target_user_evidence",
    "contractImpact": "none",
    "gapAnalysis": gaps,
    "nextSteps": [
        "Keep using this wrapper for static D-OPS readiness",
        "Use mode=mixed-live with V5D_MIXED_STATE_PATH and optional before/after snapshots from v5d_mixed_* CLIs",
        "Do not invent fallback seed logic or weaken restore preflight",
        "D-ACCEPT must not mark D-G6 mixed live pass until mixed identity evidence exists",
    ],
}
(root / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
(root / "state.json").write_text(json.dumps({
    "schemaVersion": "v5d-mixed-acceptance-state-v1",
    "runId": run_id,
    "mode": mode,
    "sourceSha": source_sha,
    "engineeringGate": overall,
}, indent=2, sort_keys=True) + "\n")
print(json.dumps({"engineeringGate": overall, "report": str(root / "report.json")}, sort_keys=True))
PY
}

run_document_lane() {
  local out="$OUTPUT_DIR/document"
  printf 'v5d_mixed_document_lane_start output=%s\n' "$out"
  set +e
  "$SCRIPT_DIR/run-v5b-document-acceptance.sh" --output-dir "$out"
  local status=$?
  set -e
  DOCUMENT_STATUS="$status"
  printf 'v5d_mixed_document_lane_exit status=%s\n' "$status"
  return "$status"
}

run_research_lane() {
  local out="$OUTPUT_DIR/research"
  printf 'v5d_mixed_research_lane_start output=%s\n' "$out"
  set +e
  "$SCRIPT_DIR/run-r800-acceptance.sh" --output-dir "$out"
  local status=$?
  set -e
  RESEARCH_STATUS="$status"
  printf 'v5d_mixed_research_lane_exit status=%s\n' "$status"
  return "$status"
}

OVERALL="fail"
write_gap_analysis

case "$MODE" in
  skeleton)
    STATIC_STATUS=0
    OVERALL="skeleton"
    write_report "$MODE" "$STATIC_STATUS" "$DOCUMENT_STATUS" "$RESEARCH_STATUS" "$OVERALL"
    printf 'v5d_mixed_skeleton_complete report=%s\n' "$OUTPUT_DIR/report.json"
    exit 0
    ;;
  static-only)
    if run_static_checks; then
      OVERALL="static-pass"
    else
      OVERALL="static-fail"
    fi
    write_report "$MODE" "$STATIC_STATUS" "$DOCUMENT_STATUS" "$RESEARCH_STATUS" "$OVERALL"
    if [[ "$OVERALL" != "static-pass" ]]; then
      printf 'v5d_mixed_static_failed report=%s\n' "$OUTPUT_DIR/report.json" >&2
      exit 1
    fi
    printf 'v5d_mixed_static_complete report=%s mixed_live=blocked\n' "$OUTPUT_DIR/report.json"
    exit 0
    ;;
  document)
    run_static_checks || true
    if ! run_document_lane; then
      OVERALL="document-fail"
      write_report "$MODE" "$STATIC_STATUS" "$DOCUMENT_STATUS" "$RESEARCH_STATUS" "$OVERALL"
      exit 1
    fi
    if [[ "$STATIC_STATUS" -eq 0 ]]; then
      OVERALL="document-pass-mixed-blocked"
    else
      OVERALL="document-pass-static-fail"
    fi
    write_report "$MODE" "$STATIC_STATUS" "$DOCUMENT_STATUS" "$RESEARCH_STATUS" "$OVERALL"
    [[ "$STATIC_STATUS" -eq 0 ]]
    printf 'v5d_mixed_document_complete report=%s mixed_live=blocked\n' "$OUTPUT_DIR/report.json"
    exit 0
    ;;
  research)
    run_static_checks || true
    if ! run_research_lane; then
      OVERALL="research-fail"
      write_report "$MODE" "$STATIC_STATUS" "$DOCUMENT_STATUS" "$RESEARCH_STATUS" "$OVERALL"
      exit 1
    fi
    if [[ "$STATIC_STATUS" -eq 0 ]]; then
      OVERALL="research-pass-mixed-blocked"
    else
      OVERALL="research-pass-static-fail"
    fi
    write_report "$MODE" "$STATIC_STATUS" "$DOCUMENT_STATUS" "$RESEARCH_STATUS" "$OVERALL"
    [[ "$STATIC_STATUS" -eq 0 ]]
    printf 'v5d_mixed_research_complete report=%s mixed_live=blocked\n' "$OUTPUT_DIR/report.json"
    exit 0
    ;;
  both)
    run_static_checks || true
    doc_ok=0
    res_ok=0
    run_document_lane || doc_ok=$?
    run_research_lane || res_ok=$?
    if [[ "$doc_ok" -ne 0 || "$res_ok" -ne 0 || "$STATIC_STATUS" -ne 0 ]]; then
      OVERALL="both-fail"
      write_report "$MODE" "$STATIC_STATUS" "$DOCUMENT_STATUS" "$RESEARCH_STATUS" "$OVERALL"
      exit 1
    fi
    OVERALL="both-pass-mixed-blocked"
    write_report "$MODE" "$STATIC_STATUS" "$DOCUMENT_STATUS" "$RESEARCH_STATUS" "$OVERALL"
    printf 'v5d_mixed_both_complete report=%s mixed_live=blocked\n' "$OUTPUT_DIR/report.json"
    exit 0
    ;;
  mixed-live)
    run_static_checks || true
    set +e
    python3 - "$OUTPUT_DIR" "$REPO_ROOT" <<'PY'
import json
import os
from pathlib import Path
import sys

root = Path(sys.argv[1])
repo = Path(sys.argv[2])
checks = {
    "seedCli": (repo / "apps/worker/scripts/v5d_mixed_deployment_seed.py").is_file(),
    "restoreCli": (repo / "apps/worker/scripts/v5d_mixed_restore_acceptance.py").is_file(),
    "productionStartE2e": (repo / "apps/web/e2e/v5d-mixed-production-start.spec.ts").is_file(),
}
state_path = os.environ.get("V5D_MIXED_STATE_PATH")
before = os.environ.get("V5D_MIXED_BEFORE_SNAPSHOT")
after = os.environ.get("V5D_MIXED_AFTER_SNAPSHOT")
verification = os.environ.get("V5D_MIXED_VERIFICATION")
state = None
if state_path and Path(state_path).is_file():
    state = json.loads(Path(state_path).read_text())
verify = None
if verification and Path(verification).is_file():
    verify = json.loads(Path(verification).read_text())
elif before and after and Path(before).is_file() and Path(after).is_file():
    b = json.loads(Path(before).read_text())
    a = json.loads(Path(after).read_text())
    verify = {
        "passed": b.get("semanticSha256") == a.get("semanticSha256")
        and b.get("evidenceMode") == "live"
        and a.get("evidenceMode") == "live",
        "beforeSemanticSha256": b.get("semanticSha256"),
        "afterSemanticSha256": a.get("semanticSha256"),
    }
payload = {
    "schemaVersion": "v5d-mixed-live-lane-v1",
    "checks": checks,
    "statePath": state_path,
    "stateSchema": None if state is None else state.get("schemaVersion"),
    "stateHasThreeModalities": bool(
        state
        and set((state.get("assets") or {}).keys()) >= {"pdf", "image", "document"}
        and set((state.get("citationIds") or {}).keys()) >= {"pdf", "image", "document"}
    ),
    "verification": verify,
    "passed": all(checks.values())
    and state is not None
    and set((state.get("assets") or {}).keys()) >= {"pdf", "image", "document"}
    and set((state.get("citationIds") or {}).keys()) >= {"pdf", "image", "document"}
    and (verify is None or verify.get("passed") is True),
}
if before or after or verification:
    payload["passed"] = payload["passed"] and bool(verify and verify.get("passed") is True)
(root / "mixed-live.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
print(json.dumps(payload, sort_keys=True))
if not payload["passed"]:
    raise SystemExit(1)
PY
    mixed_status=$?
    set -e
    if [[ "$mixed_status" -ne 0 ]]; then
      OVERALL="mixed-live-fail"
      write_report "$MODE" "$STATIC_STATUS" "$DOCUMENT_STATUS" "$RESEARCH_STATUS" "$OVERALL"
      exit 1
    fi
    if [[ "$STATIC_STATUS" -eq 0 ]]; then
      OVERALL="mixed-live-pass"
    else
      OVERALL="mixed-live-pass-static-fail"
    fi
    write_report "$MODE" "$STATIC_STATUS" "$DOCUMENT_STATUS" "$RESEARCH_STATUS" "$OVERALL"
    printf 'v5d_mixed_live_complete report=%s overall=%s\n' "$OUTPUT_DIR/report.json" "$OVERALL"
    [[ "$STATIC_STATUS" -eq 0 ]]
    exit 0
    ;;

esac
