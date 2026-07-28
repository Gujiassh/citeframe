#!/usr/bin/env bash

set -euo pipefail
umask 077

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
# shellcheck source=compose-common.sh
source "$SCRIPT_DIR/compose-common.sh"

usage() {
  cat <<'EOF'
Usage: run-r800-acceptance.sh --output-dir PATH [--project citeframe-r800-NAME]

Runs the isolated R800 API/Worker/PostgreSQL/MinIO engineering acceptance,
then exercises the production backup and empty-deployment restore path. The
Compose project and all of its containers, volumes, networks, and secret env
file are removed before the command returns.
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
  COMPOSE_PROJECT="citeframe-r800-$RUN_TOKEN"
fi
if [[ ! "$COMPOSE_PROJECT" =~ ^citeframe-r800-[a-z0-9][a-z0-9_-]*$ ]]; then
  printf 'r800_project_must_be_isolated project=%s\n' "$COMPOSE_PROJECT" >&2
  exit 2
fi

OUTPUT_DIR=$(realpath -m "$OUTPUT_DIR")
if [[ -e "$OUTPUT_DIR" ]]; then
  printf 'r800_output_exists path=%s\n' "$OUTPUT_DIR" >&2
  exit 1
fi
mkdir -m 700 -p "$OUTPUT_DIR"

# Every value is single-line, URL-safe, and scoped to this disposable project.
POSTGRES_PASSWORD="R800-db-$RUN_TOKEN"
MINIO_ROOT_USER="r800minio${RANDOM}"
MINIO_ROOT_PASSWORD="R800-minio-$RUN_TOKEN"
API_INTERNAL_TOKEN="R800-internal-token-$RUN_TOKEN"
SESSION_SECRET="R800-session-secret-$RUN_TOKEN-long-enough"
OPENAI_API_KEY="R800-private-no-network-$RUN_TOKEN"
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
ENV_FILE="$OUTPUT_DIR/.env.deploy"
cat > "$ENV_FILE" <<EOF
POSTGRES_DB=ai_pdf_workspace
POSTGRES_USER=ai_pdf
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
MINIO_ROOT_USER=$MINIO_ROOT_USER
MINIO_ROOT_PASSWORD=$MINIO_ROOT_PASSWORD
MINIO_BUCKET=ai-pdf-workspace
AI_PDF_API_IMAGE=ai-pdf-workspace-api:r800-$RUN_TOKEN
AI_PDF_WORKER_IMAGE=ai-pdf-workspace-worker:r800-$RUN_TOKEN
AI_PDF_WEB_IMAGE=ai-pdf-workspace-web:r800-$RUN_TOKEN
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
CADDY_HTTP_PORT=$CADDY_HTTP_PORT
CADDY_HTTPS_PORT=$CADDY_HTTPS_PORT
MINIO_CONSOLE_PORT=$MINIO_CONSOLE_PORT
EOF
chmod 600 "$ENV_FILE"
ENV_FILE=$(realpath "$ENV_FILE")
COMPOSE_OVERRIDE_FILE="$REPO_ROOT/infra/docker/compose.r800.yml"
export ENV_FILE COMPOSE_PROJECT COMPOSE_OVERRIDE_FILE

RUN_STATUS=1
OWNS_PROJECT=false

capture_provider_timeline() {
  local output=$1
  compose exec -T provider-stub python -c \
    'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:18082/__r800__/control/timeline", timeout=5).read().decode())' \
    > "$output"
}

write_redacted_compose_config() {
  compose config | \
    R800_SECRET_POSTGRES="$POSTGRES_PASSWORD" \
    R800_SECRET_MINIO_USER="$MINIO_ROOT_USER" \
    R800_SECRET_MINIO_PASSWORD="$MINIO_ROOT_PASSWORD" \
    R800_SECRET_INTERNAL_TOKEN="$API_INTERNAL_TOKEN" \
    R800_SECRET_SESSION="$SESSION_SECRET" \
    R800_SECRET_OPENAI="$OPENAI_API_KEY" \
    python3 -c '
import os
import sys

payload = sys.stdin.read()
for key in (
    "R800_SECRET_POSTGRES",
    "R800_SECRET_MINIO_USER",
    "R800_SECRET_MINIO_PASSWORD",
    "R800_SECRET_INTERNAL_TOKEN",
    "R800_SECRET_SESSION",
    "R800_SECRET_OPENAI",
):
    value = os.environ.get(key)
    if value:
        payload = payload.replace(value, "<redacted>")
payload = payload.replace("r800-private-deterministic-key", "<redacted>")
sys.stdout.write(payload)
' > "$OUTPUT_DIR/compose-config.yml"
}

cleanup() {
  trap - EXIT INT TERM
  set +e

  if [[ "$OWNS_PROJECT" == true ]]; then
    compose exec -T api python -c \
      'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=5).read().decode())' \
      > "$OUTPUT_DIR/final-api-readiness.json" 2>&1 || true
    capture_provider_timeline "$OUTPUT_DIR/final-provider-timeline.json" 2>/dev/null || true
    compose ps > "$OUTPUT_DIR/final-compose-ps.txt" 2>&1 || true
    compose logs --no-color api > "$OUTPUT_DIR/final-api.log" 2>&1 || true
    compose logs --no-color worker > "$OUTPUT_DIR/final-worker.log" 2>&1 || true
    compose logs --no-color provider-stub > "$OUTPUT_DIR/final-provider.log" 2>&1 || true
    cleanup_down_status=0
    compose down --volumes --remove-orphans > "$OUTPUT_DIR/final-down.log" 2>&1 || cleanup_down_status=$?
  else
    cleanup_down_status=0
    : > "$OUTPUT_DIR/final-compose-ps.txt"
    : > "$OUTPUT_DIR/final-down.log"
  fi

  container_inspect_status=0
  volume_inspect_status=0
  network_inspect_status=0
  docker ps -a --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.ID}} {{.Names}}' \
    | sort > "$OUTPUT_DIR/final-containers.txt" || container_inspect_status=$?
  docker volume ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}' \
    | sort > "$OUTPUT_DIR/final-volumes.txt" || volume_inspect_status=$?
  docker network ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}' \
    | sort > "$OUTPUT_DIR/final-networks.txt" || network_inspect_status=$?

  env_remove_status=0
  rm -f "$ENV_FILE" || env_remove_status=$?
  env_removed=false
  if [[ "$env_remove_status" -eq 0 && ! -e "$ENV_FILE" ]]; then
    env_removed=true
  fi

  cleanup_passed=false
  if [[ "$cleanup_down_status" -eq 0 \
    && "$container_inspect_status" -eq 0 \
    && "$volume_inspect_status" -eq 0 \
    && "$network_inspect_status" -eq 0 \
    && "$env_removed" == true \
    && ! -s "$OUTPUT_DIR/final-containers.txt" \
    && ! -s "$OUTPUT_DIR/final-volumes.txt" \
    && ! -s "$OUTPUT_DIR/final-networks.txt" ]]; then
    cleanup_passed=true
  fi

  cleanup_report_status=0
  python3 - "$OUTPUT_DIR" "$cleanup_down_status" "$container_inspect_status" \
    "$volume_inspect_status" "$network_inspect_status" "$env_remove_status" "$env_removed" \
    "$cleanup_passed" <<'PY' || cleanup_report_status=$?
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
    "envRemoveExitCode": int(sys.argv[6]),
    "envRemoved": sys.argv[7] == "true",
    "containersRemaining": [line for line in (root / "final-containers.txt").read_text().splitlines() if line],
    "volumesRemaining": [line for line in (root / "final-volumes.txt").read_text().splitlines() if line],
    "networksRemaining": [line for line in (root / "final-networks.txt").read_text().splitlines() if line],
    "passed": sys.argv[8] == "true",
}
(root / "cleanup.json").write_text(json.dumps(cleanup, indent=2, sort_keys=True) + "\n")
report_path = root / "report.json"
if report_path.exists():
    report = json.loads(report_path.read_text())
    report["cleanup"] = cleanup
    report["releaseGatePassed"] = report.get("engineeringGate") == "pass" and cleanup["passed"]
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
PY

  if [[ "$RUN_STATUS" -eq 0 \
    && ("$cleanup_passed" != true || "$cleanup_report_status" -ne 0) ]]; then
    RUN_STATUS=1
  fi
  exit "$RUN_STATUS"
}
trap cleanup EXIT INT TERM

validate_common_options
require_command uv

if compose ps -q postgres minio redis provider-stub api worker web caddy 2>/dev/null | grep -q .; then
  printf 'r800_project_already_exists project=%s\n' "$COMPOSE_PROJECT" >&2
  exit 1
fi
OWNS_PROJECT=true

printf 'r800_start project=%s output=%s\n' "$COMPOSE_PROJECT" "$OUTPUT_DIR"
write_redacted_compose_config
sha256sum "$OUTPUT_DIR/compose-config.yml" > "$OUTPUT_DIR/compose-config.sha256"

compose up -d postgres minio redis
wait_for_service_health postgres
wait_for_postgres_sql
wait_for_service_health minio
wait_for_service_health redis

# The provider service reuses the API image, so build that image before starting it.
compose build api worker web > "$OUTPUT_DIR/build.log"
compose up -d provider-stub
wait_for_service_health provider-stub
compose run --rm -T migration > "$OUTPUT_DIR/migration.log"
compose up -d api
wait_for_service_health api

compose run --rm -T --no-deps worker \
  python scripts/r800_research_acceptance.py seed > "$OUTPUT_DIR/state.json"

compose up -d web caddy
for service in web caddy; do wait_for_service_health "$service"; done
compose exec -T api python -c \
  'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=5).read().decode())' \
  > "$OUTPUT_DIR/api-readiness.json"

date +%s%N > "$OUTPUT_DIR/scenarios-start.ns"
compose run --rm -T --no-deps worker \
  python scripts/r800_research_acceptance.py run-scenarios > "$OUTPUT_DIR/scenarios.json"
date +%s%N > "$OUTPUT_DIR/scenarios-end.ns"
capture_provider_timeline "$OUTPUT_DIR/provider-timeline.json"
compose logs --no-color api > "$OUTPUT_DIR/api.log"
compose logs --no-color worker > "$OUTPUT_DIR/worker.log"
compose logs --no-color provider-stub > "$OUTPUT_DIR/provider.log"

compose run --rm -T --no-deps worker \
  python scripts/r800_research_acceptance.py snapshot > "$OUTPUT_DIR/before.json"

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
compose down --volumes --remove-orphans > "$OUTPUT_DIR/down-before-restore.log"
docker volume ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}' \
  | sort > "$OUTPUT_DIR/volumes-after-down.txt"
docker ps -a --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.ID}} {{.Names}}' \
  | sort > "$OUTPUT_DIR/containers-after-down.txt"
if [[ -s "$OUTPUT_DIR/volumes-after-down.txt" || -s "$OUTPUT_DIR/containers-after-down.txt" ]]; then
  printf 'r800_isolated_resources_not_destroyed project=%s\n' "$COMPOSE_PROJECT" >&2
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
for service in postgres minio redis provider-stub api worker web caddy; do
  wait_for_service_health "$service"
done

compose run --rm -T --no-deps worker \
  python scripts/r800_research_acceptance.py snapshot > "$OUTPUT_DIR/after.json"
capture_provider_timeline "$OUTPUT_DIR/provider-timeline-after-restore.json"

(cd "$REPO_ROOT/apps/worker" && uv run python scripts/r800_research_acceptance.py verify \
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

def load(name):
    return json.loads((root / name).read_text())

def file_sha(name):
    return sha256((root / name).read_bytes()).hexdigest()

def elapsed_ms(start_name, end_name):
    start = int((root / start_name).read_text().strip())
    end = int((root / end_name).read_text().strip())
    return round((end - start) / 1_000_000, 3)

scenarios = load("scenarios.json")
verification = load("verification.json")
before = load("before.json")
after = load("after.json")
timeline = load("provider-timeline.json")

engineering_checks = {
    "scenarios": scenarios.get("engineeringGate") == "pass",
    "restoreVerification": verification.get("passed") is True,
    "snapshotIdentity": before.get("semanticSha256") == after.get("semanticSha256"),
    "providerTimeline": bool(timeline.get("entries")),
}
engineering_gate = "pass" if all(engineering_checks.values()) else "fail"
backup_hashes = {
    name: file_sha(f"backup/{name}")
    for name in ("manifest.env", "SHA256SUMS", "postgres.dump")
}
report = {
    "schemaVersion": "citeframe-r800-deployment-acceptance-v1",
    "project": project,
    "evidence": {
        "composeConfigSha256": file_sha("compose-config.yml"),
        "scenariosSha256": file_sha("scenarios.json"),
        "providerTimelineSha256": file_sha("provider-timeline.json"),
        "beforeSha256": file_sha("before.json"),
        "afterSha256": file_sha("after.json"),
        "verificationSha256": file_sha("verification.json"),
        "backupHashes": backup_hashes,
    },
    "durationsMs": {
        "scenarios": elapsed_ms("scenarios-start.ns", "scenarios-end.ns"),
        "backup": elapsed_ms("backup-start.ns", "backup-end.ns"),
        "restore": elapsed_ms("restore-start.ns", "restore-end.ns"),
    },
    "engineeringChecks": engineering_checks,
    "engineeringGate": engineering_gate,
    "modelQualityGate": "not_evaluable",
    "modelQualityReason": "scripted_provider_is_engineering_evidence_only",
    "userValueGate": "not_evaluable",
    "userValueReason": "no_real_target_user_evidence",
    "cleanup": None,
    "releaseGatePassed": False,
}
(root / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
PY

if ! python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1]))["engineeringGate"] == "pass" else 1)' \
  "$OUTPUT_DIR/report.json"; then
  printf 'r800_engineering_gate_failed report=%s\n' "$OUTPUT_DIR/report.json" >&2
  exit 1
fi

RUN_STATUS=0
printf 'r800_engineering_complete report=%s cleanup=pending\n' "$OUTPUT_DIR/report.json"
