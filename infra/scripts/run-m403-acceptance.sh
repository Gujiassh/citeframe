#!/usr/bin/env bash

set -euo pipefail
umask 077

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
# shellcheck source=compose-common.sh
source "$SCRIPT_DIR/compose-common.sh"

usage() {
  cat <<'EOF'
Usage: run-m403-acceptance.sh --output-dir PATH [--project citeframe-m403-NAME]

Runs the real isolated Compose backup/restore and historical semantic oracle.
The project is always removed, including all named volumes, before returning.
M403_EXPECT_IMAGE_ENABLED defaults to false for the historical M403 gate; set
it to true when validating M403B or any deployment at/after a3c5e7f9b1d4.
EOF
}

OUTPUT_DIR=""
COMPOSE_PROJECT=""
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR=${2:-}
      shift 2
      ;;
    --project)
      COMPOSE_PROJECT=${2:-}
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

if [[ -z "$OUTPUT_DIR" ]]; then
  usage >&2
  exit 2
fi
if [[ -z "$COMPOSE_PROJECT" ]]; then
  COMPOSE_PROJECT="citeframe-m403-${RUN_ID,,}"
fi
if [[ ! "$COMPOSE_PROJECT" =~ ^citeframe-m403-[a-z0-9][a-z0-9_-]*$ ]]; then
  printf 'm403_project_must_be_isolated project=%s\n' "$COMPOSE_PROJECT" >&2
  exit 2
fi
M403_EXPECT_IMAGE_ENABLED=${M403_EXPECT_IMAGE_ENABLED:-false}
if [[ "$M403_EXPECT_IMAGE_ENABLED" != "true" && "$M403_EXPECT_IMAGE_ENABLED" != "false" ]]; then
  printf 'm403_invalid_image_expectation value=%s expected=true_or_false\n' "$M403_EXPECT_IMAGE_ENABLED" >&2
  exit 2
fi
export M403_EXPECT_IMAGE_ENABLED
OUTPUT_DIR=$(realpath -m "$OUTPUT_DIR")
if [[ -e "$OUTPUT_DIR" ]]; then
  printf 'm403_output_exists path=%s\n' "$OUTPUT_DIR" >&2
  exit 1
fi
mkdir -m 700 -p "$OUTPUT_DIR"

ENV_FILE="$OUTPUT_DIR/.env.deploy"
cat > "$ENV_FILE" <<EOF
POSTGRES_DB=ai_pdf_workspace
POSTGRES_USER=ai_pdf
POSTGRES_PASSWORD=M403-db-${RUN_ID}
MINIO_ROOT_USER=m403minio
MINIO_ROOT_PASSWORD=M403-minio-${RUN_ID}
MINIO_BUCKET=ai-pdf-workspace
AI_PDF_API_IMAGE=ai-pdf-workspace-api:m403-${RUN_ID}
AI_PDF_WORKER_IMAGE=ai-pdf-workspace-worker:m403-${RUN_ID}
AI_PDF_WEB_IMAGE=ai-pdf-workspace-web:m403-${RUN_ID}
AI_PDF_API_INTERNAL_TOKEN=M403-internal-token-${RUN_ID}
AI_PDF_SESSION_SECRET=M403-session-secret-${RUN_ID}-long-enough
AI_PDF_OPENAI_API_KEY=M403-no-network
AI_PDF_EMBEDDING_PROVIDER=ollama
AI_PDF_EMBEDDING_MODEL=qwen3-embedding:0.6b
AI_PDF_EMBEDDING_VERSION=embedding-v1
AI_PDF_OLLAMA_BASE_URL=http://provider-stub:11434
AI_PDF_RETRIEVAL_STRATEGY=hybrid
AI_PDF_RETRIEVAL_CANDIDATE_K=10
AI_PDF_RETRIEVAL_RRF_CONSTANT=60
AI_PDF_GENERATION_PROVIDER=openai
AI_PDF_GENERATION_MODEL=gpt-5.5
AI_PDF_WORKER_METRICS_HOST=0.0.0.0
AI_PDF_WORKER_METRICS_PORT=9101
CADDY_SITE_ADDRESS=:80
CADDY_HTTP_PORT=18080
CADDY_HTTPS_PORT=18443
MINIO_CONSOLE_PORT=19001
EOF
chmod 600 "$ENV_FILE"
ENV_FILE=$(realpath "$ENV_FILE")
COMPOSE_OVERRIDE_FILE="$REPO_ROOT/infra/docker/compose.m403.yml"
export ENV_FILE COMPOSE_PROJECT COMPOSE_OVERRIDE_FILE
validate_common_options

if compose ps -q postgres minio redis api worker web caddy 2>/dev/null | grep -q .; then
  printf 'm403_project_already_exists project=%s\n' "$COMPOSE_PROJECT" >&2
  exit 1
fi

RUN_STATUS=1
cleanup() {
  trap - EXIT INT TERM
  set +e
  compose exec -T api python -c 'import http.client; c=http.client.HTTPConnection("127.0.0.1",8000,timeout=5); c.request("GET","/health/ready"); r=c.getresponse(); print(r.read().decode())' \
    > "$OUTPUT_DIR/final-readiness.json" 2>&1 || true
  compose ps > "$OUTPUT_DIR/final-compose-ps.txt" 2>&1 || true
  compose logs --no-color > "$OUTPUT_DIR/final-compose.log" 2>&1 || true
  cleanup_down_status=0
  compose down --volumes --remove-orphans > "$OUTPUT_DIR/final-down.log" 2>&1 || cleanup_down_status=$?
  container_inspect_status=0
  volume_inspect_status=0
  network_inspect_status=0
  docker ps -a --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.ID}} {{.Names}}' \
    | sort > "$OUTPUT_DIR/final-containers.txt" || container_inspect_status=$?
  docker volume ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}' \
    | sort > "$OUTPUT_DIR/final-volumes.txt" || volume_inspect_status=$?
  docker network ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}' \
    | sort > "$OUTPUT_DIR/final-networks.txt" || network_inspect_status=$?
  cleanup_passed=false
  if [[ "$cleanup_down_status" -eq 0 \
    && "$container_inspect_status" -eq 0 \
    && "$volume_inspect_status" -eq 0 \
    && "$network_inspect_status" -eq 0 \
    && ! -s "$OUTPUT_DIR/final-containers.txt" \
    && ! -s "$OUTPUT_DIR/final-volumes.txt" \
    && ! -s "$OUTPUT_DIR/final-networks.txt" ]]; then
    cleanup_passed=true
  fi
  cleanup_report_status=0
  python3 - "$OUTPUT_DIR" "$cleanup_down_status" "$container_inspect_status" \
    "$volume_inspect_status" "$network_inspect_status" "$cleanup_passed" <<'PY' \
    || cleanup_report_status=$?
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
cleanup = {
    "composeDownExitCode": int(sys.argv[2]),
    "inspectionExitCodes": {
        "containers": int(sys.argv[3]),
        "volumes": int(sys.argv[4]),
        "networks": int(sys.argv[5]),
    },
    "containersRemaining": [line for line in (root / "final-containers.txt").read_text().splitlines() if line],
    "volumesRemaining": [line for line in (root / "final-volumes.txt").read_text().splitlines() if line],
    "networksRemaining": [line for line in (root / "final-networks.txt").read_text().splitlines() if line],
    "passed": sys.argv[6] == "true",
}
(root / "final-cleanup.json").write_text(json.dumps(cleanup, indent=2, sort_keys=True) + "\n")
report_path = root / "report.json"
if report_path.exists():
    report = json.loads(report_path.read_text())
    report["finalCleanup"] = cleanup
    report["releaseGatePassed"] = bool(report.get("releaseGatePassed")) and cleanup["passed"]
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
PY
  if [[ "$RUN_STATUS" -eq 0 \
    && ("$cleanup_passed" != true || "$cleanup_report_status" -ne 0) ]]; then
    RUN_STATUS=1
  fi
  rm -f "$ENV_FILE"
  exit "$RUN_STATUS"
}
trap cleanup EXIT INT TERM

printf 'm403_start project=%s output=%s expect_image_enabled=%s\n' \
  "$COMPOSE_PROJECT" "$OUTPUT_DIR" "$M403_EXPECT_IMAGE_ENABLED"
compose config > "$OUTPUT_DIR/compose-config.yml"
sha256sum "$OUTPUT_DIR/compose-config.yml" > "$OUTPUT_DIR/compose-config.sha256"

compose up -d --build postgres minio redis
wait_for_service_health postgres
wait_for_postgres_sql
wait_for_service_health minio
wait_for_service_health redis
compose build api worker web
compose run --rm -T migration > "$OUTPUT_DIR/migration.log"
compose up -d api worker
for service in api worker; do wait_for_service_health "$service"; done
compose up -d web caddy
for service in web caddy; do wait_for_service_health "$service"; done

compose run --rm -T --no-deps worker python scripts/m403_restore_acceptance.py seed > "$OUTPUT_DIR/state.json"
compose run --rm -T --no-deps worker python scripts/m403_restore_acceptance.py snapshot > "$OUTPUT_DIR/before.json"

PLAYWRIGHT_BASE_URL=http://127.0.0.1:18080 \
PLAYWRIGHT_M403_STATE_PATH="$OUTPUT_DIR/state.json" \
PLAYWRIGHT_M403_PHASE=before \
PLAYWRIGHT_M403_ARTIFACT_DIR="$OUTPUT_DIR" \
  pnpm --dir "$REPO_ROOT/apps/web" exec playwright test e2e/m403-restore.spec.ts \
  > "$OUTPUT_DIR/playwright-before.log"

date +%s%N > "$OUTPUT_DIR/backup-start.ns"
"$SCRIPT_DIR/backup-deployment.sh" \
  --env-file "$ENV_FILE" \
  --project "$COMPOSE_PROJECT" \
  --output-dir "$OUTPUT_DIR/backup" \
  > "$OUTPUT_DIR/backup.log"
date +%s%N > "$OUTPUT_DIR/backup-end.ns"

docker volume ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}' \
  | sort > "$OUTPUT_DIR/volumes-before-down.txt"
docker ps -a --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.ID}} {{.Names}}' \
  | sort > "$OUTPUT_DIR/containers-before-down.txt"
compose down --volumes --remove-orphans > "$OUTPUT_DIR/down.log"
docker volume ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}' \
  | sort > "$OUTPUT_DIR/volumes-after-down.txt"
docker ps -a --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.ID}} {{.Names}}' \
  | sort > "$OUTPUT_DIR/containers-after-down.txt"
if [[ -s "$OUTPUT_DIR/volumes-after-down.txt" || -s "$OUTPUT_DIR/containers-after-down.txt" ]]; then
  printf 'm403_isolated_resources_not_destroyed project=%s\n' "$COMPOSE_PROJECT" >&2
  exit 1
fi

date +%s%N > "$OUTPUT_DIR/restore-start.ns"
"$SCRIPT_DIR/restore-deployment.sh" \
  --env-file "$ENV_FILE" \
  --project "$COMPOSE_PROJECT" \
  --backup-dir "$OUTPUT_DIR/backup" \
  --confirm \
  > "$OUTPUT_DIR/restore.log"
date +%s%N > "$OUTPUT_DIR/restore-end.ns"
for service in postgres minio redis api worker web caddy; do wait_for_service_health "$service"; done
compose run --rm -T --no-deps worker python scripts/m403_restore_acceptance.py snapshot > "$OUTPUT_DIR/after.json"

PLAYWRIGHT_BASE_URL=http://127.0.0.1:18080 \
PLAYWRIGHT_M403_STATE_PATH="$OUTPUT_DIR/state.json" \
PLAYWRIGHT_M403_PHASE=after \
PLAYWRIGHT_M403_ARTIFACT_DIR="$OUTPUT_DIR" \
  pnpm --dir "$REPO_ROOT/apps/web" exec playwright test e2e/m403-restore.spec.ts \
  > "$OUTPUT_DIR/playwright-after.log"

(cd "$REPO_ROOT/apps/worker" && uv run python scripts/m403_restore_acceptance.py verify \
  --before "$OUTPUT_DIR/before.json" \
  --after "$OUTPUT_DIR/after.json" \
  --output "$OUTPUT_DIR/verification.json")

python3 - "$OUTPUT_DIR" "$COMPOSE_PROJECT" <<'PY'
import json
from hashlib import sha256
from pathlib import Path
import sys

root = Path(sys.argv[1])
project = sys.argv[2]
before = json.loads((root / "before.json").read_text())
after = json.loads((root / "after.json").read_text())
verification = json.loads((root / "verification.json").read_text())
state = json.loads((root / "state.json").read_text())
historical_citations = {
    item["id"]: item
    for item in before["rows"]["message_citations"]
    if item["id"] in {
        state["citationIds"]["pdfHistorical"],
        state["citationIds"]["imageHistorical"],
    }
}
regions_by_locator = {}
for region in before["rows"]["spatial_locator_regions"]:
    regions_by_locator.setdefault(region["locator_id"], []).append(region)
for regions in regions_by_locator.values():
    regions.sort(key=lambda item: item["region_order"])
historical_image_pixels = next(
    item["pixelSha256"]
    for item in before["visualReplay"]["images"]
    if item["generation"] == 1
)

def expected_geometry(citation_id):
    locator_id = historical_citations[citation_id]["evidence_locator_id"]
    return [
        {key: region[key] for key in ("x", "y", "width", "height")}
        for region in regions_by_locator.get(locator_id, [])
    ]

def geometry_matches(actual, expected, tolerance=0.002):
    return len(actual) == len(expected) and all(
        all(abs(float(left[key]) - float(right[key])) <= tolerance for key in ("x", "y", "width", "height"))
        for left, right in zip(actual, expected)
    )

def ns(name):
    return int((root / name).read_text().strip())
def elapsed(start, end):
    return round((ns(end) - ns(start)) / 1_000_000, 3)
backup_hashes = {}
for name in ("manifest.env", "SHA256SUMS", "postgres.dump"):
    path = root / "backup" / name
    backup_hashes[name] = sha256(path.read_bytes()).hexdigest()
playwright = {}
for name in ("desktop", "mobile"):
    values = {}
    for phase in ("before", "after"):
        path = root / f"playwright-{phase}-{name}.json"
        values[phase] = json.loads(path.read_text())
    before_results = values["before"]["results"]
    after_results = values["after"]["results"]
    semantic = []
    expected_ids = [state["citationIds"]["pdfHistorical"], state["citationIds"]["imageHistorical"]]
    structure_passed = (
        values["before"]["phase"] == "before"
        and values["after"]["phase"] == "after"
        and values["before"]["viewport"] == name
        and values["after"]["viewport"] == name
        and len(before_results) == len(after_results) == len(expected_ids)
        and [item["citationId"] for item in before_results] == expected_ids
        and [item["citationId"] for item in after_results] == expected_ids
    )
    for before_item, after_item in zip(before_results, after_results):
        citation_id = before_item["citationId"]
        expected_regions = expected_geometry(citation_id)
        region_oracle_passed = (
            geometry_matches(before_item["regionGeometry"], expected_regions)
            and geometry_matches(after_item["regionGeometry"], expected_regions)
        )
        image_pixel_oracle_passed = (
            before_item["kind"] != "image"
            or (
                before_item["pixels"]["pixelSha256"] == historical_image_pixels
                and after_item["pixels"]["pixelSha256"] == historical_image_pixels
            )
        )
        semantic.append({
            "citationId": citation_id,
            "kind": before_item["kind"],
            "beforePixels": before_item["pixels"],
            "afterPixels": after_item["pixels"],
            "beforeRegionGeometry": before_item["regionGeometry"],
            "afterRegionGeometry": after_item["regionGeometry"],
            "expectedRegionGeometry": expected_regions,
            "regionOraclePassed": region_oracle_passed,
            "expectedImagePixelSha256": historical_image_pixels if before_item["kind"] == "image" else None,
            "imagePixelOraclePassed": image_pixel_oracle_passed,
            "passed": before_item["citationId"] == after_item["citationId"] and before_item["kind"] == after_item["kind"] and before_item["pixels"] == after_item["pixels"] and before_item["regionGeometry"] == after_item["regionGeometry"] and region_oracle_passed and image_pixel_oracle_passed,
        })
    playwright[name] = {"structurePassed": structure_passed, "semantic": semantic, "passed": structure_passed and all(item["passed"] for item in semantic)}
report = {
    "schemaVersion": "m403-restore-report-v2",
    "project": project,
    "backup": {"hashes": backup_hashes, "durationMs": elapsed("backup-start.ns", "backup-end.ns")},
    "restore": {"durationMs": elapsed("restore-start.ns", "restore-end.ns"), "destroyedVolumes": not (root / "volumes-after-down.txt").read_text().strip(), "destroyedContainers": not (root / "containers-after-down.txt").read_text().strip()},
    "before": {"semanticSha256": before["semanticSha256"], "objectCount": before["objectCount"], "tableCounts": before["tableCounts"]},
    "after": {"semanticSha256": after["semanticSha256"], "objectCount": after["objectCount"], "tableCounts": after["tableCounts"]},
    "verification": verification,
    "playwright": playwright,
    "releaseGatePassed": verification["passed"] and all(item["passed"] for item in playwright.values()),
}
(root / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
PY

if ! python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1]))["releaseGatePassed"] else 1)' "$OUTPUT_DIR/report.json"; then
  printf 'm403_release_gate_failed report=%s\n' "$OUTPUT_DIR/report.json" >&2
  exit 1
fi

RUN_STATUS=0
printf 'm403_complete report=%s\n' "$OUTPUT_DIR/report.json"
