#!/usr/bin/env bash

set -euo pipefail
umask 077

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
# shellcheck source=compose-common.sh
source "$SCRIPT_DIR/compose-common.sh"
BASE_COMPOSE_FILE="$COMPOSE_FILE"
R800_COMPOSE_FILE="$REPO_ROOT/infra/docker/compose.r800.yml"
OVERLAP_COMPOSE_FILE="$SCRIPT_DIR/run-r2-dispatcher-overlap.compose.yml"
POSTGRES_DIGEST=sha256:dd467f03ca5c5581222490e5217e48a262864ccb659be559f8491bbafdc97da0
POSTGRES_OFFICIAL_IMAGE="pgvector/pgvector:pg17@$POSTGRES_DIGEST"
POSTGRES_MIRROR_IMAGE="docker.m.daocloud.io/pgvector/pgvector:pg17@$POSTGRES_DIGEST"
R2_OVERLAP_POSTGRES_IMAGE="$POSTGRES_OFFICIAL_IMAGE"
export R2_OVERLAP_POSTGRES_IMAGE

compose() {
  docker-compose \
    --project-name "$COMPOSE_PROJECT" \
    --env-file "$ENV_FILE" \
    -f "$BASE_COMPOSE_FILE" \
    -f "$R800_COMPOSE_FILE" \
    -f "$OVERLAP_COMPOSE_FILE" \
    "$@"
}

usage() {
  cat <<'EOF'
Usage: run-r2-dispatcher-overlap.sh --output-dir PATH [--project NAME]

Runs a proof-only R800-backed overlap scenario with two one-shot OS
ResearchWorkProcessor.process_one actors. The isolated Compose project and its
containers, volumes, network, and generated secret env file are always removed.
This command does not claim R2 acceptance.
EOF
}

OUTPUT_DIR=""
COMPOSE_PROJECT=""
RUN_TOKEN="$(date -u +%Y%m%dT%H%M%SZ)-$$"
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
      printf 'r2_dispatcher_overlap_unknown_option option=%s\n' "$1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$OUTPUT_DIR" ]]; then
  usage >&2
  exit 2
fi
if [[ -z "$COMPOSE_PROJECT" ]]; then
  COMPOSE_PROJECT="citeframe-r2-overlap-${RUN_TOKEN,,}"
fi
if [[ ! "$COMPOSE_PROJECT" =~ ^citeframe-r2-overlap-[a-z0-9][a-z0-9_-]*$ ]]; then
  printf 'r2_dispatcher_overlap_project_invalid project=%s\n' "$COMPOSE_PROJECT" >&2
  exit 2
fi

OUTPUT_DIR=$(realpath -m "$OUTPUT_DIR")
if [[ -e "$OUTPUT_DIR" ]]; then
  printf 'r2_dispatcher_overlap_output_exists path=%s\n' "$OUTPUT_DIR" >&2
  exit 1
fi
mkdir -m 700 -p "$OUTPUT_DIR"

POSTGRES_PASSWORD="R2Overlap-db-${RUN_TOKEN}"
MINIO_ROOT_USER="r2overlap${RANDOM}${RANDOM}"
MINIO_ROOT_PASSWORD="R2Overlap-minio-${RUN_TOKEN}"
API_INTERNAL_TOKEN="R2Overlap-internal-${RUN_TOKEN}"
SESSION_SECRET="R2Overlap-session-${RUN_TOKEN}-long-enough"
OPENAI_API_KEY="R2Overlap-provider-${RUN_TOKEN}"
pick_free_port() {
  python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'
}
MINIO_CONSOLE_PORT=$(pick_free_port)
ENV_FILE="$OUTPUT_DIR/.env.deploy"
API_IMAGE="citeframe-api:r2-overlap-${RUN_TOKEN,,}"
WORKER_IMAGE="citeframe-worker:r2-overlap-${RUN_TOKEN,,}"
cat > "$ENV_FILE" <<EOF
POSTGRES_DB=ai_pdf_workspace
POSTGRES_USER=ai_pdf
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
MINIO_ROOT_USER=$MINIO_ROOT_USER
MINIO_ROOT_PASSWORD=$MINIO_ROOT_PASSWORD
MINIO_BUCKET=ai-pdf-workspace
AI_PDF_API_IMAGE=$API_IMAGE
AI_PDF_WORKER_IMAGE=$WORKER_IMAGE
AI_PDF_WEB_IMAGE=citeframe-web:r2-overlap-unused
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
AI_PDF_WORKER_METRICS_HOST=127.0.0.1
AI_PDF_WORKER_METRICS_PORT=9101
CADDY_SITE_ADDRESS=:80
CADDY_HTTP_PORT=38080
CADDY_HTTPS_PORT=38443
MINIO_CONSOLE_PORT=$MINIO_CONSOLE_PORT
EOF
chmod 600 "$ENV_FILE"
ENV_FILE=$(realpath "$ENV_FILE")
export ENV_FILE COMPOSE_PROJECT

RUN_STATUS=1
OWNS_PROJECT=false

write_redacted_compose_config() {
  compose config | \
    R2_SECRET_POSTGRES="$POSTGRES_PASSWORD" \
    R2_SECRET_MINIO_USER="$MINIO_ROOT_USER" \
    R2_SECRET_MINIO_PASSWORD="$MINIO_ROOT_PASSWORD" \
    R2_SECRET_INTERNAL_TOKEN="$API_INTERNAL_TOKEN" \
    R2_SECRET_SESSION="$SESSION_SECRET" \
    R2_SECRET_OPENAI="$OPENAI_API_KEY" \
    python3 -c '
import os, sys
payload = sys.stdin.read()
for key in (
    "R2_SECRET_POSTGRES", "R2_SECRET_MINIO_USER", "R2_SECRET_MINIO_PASSWORD",
    "R2_SECRET_INTERNAL_TOKEN", "R2_SECRET_SESSION", "R2_SECRET_OPENAI",
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
    compose ps > "$OUTPUT_DIR/final-compose-ps.txt" 2>&1 || true
    compose logs --no-color api > "$OUTPUT_DIR/final-api.log" 2>&1 || true
    compose logs --no-color provider-stub > "$OUTPUT_DIR/final-provider.log" 2>&1 || true
    cleanup_down_status=0
    compose down --volumes --remove-orphans > "$OUTPUT_DIR/final-down.log" 2>&1 || cleanup_down_status=$?
  else
    cleanup_down_status=0
    : > "$OUTPUT_DIR/final-compose-ps.txt"
    : > "$OUTPUT_DIR/final-api.log"
    : > "$OUTPUT_DIR/final-provider.log"
    : > "$OUTPUT_DIR/final-down.log"
  fi

  docker ps -a --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.ID}} {{.Names}}' \
    | sort > "$OUTPUT_DIR/final-containers.txt" 2>/dev/null
  container_status=$?
  docker volume ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}' \
    | sort > "$OUTPUT_DIR/final-volumes.txt" 2>/dev/null
  volume_status=$?
  docker network ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}' \
    | sort > "$OUTPUT_DIR/final-networks.txt" 2>/dev/null
  network_status=$?

  env_remove_status=0
  rm -f "$ENV_FILE" || env_remove_status=$?
  cleanup_passed=false
  if [[ "$cleanup_down_status" -eq 0 && "$container_status" -eq 0 \
    && "$volume_status" -eq 0 && "$network_status" -eq 0 \
    && "$env_remove_status" -eq 0 && ! -e "$ENV_FILE" \
    && ! -s "$OUTPUT_DIR/final-containers.txt" \
    && ! -s "$OUTPUT_DIR/final-volumes.txt" \
    && ! -s "$OUTPUT_DIR/final-networks.txt" ]]; then
    cleanup_passed=true
  fi

  R2_SECRET_POSTGRES="$POSTGRES_PASSWORD" \
  R2_SECRET_MINIO_USER="$MINIO_ROOT_USER" \
  R2_SECRET_MINIO_PASSWORD="$MINIO_ROOT_PASSWORD" \
  R2_SECRET_INTERNAL_TOKEN="$API_INTERNAL_TOKEN" \
  R2_SECRET_SESSION="$SESSION_SECRET" \
  R2_SECRET_OPENAI="$OPENAI_API_KEY" \
  python3 - "$OUTPUT_DIR" "$cleanup_down_status" "$container_status" "$volume_status" \
    "$network_status" "$env_remove_status" "$cleanup_passed" <<'PY'
import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
report_path = root / "report.json"
try:
    report = json.loads(report_path.read_text())
except Exception as error:
    report = {
        "schemaVersion": "citeframe-r2-dispatcher-overlap-proof-v1",
        "status": "fail",
        "evidenceClassification": "R2 dispatcher overlap proof only; not R2 ACCEPT",
        "acceptanceClaim": "none",
        "reportReadError": {"type": type(error).__name__, "message": str(error)[:300]},
    }
cleanup = {
    "composeDownExitCode": int(sys.argv[2]),
    "inspectionExitCodes": {
        "containers": int(sys.argv[3]),
        "volumes": int(sys.argv[4]),
        "networks": int(sys.argv[5]),
    },
    "envRemoveExitCode": int(sys.argv[6]),
    "envRemoved": not (root / ".env.deploy").exists(),
    "containersRemaining": (root / "final-containers.txt").read_text().splitlines(),
    "volumesRemaining": (root / "final-volumes.txt").read_text().splitlines(),
    "networksRemaining": (root / "final-networks.txt").read_text().splitlines(),
    "passed": sys.argv[7] == "true",
}
secret_values = {
    key: os.environ.get(key, "")
    for key in (
        "R2_SECRET_POSTGRES", "R2_SECRET_MINIO_USER", "R2_SECRET_MINIO_PASSWORD",
        "R2_SECRET_INTERNAL_TOKEN", "R2_SECRET_SESSION", "R2_SECRET_OPENAI",
    )
}
matches = []
for path in sorted(root.rglob("*")):
    if not path.is_file():
        continue
    try:
        payload = path.read_bytes()
    except OSError:
        continue
    for key, value in secret_values.items():
        if value and value.encode() in payload:
            matches.append({"file": path.relative_to(root).as_posix(), "secretClass": key})
report["orchestrationCleanup"] = cleanup
report["secretScan"] = {"status": "pass" if not matches else "fail", "matches": matches}
if not cleanup["passed"] or matches:
    report["status"] = "fail"
report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n")
PY
  report_update_status=$?
  if [[ "$RUN_STATUS" -eq 0 && ( "$cleanup_passed" != true || "$report_update_status" -ne 0 ) ]]; then
    RUN_STATUS=1
  fi
  if [[ -f "$OUTPUT_DIR/report.json" ]] && ! python3 -c \
    'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("status") == "pass" else 1)' \
    "$OUTPUT_DIR/report.json"; then
    RUN_STATUS=1
  fi
  exit "$RUN_STATUS"
}
trap cleanup EXIT INT TERM

validate_common_options
require_command python3
if [[ "$POSTGRES_OFFICIAL_IMAGE" != *@"$POSTGRES_DIGEST" \
  || "$POSTGRES_MIRROR_IMAGE" != *@"$POSTGRES_DIGEST" ]]; then
  printf 'r2_dispatcher_overlap_postgres_digest_invalid required=%s\n' "$POSTGRES_DIGEST" >&2
  exit 1
fi
if docker image inspect "$POSTGRES_OFFICIAL_IMAGE" >/dev/null 2>&1; then
  R2_OVERLAP_POSTGRES_IMAGE="$POSTGRES_OFFICIAL_IMAGE"
elif docker pull "$POSTGRES_OFFICIAL_IMAGE" > "$OUTPUT_DIR/postgres-official-pull.log" 2>&1; then
  R2_OVERLAP_POSTGRES_IMAGE="$POSTGRES_OFFICIAL_IMAGE"
else
  printf 'r2_dispatcher_overlap_postgres_transport=fallback image=%s\n' "$POSTGRES_MIRROR_IMAGE"
  docker pull "$POSTGRES_MIRROR_IMAGE" > "$OUTPUT_DIR/postgres-mirror-pull.log" 2>&1
  R2_OVERLAP_POSTGRES_IMAGE="$POSTGRES_MIRROR_IMAGE"
fi
export R2_OVERLAP_POSTGRES_IMAGE
if compose ps -q postgres minio redis provider-stub api worker 2>/dev/null | grep -q .; then
  printf 'r2_dispatcher_overlap_project_exists project=%s\n' "$COMPOSE_PROJECT" >&2
  exit 1
fi
OWNS_PROJECT=true

PYTHONPATH="$SCRIPT_DIR" python3 - "$REPO_ROOT" "$OUTPUT_DIR/source-manifest.json" <<'PY'
import json
import sys
from pathlib import Path
from r2_dispatcher_overlap.manifest import build_host_manifest

payload = build_host_manifest(Path(sys.argv[1]))
Path(sys.argv[2]).write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n")
PY
chmod 644 "$OUTPUT_DIR/source-manifest.json"
write_redacted_compose_config
sha256sum "$OUTPUT_DIR/compose-config.yml" > "$OUTPUT_DIR/compose-config.sha256"

printf 'r2_dispatcher_overlap_start project=%s output=%s\n' "$COMPOSE_PROJECT" "$OUTPUT_DIR"
compose up -d postgres minio redis
wait_for_service_health postgres
wait_for_postgres_sql
wait_for_service_health minio
wait_for_service_health redis
PYTHON_BASE_DIGEST=sha256:c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28
PYTHON_OFFICIAL_BASE="python:3.12-slim@$PYTHON_BASE_DIGEST"
PYTHON_MIRROR_BASE="docker.m.daocloud.io/library/python:3.12-slim@$PYTHON_BASE_DIGEST"
if compose build api worker > "$OUTPUT_DIR/build.log" 2>&1; then
  python3 - "$OUTPUT_DIR/python-build-provenance.json" "$PYTHON_OFFICIAL_BASE" <<'PYBUILD'
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
    "transport": "official",
    "configuredBase": sys.argv[2],
    "normalizedDockerfileMatchesRepository": True,
}, indent=2, sort_keys=True) + "\n")
PYBUILD
else
  printf 'r2_dispatcher_overlap_python_transport=fallback image=%s\n' "$PYTHON_MIRROR_BASE"
  if [[ "$PYTHON_MIRROR_BASE" != *@"$PYTHON_BASE_DIGEST" ]]; then
    printf 'r2_dispatcher_overlap_python_digest_invalid required=%s\n' "$PYTHON_BASE_DIGEST" >&2
    exit 1
  fi
  docker pull "$PYTHON_MIRROR_BASE" > "$OUTPUT_DIR/python-mirror-pull.log" 2>&1
  MIRROR_DOCKERFILE="$OUTPUT_DIR/Dockerfile.python.mirror"
  python3 - "$REPO_ROOT/infra/docker/Dockerfile.python" "$MIRROR_DOCKERFILE" \
    "$PYTHON_OFFICIAL_BASE" "$PYTHON_MIRROR_BASE" "$OUTPUT_DIR/python-build-provenance.json" <<'PYBUILD'
import hashlib
import json
import sys
from pathlib import Path
source_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])
official = sys.argv[3]
mirror = sys.argv[4]
output = Path(sys.argv[5])
source = source_path.read_text()
needle = f"FROM {official} AS python-base"
replacement = f"FROM {mirror} AS python-base"
if source.count(needle) != 1:
    raise SystemExit("expected exactly one pinned Python FROM line")
mirrored = source.replace(needle, replacement)
target_path.write_text(mirrored)
normalized = mirrored.replace(replacement, needle)
sha = lambda value: hashlib.sha256(value.encode()).hexdigest()
proof = {
    "transport": "same-digest-mirror",
    "configuredBase": mirror,
    "requiredDigest": official.rsplit("@", 1)[1],
    "repositoryDockerfileSha256": sha(source),
    "mirrorDockerfileSha256": sha(mirrored),
    "normalizedDockerfileSha256": sha(normalized),
    "normalizedDockerfileMatchesRepository": normalized == source,
}
output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
PYBUILD
  docker build --target api -f "$MIRROR_DOCKERFILE" -t "$API_IMAGE" "$REPO_ROOT" \
    > "$OUTPUT_DIR/build-api-mirror.log" 2>&1
  docker build --target worker -f "$MIRROR_DOCKERFILE" -t "$WORKER_IMAGE" "$REPO_ROOT" \
    > "$OUTPUT_DIR/build-worker-mirror.log" 2>&1
fi
compose up -d provider-stub
wait_for_service_health provider-stub
compose run --rm -T migration > "$OUTPUT_DIR/migration.log"
compose up -d api
wait_for_service_health api

compose run --rm -T --no-deps worker \
  python scripts/r800_research_acceptance.py seed > "$OUTPUT_DIR/seed.json"

POSTGRES_CONTAINER=$(compose ps -q postgres)
MINIO_CONTAINER=$(compose ps -q minio)
REDIS_CONTAINER=$(compose ps -q redis)
API_CONTAINER=$(compose ps -q api)
PROVIDER_CONTAINER=$(compose ps -q provider-stub)
python3 - "$OUTPUT_DIR/resources.json" \
  "$(docker inspect --format '{{.Config.Image}}' "$POSTGRES_CONTAINER")" "$(docker inspect --format '{{.Image}}' "$POSTGRES_CONTAINER")" \
  "$(docker inspect --format '{{.Config.Image}}' "$MINIO_CONTAINER")" "$(docker inspect --format '{{.Image}}' "$MINIO_CONTAINER")" \
  "$(docker inspect --format '{{.Config.Image}}' "$REDIS_CONTAINER")" "$(docker inspect --format '{{.Image}}' "$REDIS_CONTAINER")" \
  "$(docker inspect --format '{{.Config.Image}}' "$API_CONTAINER")" "$(docker inspect --format '{{.Image}}' "$API_CONTAINER")" \
  "$(docker inspect --format '{{.Config.Image}}' "$PROVIDER_CONTAINER")" "$(docker inspect --format '{{.Image}}' "$PROVIDER_CONTAINER")" \
  "$WORKER_IMAGE" "$(docker image inspect --format '{{.Id}}' "$WORKER_IMAGE")" \
  "$(sha256sum "$OUTPUT_DIR/compose-config.yml" | awk '{print $1}')" <<'PY'
import json
import sys
from pathlib import Path

names = ("postgres", "minio", "redis", "api", "providerStub", "worker")
values = sys.argv[2:14]
resources = {
    name: {"configuredImage": values[index * 2], "imageId": values[index * 2 + 1]}
    for index, name in enumerate(names)
}
payload = {
    "composeConfigSha256": sys.argv[14],
    "resources": resources,
    "pythonBuild": json.loads((Path(sys.argv[1]).parent / "python-build-provenance.json").read_text()),
}
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n")
PY
chmod 644 "$OUTPUT_DIR/resources.json"

controller_status=0
compose run --rm -T --no-deps \
  -v "$SCRIPT_DIR:/opt/citeframe-infra:ro" \
  -v "$OUTPUT_DIR/source-manifest.json:/evidence/source-manifest.json:ro" \
  -v "$OUTPUT_DIR/resources.json:/evidence/resources.json:ro" \
  worker sh -c \
  'PYTHONPATH="/opt/citeframe-infra:$PYTHONPATH" exec python -m r2_dispatcher_overlap.controller --source-manifest /evidence/source-manifest.json --resources /evidence/resources.json' \
  > "$OUTPUT_DIR/report.json" 2> "$OUTPUT_DIR/controller.log" || controller_status=$?

RUN_STATUS=$controller_status
printf 'r2_dispatcher_overlap_complete report=%s status=%s cleanup=pending\n' \
  "$OUTPUT_DIR/report.json" "$controller_status"
