#!/usr/bin/env bash

set -euo pipefail
umask 077

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
# shellcheck source=compose-common.sh
source "$SCRIPT_DIR/compose-common.sh"

usage() {
  cat <<'EOF'
Usage: run-v5b-document-acceptance.sh --output-dir PATH [--project citeframe-v5b-NAME]

Builds API/Worker/Web images, runs the Markdown Document browser flow through
Caddy, performs the production backup/empty-deployment restore, replays the
browser flow after restore, and removes the isolated Compose project and images.
EOF
}

OUTPUT_DIR=""
COMPOSE_PROJECT=""
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
RUN_TOKEN="${RUN_ID,,}-$$"

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
  COMPOSE_PROJECT="citeframe-v5b-$RUN_TOKEN"
fi
if [[ ! "$COMPOSE_PROJECT" =~ ^citeframe-v5b-[a-z0-9][a-z0-9_-]*$ ]]; then
  printf 'v5b_project_must_be_isolated project=%s\n' "$COMPOSE_PROJECT" >&2
  exit 2
fi
OUTPUT_DIR=$(realpath -m "$OUTPUT_DIR")
if [[ -e "$OUTPUT_DIR" ]]; then
  printf 'v5b_output_exists path=%s\n' "$OUTPUT_DIR" >&2
  exit 1
fi
mkdir -m 700 -p "$OUTPUT_DIR"
mkdir -m 700 -p "$OUTPUT_DIR/browser-before" "$OUTPUT_DIR/browser-after"

POSTGRES_PASSWORD="V5B-db-$RUN_TOKEN"
MINIO_ROOT_USER="v5bminio${RANDOM}"
MINIO_ROOT_PASSWORD="V5B-minio-$RUN_TOKEN"
API_INTERNAL_TOKEN="V5B-internal-token-$RUN_TOKEN"
SESSION_SECRET="V5B-session-secret-$RUN_TOKEN-long-enough"
OPENAI_API_KEY="V5B-private-no-network-$RUN_TOKEN"
BROWSER_EMAIL="v5b-browser-$RUN_TOKEN@example.com"
BROWSER_PASSWORD="V5B-browser-password-$RUN_TOKEN-long"

pick_free_port() {
  python3 -c 'import socket; s=socket.socket(); s.bind(("0.0.0.0", 0)); print(s.getsockname()[1]); s.close()'
}

CADDY_HTTP_PORT=$(pick_free_port)
CADDY_HTTPS_PORT=$(pick_free_port)
while [[ "$CADDY_HTTPS_PORT" == "$CADDY_HTTP_PORT" ]]; do CADDY_HTTPS_PORT=$(pick_free_port); done
MINIO_CONSOLE_PORT=$(pick_free_port)
while [[ "$MINIO_CONSOLE_PORT" == "$CADDY_HTTP_PORT" || "$MINIO_CONSOLE_PORT" == "$CADDY_HTTPS_PORT" ]]; do
  MINIO_CONSOLE_PORT=$(pick_free_port)
done

API_IMAGE="ai-pdf-workspace-api:v5b-$RUN_TOKEN"
WORKER_IMAGE="ai-pdf-workspace-worker:v5b-$RUN_TOKEN"
WEB_IMAGE="ai-pdf-workspace-web:v5b-$RUN_TOKEN"
ENV_FILE="$OUTPUT_DIR/.env.deploy"
cat > "$ENV_FILE" <<EOF
POSTGRES_DB=ai_pdf_workspace
POSTGRES_USER=ai_pdf
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
MINIO_ROOT_USER=$MINIO_ROOT_USER
MINIO_ROOT_PASSWORD=$MINIO_ROOT_PASSWORD
MINIO_BUCKET=ai-pdf-workspace
AI_PDF_API_IMAGE=$API_IMAGE
AI_PDF_WORKER_IMAGE=$WORKER_IMAGE
AI_PDF_WEB_IMAGE=$WEB_IMAGE
AI_PDF_API_INTERNAL_TOKEN=$API_INTERNAL_TOKEN
AI_PDF_SESSION_SECRET=$SESSION_SECRET
AI_PDF_OPENAI_API_KEY=$OPENAI_API_KEY
AI_PDF_OPENAI_API_BASE=http://provider-stub:18082/v1
AI_PDF_EMBEDDING_PROVIDER=ollama
AI_PDF_EMBEDDING_MODEL=qwen3-embedding:0.6b
AI_PDF_EMBEDDING_VERSION=embedding-v1
AI_PDF_OLLAMA_BASE_URL=http://provider-stub:18082
AI_PDF_RETRIEVAL_STRATEGY=hybrid
AI_PDF_RETRIEVAL_CANDIDATE_K=10
AI_PDF_RETRIEVAL_RRF_CONSTANT=60
AI_PDF_GENERATION_PROVIDER=openai
AI_PDF_GENERATION_MODEL=gpt-5.5
AI_PDF_IMAGE_CAPTION_PROVIDER=openai
AI_PDF_IMAGE_CAPTION_MODEL=gpt-5.5
AI_PDF_IMAGE_CAPTION_VERSION=image-caption-v1
AI_PDF_IMAGE_CAPTION_DETAIL=high
AI_PDF_IMAGE_CAPTION_TIMEOUT_SECONDS=120
AI_PDF_IMAGE_CAPTION_MAX_OUTPUT_TOKENS=320
AI_PDF_WORKER_METRICS_HOST=0.0.0.0
AI_PDF_WORKER_METRICS_PORT=9101
CADDY_SITE_ADDRESS=:80
CADDY_BIND_ADDRESS=127.0.0.1
CADDY_HTTP_PORT=$CADDY_HTTP_PORT
CADDY_HTTPS_PORT=$CADDY_HTTPS_PORT
MINIO_CONSOLE_PORT=$MINIO_CONSOLE_PORT
EOF
chmod 600 "$ENV_FILE"
ENV_FILE=$(realpath "$ENV_FILE")
COMPOSE_OVERRIDE_FILE="$REPO_ROOT/infra/docker/compose.v5b.yml"
export ENV_FILE COMPOSE_PROJECT COMPOSE_OVERRIDE_FILE

RUN_STATUS=1
OWNS_PROJECT=false

write_redacted_compose_config() {
  compose config | \
    V5B_SECRET_POSTGRES="$POSTGRES_PASSWORD" \
    V5B_SECRET_MINIO_USER="$MINIO_ROOT_USER" \
    V5B_SECRET_MINIO_PASSWORD="$MINIO_ROOT_PASSWORD" \
    V5B_SECRET_INTERNAL_TOKEN="$API_INTERNAL_TOKEN" \
    V5B_SECRET_SESSION="$SESSION_SECRET" \
    V5B_SECRET_OPENAI="$OPENAI_API_KEY" \
    V5B_SECRET_BROWSER_PASSWORD="$BROWSER_PASSWORD" \
    python3 -c '
import os
import sys
payload = sys.stdin.read()
for key in (
    "V5B_SECRET_POSTGRES", "V5B_SECRET_MINIO_USER", "V5B_SECRET_MINIO_PASSWORD",
    "V5B_SECRET_INTERNAL_TOKEN", "V5B_SECRET_SESSION", "V5B_SECRET_OPENAI",
    "V5B_SECRET_BROWSER_PASSWORD",
):
    value = os.environ.get(key)
    if value:
        payload = payload.replace(value, "<redacted>")
payload = payload.replace("v5b-browser-", "<redacted-browser-user>-")
payload = payload.replace("v5b-private-deterministic-key", "<redacted>")
sys.stdout.write(payload)
' > "$OUTPUT_DIR/compose-config.yml"
}

record_image_manifest() {
  python3 - "$OUTPUT_DIR/image-manifest.json" "$API_IMAGE" "$WORKER_IMAGE" "$WEB_IMAGE" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

output = Path(sys.argv[1])
images = []
for tag in sys.argv[2:]:
    payload = json.loads(subprocess.check_output(["docker", "image", "inspect", tag], text=True))[0]
    images.append({
        "tag": tag,
        "id": payload["Id"],
        "created": payload.get("Created"),
        "size": payload.get("Size"),
        "repoTags": payload.get("RepoTags", []),
    })
output.write_text(json.dumps({"schemaVersion": "v5b-built-image-manifest-v1", "images": images}, indent=2) + "\n")
PY
}

record_runtime_manifest() {
  local phase=$1
  python3 - "$OUTPUT_DIR/runtime-containers-$phase.json" "$API_IMAGE" "$WORKER_IMAGE" "$WEB_IMAGE" \
    "$(compose ps -q api)" "$(compose ps -q worker)" "$(compose ps -q web)" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

output = Path(sys.argv[1])
expected_tags = sys.argv[2:5]
container_ids = sys.argv[5:8]
services = ("api", "worker", "web")
containers = []
for service, expected_tag, container_id in zip(services, expected_tags, container_ids, strict=True):
    if not container_id:
        raise SystemExit(f"missing running container for {service}")
    payload = json.loads(
        subprocess.check_output(["docker", "container", "inspect", container_id], text=True)
    )[0]
    health = payload.get("State", {}).get("Health", {}).get("Status")
    containers.append(
        {
            "service": service,
            "containerId": payload["Id"],
            "expectedImageTag": expected_tag,
            "configuredImage": payload.get("Config", {}).get("Image"),
            "resolvedImageId": payload.get("Image"),
            "status": payload.get("State", {}).get("Status"),
            "health": health,
            "command": payload.get("Config", {}).get("Cmd"),
            "entrypoint": payload.get("Config", {}).get("Entrypoint"),
        }
    )
output.write_text(
    json.dumps(
        {"schemaVersion": "v5b-runtime-container-manifest-v1", "containers": containers},
        indent=2,
    )
    + "\n"
)
PY
}

worker_run() {
  compose run --rm -T --no-deps --user "$(id -u):$(id -g)" \
    -v "$OUTPUT_DIR:/tmp/v5b-output:rw" \
    "$@"
}

run_browser() {
  local phase=$1
  local artifact_dir="$OUTPUT_DIR/browser-$phase"
  set +e
  PLAYWRIGHT_STANDALONE_SERVER=1 \
  PLAYWRIGHT_BASE_URL="http://localhost:$CADDY_HTTP_PORT" \
  PLAYWRIGHT_V5B_DOCUMENT_STATE_PATH="$OUTPUT_DIR/browser-state.json" \
  PLAYWRIGHT_V5B_DOCUMENT_ARTIFACT_DIR="$artifact_dir" \
    pnpm --dir "$REPO_ROOT/apps/web" exec playwright test \
      e2e/v5b-document-production-start.spec.ts \
      > "$artifact_dir/playwright.log" 2>&1
  local status=$?
  set -e
  printf '%s\n' "$status" > "$artifact_dir/exit-code"
  return "$status"
}

cleanup() {
  trap - EXIT INT TERM
  set +e
  if [[ "$OWNS_PROJECT" == true ]]; then
    compose ps > "$OUTPUT_DIR/final-compose-ps.txt" 2>&1
    compose logs --no-color api > "$OUTPUT_DIR/final-api.log" 2>&1
    compose logs --no-color worker > "$OUTPUT_DIR/final-worker.log" 2>&1
    compose logs --no-color provider-stub > "$OUTPUT_DIR/final-provider.log" 2>&1
    compose logs --no-color web > "$OUTPUT_DIR/final-web.log" 2>&1
    compose logs --no-color caddy > "$OUTPUT_DIR/final-caddy.log" 2>&1
  fi
  cleanup_down_status=0
  if [[ "$OWNS_PROJECT" == true ]]; then
    compose down --volumes --remove-orphans > "$OUTPUT_DIR/final-down.log" 2>&1 || cleanup_down_status=$?
  else
    : > "$OUTPUT_DIR/final-down.log"
  fi
  docker ps -a --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.ID}} {{.Names}}' | sort > "$OUTPUT_DIR/final-containers.txt"
  docker volume ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}' | sort > "$OUTPUT_DIR/final-volumes.txt"
  docker network ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}' | sort > "$OUTPUT_DIR/final-networks.txt"
  image_remove_status=0
  docker image rm "$API_IMAGE" "$WORKER_IMAGE" "$WEB_IMAGE" > "$OUTPUT_DIR/final-image-remove.log" 2>&1 || image_remove_status=$?
  image_residue_status=0
  for generated_image in "$API_IMAGE" "$WORKER_IMAGE" "$WEB_IMAGE"; do
    if docker image inspect "$generated_image" > /dev/null 2>&1; then
      image_residue_status=1
    fi
  done
  rm -f "$ENV_FILE" "$OUTPUT_DIR/browser-state.json"
  env_removed=false
  [[ ! -e "$ENV_FILE" ]] && env_removed=true
  cleanup_passed=false
  [[ "$cleanup_down_status" -eq 0 \
    && ! -s "$OUTPUT_DIR/final-containers.txt" \
    && ! -s "$OUTPUT_DIR/final-volumes.txt" \
    && ! -s "$OUTPUT_DIR/final-networks.txt" \
    && "$image_remove_status" -eq 0 \
    && "$image_residue_status" -eq 0 \
    && "$env_removed" == true ]] && cleanup_passed=true
  python3 - "$OUTPUT_DIR" "$cleanup_down_status" "$image_remove_status" "$image_residue_status" "$env_removed" "$cleanup_passed" <<'PY'
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
cleanup = {
    "composeDownExitCode": int(sys.argv[2]),
    "imageRemoveExitCode": int(sys.argv[3]),
    "imageResidueCheckExitCode": int(sys.argv[4]),
    "containersRemaining": [x for x in (root / "final-containers.txt").read_text().splitlines() if x],
    "volumesRemaining": [x for x in (root / "final-volumes.txt").read_text().splitlines() if x],
    "networksRemaining": [x for x in (root / "final-networks.txt").read_text().splitlines() if x],
    "envRemoved": sys.argv[5] == "true",
    "passed": sys.argv[6] == "true",
}
(root / "cleanup.json").write_text(json.dumps(cleanup, indent=2, sort_keys=True) + "\n")
report_path = root / "report.json"
if report_path.exists():
    report = json.loads(report_path.read_text())
    report["cleanup"] = cleanup
    report["releaseGatePassed"] = report.get("deploymentGate") == "pass" and cleanup["passed"]
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
PY
  # The generated report is updated below even when an earlier phase fails.
  if [[ "$RUN_STATUS" -eq 0 && "$cleanup_passed" != true ]]; then RUN_STATUS=1; fi
  exit "$RUN_STATUS"
}
trap cleanup EXIT INT TERM

validate_common_options
require_command uv
require_command pnpm

if compose ps -q postgres minio redis provider-stub api worker web caddy 2>/dev/null | grep -q .; then
  printf 'v5b_project_already_exists project=%s\n' "$COMPOSE_PROJECT" >&2
  exit 1
fi
OWNS_PROJECT=true

printf 'v5b_deployment_start project=%s output=%s\n' "$COMPOSE_PROJECT" "$OUTPUT_DIR"
write_redacted_compose_config
sha256sum "$OUTPUT_DIR/compose-config.yml" > "$OUTPUT_DIR/compose-config.sha256"

compose build api worker web > "$OUTPUT_DIR/build.log" 2>&1
record_image_manifest
compose up -d postgres minio redis provider-stub
wait_for_service_health postgres
wait_for_postgres_sql
wait_for_service_health minio
wait_for_service_health redis
wait_for_service_health provider-stub
compose run --rm -T migration > "$OUTPUT_DIR/migration.log" 2>&1
compose up -d api worker web caddy
for service in api worker web caddy; do wait_for_service_health "$service"; done
record_runtime_manifest before

worker_run \
  -v "$REPO_ROOT/docs/fixtures/document-modality:/tmp/v5b-fixture:ro" \
  -e "V5B_BROWSER_EMAIL=$BROWSER_EMAIL" \
  -e "V5B_BROWSER_PASSWORD=$BROWSER_PASSWORD" \
  -e V5B_SEED_API_BASE_URL=http://api:8000 \
  worker python scripts/v5b_document_deployment_seed.py \
  --fixture /tmp/v5b-fixture/markdown-note.md \
  --state /tmp/v5b-output/browser-state.json \
  > "$OUTPUT_DIR/seed.json"

run_browser before
BEFORE_BROWSER_STATUS=$(cat "$OUTPUT_DIR/browser-before/exit-code")
[[ "$BEFORE_BROWSER_STATUS" == 0 ]]

SEED_STATE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["workspaceId"] + " " + json.load(open(sys.argv[1]))["documentAssetId"])' "$OUTPUT_DIR/browser-state.json")
V5B_WORKSPACE_ID=${SEED_STATE%% *}
V5B_ASSET_ID=${SEED_STATE##* }
BROWSER_ASSET_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["assetId"])' "$OUTPUT_DIR/browser-before/production-start-upload.json")
BROWSER_ASSET_WORKSPACE_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["jobWorkspaceId"])' "$OUTPUT_DIR/browser-before/production-start-upload.json")
[[ "$BROWSER_ASSET_WORKSPACE_ID" == "$V5B_WORKSPACE_ID" ]]
[[ "$BROWSER_ASSET_ID" != "$V5B_ASSET_ID" ]]
worker_run \
  -e "V5B_WORKSPACE_ID=$V5B_WORKSPACE_ID" \
  -e "V5B_ASSET_ID=$V5B_ASSET_ID" \
  worker python scripts/v5b_document_restore_acceptance.py snapshot \
  --mode live --output /tmp/v5b-output/before.json
worker_run \
  -e "V5B_WORKSPACE_ID=$V5B_WORKSPACE_ID" \
  -e "V5B_ASSET_ID=$BROWSER_ASSET_ID" \
  worker python scripts/v5b_document_restore_acceptance.py snapshot \
  --mode live --allow-empty-evidence-links --output /tmp/v5b-output/browser-asset-before.json

BACKUP_START_NS=$(date +%s%N)
printf '%s\n' "$BACKUP_START_NS" > "$OUTPUT_DIR/backup-start.ns"
"$SCRIPT_DIR/backup-deployment.sh" \
  --env-file "$ENV_FILE" --project "$COMPOSE_PROJECT" \
  --output-dir "$OUTPUT_DIR/backup" > "$OUTPUT_DIR/backup.log" 2>&1
printf '%s\n' "$(date +%s%N)" > "$OUTPUT_DIR/backup-end.ns"

compose down --volumes --remove-orphans > "$OUTPUT_DIR/down-before-restore.log" 2>&1
docker ps -a --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.ID}} {{.Names}}' | sort > "$OUTPUT_DIR/containers-after-down.txt"
docker volume ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}' | sort > "$OUTPUT_DIR/volumes-after-down.txt"
docker network ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}' | sort > "$OUTPUT_DIR/networks-after-down.txt"
[[ ! -s "$OUTPUT_DIR/containers-after-down.txt" && ! -s "$OUTPUT_DIR/volumes-after-down.txt" && ! -s "$OUTPUT_DIR/networks-after-down.txt" ]]

printf '%s\n' "$(date +%s%N)" > "$OUTPUT_DIR/restore-start.ns"
"$SCRIPT_DIR/restore-deployment.sh" \
  --env-file "$ENV_FILE" --project "$COMPOSE_PROJECT" \
  --backup-dir "$OUTPUT_DIR/backup" --confirm > "$OUTPUT_DIR/restore.log" 2>&1
printf '%s\n' "$(date +%s%N)" > "$OUTPUT_DIR/restore-end.ns"
for service in postgres minio redis provider-stub api worker web caddy; do wait_for_service_health "$service"; done
record_runtime_manifest after

worker_run \
  -e "V5B_WORKSPACE_ID=$V5B_WORKSPACE_ID" \
  -e "V5B_ASSET_ID=$V5B_ASSET_ID" \
  worker python scripts/v5b_document_restore_acceptance.py snapshot \
  --mode live --output /tmp/v5b-output/after.json
worker_run \
  -e "V5B_WORKSPACE_ID=$BROWSER_ASSET_WORKSPACE_ID" \
  -e "V5B_ASSET_ID=$BROWSER_ASSET_ID" \
  worker python scripts/v5b_document_restore_acceptance.py snapshot \
  --mode live --allow-empty-evidence-links --output /tmp/v5b-output/browser-asset-after.json
worker_run \
  -e "V5B_WORKSPACE_ID=$V5B_WORKSPACE_ID" \
  -e "V5B_ASSET_ID=$V5B_ASSET_ID" \
  worker python scripts/v5b_document_restore_acceptance.py verify \
  --before /tmp/v5b-output/before.json \
  --after /tmp/v5b-output/after.json \
  --output /tmp/v5b-output/verification.json
worker_run \
  -e "V5B_WORKSPACE_ID=$BROWSER_ASSET_WORKSPACE_ID" \
  -e "V5B_ASSET_ID=$BROWSER_ASSET_ID" \
  worker python scripts/v5b_document_restore_acceptance.py verify \
  --before /tmp/v5b-output/browser-asset-before.json \
  --after /tmp/v5b-output/browser-asset-after.json \
  --output /tmp/v5b-output/browser-asset-verification.json

run_browser after
AFTER_BROWSER_STATUS=$(cat "$OUTPUT_DIR/browser-after/exit-code")
[[ "$AFTER_BROWSER_STATUS" == 0 ]]

python3 - "$OUTPUT_DIR" "$COMPOSE_PROJECT" "$CADDY_HTTP_PORT" "$BROWSER_EMAIL" "$API_IMAGE" "$WORKER_IMAGE" "$WEB_IMAGE" <<'PY'
import json
from hashlib import sha256
from pathlib import Path
import sys

root = Path(sys.argv[1])
project = sys.argv[2]
port = int(sys.argv[3])
email = sys.argv[4]
expected_image_tags = list(sys.argv[5:8])

def load(name):
    return json.loads((root / name).read_text())

def file_sha(path):
    return sha256(path.read_bytes()).hexdigest()

def image_ids():
    return {entry["tag"]: entry["id"] for entry in load("image-manifest.json")["images"]}

verification = load("verification.json")
browser_asset_verification = load("browser-asset-verification.json")
seed = load("seed.json")
browser_upload = load("browser-before/production-start-upload.json")
image_manifest = load("image-manifest.json")
before = load("before.json")
after = load("after.json")
browser_asset_before = load("browser-asset-before.json")
browser_asset_after = load("browser-asset-after.json")
runtime_before = load("runtime-containers-before.json")
runtime_after = load("runtime-containers-after.json")
state = load("browser-state.json")
expected_browser_artifacts = {
    f"browser-{phase}/{name}": (root / f"browser-{phase}/{name}").is_file()
    and (root / f"browser-{phase}/{name}").stat().st_size > 0
    for phase in ("before", "after")
    for name in (
        "production-start-upload.json",
        "document-historical-citation.json",
        "document-historical-citation.png",
        "standalone-entry-check.json",
    )
}
image_tags = [entry.get("tag", "") for entry in image_manifest.get("images", [])]
built_image_ids = image_ids()

def runtime_manifest_matches(manifest):
    containers = manifest.get("containers", [])
    if len(containers) != 3:
        return False
    by_service = {entry.get("service"): entry for entry in containers}
    for service in ("api", "worker", "web"):
        entry = by_service.get(service)
        if not entry:
            return False
        expected_tag = entry.get("expectedImageTag")
        health_ok = entry.get("health") == "healthy" or (
            service == "worker" and entry.get("health") is None
        )
        if (
            entry.get("configuredImage") != expected_tag
            or entry.get("resolvedImageId") != built_image_ids.get(expected_tag)
            or entry.get("status") != "running"
            or not health_ok
        ):
            return False
    return by_service["web"].get("command") == ["node", "apps/web/server.js"]

checks = {
    "builtImagesRecorded": len(image_manifest.get("images", [])) == 3
    and all(entry.get("id") for entry in image_manifest.get("images", []))
    and sorted(image_tags) == sorted(expected_image_tags),
    "runtimeContainersBeforeMatchBuiltImages": runtime_manifest_matches(runtime_before),
    "runtimeContainersAfterMatchBuiltImages": runtime_manifest_matches(runtime_after),
    "documentSeedSucceeded": seed.get("sourceAvailable") is True,
    "seedFixtureDigest": seed.get("sourceSha256") == seed.get("fixtureSourceSha256"),
    "seedStateIdentity": (
        state.get("workspaceId") == seed.get("workspaceId")
        and state.get("documentAssetId") == seed.get("assetId")
        and state.get("citationId") == seed.get("citationId")
    ),
    "restoreVerification": verification.get("passed") is True,
    "restoreWasLivePostgresMinio": verification.get("livePostgresMinio") is True,
    "semanticIdentity": before.get("semanticSha256") == after.get("semanticSha256"),
    "browserAssetIdentity": (
        browser_upload.get("jobStatus") == "succeeded"
        and browser_upload.get("jobWorkspaceId") == seed.get("workspaceId")
        and browser_asset_before.get("workspaceId") == seed.get("workspaceId")
        and browser_asset_before.get("assetId") == browser_upload.get("assetId")
        and browser_asset_after.get("workspaceId") == seed.get("workspaceId")
        and browser_asset_after.get("assetId") == browser_upload.get("assetId")
    ),
    "browserAssetRestoreVerification": browser_asset_verification.get("passed") is True,
    "browserAssetRestoreWasLivePostgresMinio": (
        browser_asset_verification.get("livePostgresMinio") is True
    ),
    "browserAssetSemanticIdentity": (
        browser_asset_before.get("semanticSha256") == browser_asset_after.get("semanticSha256")
    ),
    "backupIncludesBothDocumentAssets": (
        f"assets/{seed.get('assetId')}/" in (root / "backup/SHA256SUMS").read_text()
        and f"assets/{browser_upload.get('assetId')}/" in (root / "backup/SHA256SUMS").read_text()
    ),
    "browserBeforePassed": (root / "browser-before/exit-code").read_text().strip() == "0",
    "browserAfterPassed": (root / "browser-after/exit-code").read_text().strip() == "0",
    "browserArtifactsComplete": all(expected_browser_artifacts.values()),
    "deploymentBaseURL": port > 0,
}
report = {
    "schemaVersion": "v5b-document-deployment-acceptance-v1",
    "project": project,
    "runtimeKind": "isolated-compose-built-images",
    "browser": {
        "baseURL": f"http://localhost:{port}",
        "beforeExitCode": int((root / "browser-before/exit-code").read_text()),
        "afterExitCode": int((root / "browser-after/exit-code").read_text()),
        "email": email,
        "stateSha256": file_sha(root / "browser-state.json"),
        "beforePlaywrightSha256": file_sha(root / "browser-before/playwright.log"),
        "afterPlaywrightSha256": file_sha(root / "browser-after/playwright.log"),
        "artifactFiles": expected_browser_artifacts,
    },
    "builtImages": image_manifest,
    "imageIds": built_image_ids,
    "runtimeContainers": {
        "before": runtime_before,
        "after": runtime_after,
    },
    "seed": seed,
    "restore": {
        "beforeSha256": file_sha(root / "before.json"),
        "afterSha256": file_sha(root / "after.json"),
        "verificationSha256": file_sha(root / "verification.json"),
        "semanticSha256": after.get("semanticSha256"),
        "passed": verification.get("passed") is True,
        "documentAssets": {
            "seed": {
                "assetId": seed.get("assetId"),
                "beforeSha256": file_sha(root / "before.json"),
                "afterSha256": file_sha(root / "after.json"),
                "verificationSha256": file_sha(root / "verification.json"),
                "semanticSha256": after.get("semanticSha256"),
                "passed": verification.get("passed") is True,
            },
            "browserUpload": {
                "assetId": browser_upload.get("assetId"),
                "beforeSha256": file_sha(root / "browser-asset-before.json"),
                "afterSha256": file_sha(root / "browser-asset-after.json"),
                "verificationSha256": file_sha(root / "browser-asset-verification.json"),
                "semanticSha256": browser_asset_after.get("semanticSha256"),
                "allowEmptyEvidenceLinks": True,
                "passed": browser_asset_verification.get("passed") is True,
            },
        },
    },
    "artifactSha256": {
        "composeConfig": file_sha(root / "compose-config.yml"),
        "seed": file_sha(root / "seed.json"),
        "before": file_sha(root / "before.json"),
        "after": file_sha(root / "after.json"),
        "verification": file_sha(root / "verification.json"),
        "browserAssetBefore": file_sha(root / "browser-asset-before.json"),
        "browserAssetAfter": file_sha(root / "browser-asset-after.json"),
        "browserAssetVerification": file_sha(root / "browser-asset-verification.json"),
        "runtimeContainersBefore": file_sha(root / "runtime-containers-before.json"),
        "runtimeContainersAfter": file_sha(root / "runtime-containers-after.json"),
        "backupManifest": file_sha(root / "backup/manifest.env"),
        "backupChecksums": file_sha(root / "backup/SHA256SUMS"),
    },
    "engineeringChecks": checks,
    "deploymentGate": "pass" if all(checks.values()) else "fail",
    "modelQualityGate": "not_evaluable",
    "modelQualityReason": "scripted_provider_is_engineering_evidence_only",
    "cleanup": None,
    "releaseGatePassed": False,
}
(root / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
if report["deploymentGate"] != "pass":
    raise SystemExit("v5b deployment gate failed: " + ",".join(k for k, v in checks.items() if not v))
PY

RUN_STATUS=0
printf 'v5b_document_deployment_complete report=%s cleanup=pending\n' "$OUTPUT_DIR/report.json"
