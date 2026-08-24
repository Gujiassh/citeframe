#!/usr/bin/env bash

set -euo pipefail
umask 077

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
# shellcheck source=compose-common.sh
source "$SCRIPT_DIR/compose-common.sh"

usage() {
  cat <<'EOF'
Usage: run-m403a-acceptance.sh --output-dir PATH [--scales s0,s1,s2]

Runs isolated PostgreSQL capacity tiers. Each tier starts from an empty volume,
captures production-query plans and timings, then destroys its labeled project.
EOF
}

OUTPUT_DIR=""
SCALES="s0,s1,s2"
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
ACTIVE_SCALE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR=${2:-}
      shift 2
      ;;
    --scales)
      SCALES=${2:-}
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
if [[ ! "$SCALES" =~ ^s[012](,s[012])*$ ]]; then
  printf 'm403a_scales_invalid scales=%s\n' "$SCALES" >&2
  exit 2
fi
OUTPUT_DIR=$(realpath -m "$OUTPUT_DIR")
if [[ -e "$OUTPUT_DIR" ]]; then
  printf 'm403a_output_exists path=%s\n' "$OUTPUT_DIR" >&2
  exit 1
fi
mkdir -m 700 -p "$OUTPUT_DIR"
COMPOSE_OVERRIDE_FILE="$REPO_ROOT/infra/docker/compose.m403a.yml"
export COMPOSE_OVERRIDE_FILE

cleanup_active() {
  local prior_status=$?
  trap - EXIT INT TERM
  set +e
  if [[ -n "$ACTIVE_SCALE" && -n "${ENV_FILE:-}" && -f "$ENV_FILE" ]]; then
    compose ps > "$OUTPUT_DIR/$ACTIVE_SCALE/failure-compose-ps.txt" 2>&1 || true
    compose logs --no-color > "$OUTPUT_DIR/$ACTIVE_SCALE/failure-compose.log" 2>&1 || true
    compose down --volumes --remove-orphans > "$OUTPUT_DIR/$ACTIVE_SCALE/failure-down.log" 2>&1 || true
  fi
  rm -f "${ENV_FILE:-}"
  exit "$prior_status"
}
trap cleanup_active EXIT INT TERM

IFS=',' read -r -a scale_list <<< "$SCALES"
IMAGE_TAG="ai-pdf-workspace-api:m403a-${RUN_ID}"

for scale in "${scale_list[@]}"; do
  ACTIVE_SCALE=$scale
  scale_dir="$OUTPUT_DIR/$scale"
  mkdir -m 700 -p "$scale_dir"
  COMPOSE_PROJECT="citeframe-m403a-${scale}-${RUN_ID,,}"
  ENV_FILE="$scale_dir/.env.deploy"
  cat > "$ENV_FILE" <<EOF
POSTGRES_DB=ai_pdf_workspace
POSTGRES_USER=ai_pdf
POSTGRES_PASSWORD=M403A-db-${scale}-${RUN_ID}
MINIO_ROOT_USER=m403a
MINIO_ROOT_PASSWORD=M403A-minio-${RUN_ID}
MINIO_BUCKET=ai-pdf-workspace
AI_PDF_API_IMAGE=$IMAGE_TAG
AI_PDF_WORKER_IMAGE=unused-worker-m403a
AI_PDF_WEB_IMAGE=unused-web-m403a
AI_PDF_API_INTERNAL_TOKEN=M403A-internal-token-${RUN_ID}
AI_PDF_SESSION_SECRET=M403A-session-secret-${RUN_ID}-long-enough
AI_PDF_OPENAI_API_KEY=M403A-no-network
AI_PDF_EMBEDDING_PROVIDER=ollama
AI_PDF_EMBEDDING_MODEL=qwen3-embedding:0.6b
AI_PDF_EMBEDDING_VERSION=embedding-v1
AI_PDF_OLLAMA_BASE_URL=http://unused:11434
AI_PDF_RETRIEVAL_STRATEGY=hybrid
AI_PDF_RETRIEVAL_CANDIDATE_K=10
AI_PDF_RETRIEVAL_RRF_CONSTANT=60
AI_PDF_GENERATION_PROVIDER=openai
AI_PDF_GENERATION_MODEL=gpt-5.5
AI_PDF_WORKER_METRICS_HOST=0.0.0.0
AI_PDF_WORKER_METRICS_PORT=9101
CADDY_SITE_ADDRESS=:80
CADDY_HTTP_PORT=18081
CADDY_HTTPS_PORT=18444
MINIO_CONSOLE_PORT=19002
EOF
  chmod 600 "$ENV_FILE"
  ENV_FILE=$(realpath "$ENV_FILE")
  export ENV_FILE COMPOSE_PROJECT
  validate_common_options
  if compose ps -q postgres 2>/dev/null | grep -q .; then
    printf 'm403a_project_already_exists project=%s\n' "$COMPOSE_PROJECT" >&2
    exit 1
  fi
  compose config > "$scale_dir/compose-config.yml"
  if [[ "$scale" == "${scale_list[0]}" ]]; then
    compose build api > "$scale_dir/build.log"
    docker image inspect --format '{"id":{{json .Id}},"repoDigests":{{json .RepoDigests}}}' \
      "$IMAGE_TAG" > "$OUTPUT_DIR/image.json"
  fi
  compose up -d postgres
  wait_for_service_health postgres 300
  wait_for_postgres_sql 300
  postgres_id=$(compose ps -q postgres)
  docker inspect --format \
    '{"nanoCpus":{{.HostConfig.NanoCpus}},"memoryBytes":{{.HostConfig.Memory}},"shmBytes":{{.HostConfig.ShmSize}}}' \
    "$postgres_id" > "$scale_dir/postgres-resource.json"
  compose run --rm -T --no-deps migration > "$scale_dir/migration.log"
  printf 'm403a_seed_start scale=%s project=%s\n' "$scale" "$COMPOSE_PROJECT"
  compose run --rm -T --no-deps api \
    python scripts/m403a_capacity_acceptance.py seed --scale "$scale" \
    > "$scale_dir/seed.json" 2> "$scale_dir/seed.log"
  compose restart postgres > "$scale_dir/postgres-restart.log"
  wait_for_service_health postgres 300
  wait_for_postgres_sql 300
  printf 'm403a_measure_start scale=%s project=%s\n' "$scale" "$COMPOSE_PROJECT"
  compose run --rm -T --no-deps api \
    python scripts/m403a_capacity_acceptance.py measure --scale "$scale" \
    > "$scale_dir/measurement.json" 2> "$scale_dir/measurement.log"
  docker ps -a --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.ID}} {{.Names}}' | sort > "$scale_dir/containers-before-cleanup.txt"
  date +%s%N > "$scale_dir/cleanup-start.ns"
  cleanup_status=0
  compose down --volumes --remove-orphans > "$scale_dir/down.log" 2>&1 || cleanup_status=$?
  date +%s%N > "$scale_dir/cleanup-end.ns"
  docker ps -a --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.ID}} {{.Names}}' | sort > "$scale_dir/containers-after-cleanup.txt"
  docker volume ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}' | sort > "$scale_dir/volumes-after-cleanup.txt"
  docker network ls --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" --format '{{.Name}}' | sort > "$scale_dir/networks-after-cleanup.txt"
  python3 - "$scale_dir" "$cleanup_status" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
start = int((root / "cleanup-start.ns").read_text())
end = int((root / "cleanup-end.ns").read_text())
cleanup = {
    "composeDownExitCode": int(sys.argv[2]),
    "durationSeconds": (end - start) / 1_000_000_000,
    "containersRemaining": [line for line in (root / "containers-after-cleanup.txt").read_text().splitlines() if line],
    "volumesRemaining": [line for line in (root / "volumes-after-cleanup.txt").read_text().splitlines() if line],
    "networksRemaining": [line for line in (root / "networks-after-cleanup.txt").read_text().splitlines() if line],
}
cleanup["passed"] = cleanup["composeDownExitCode"] == 0 and not cleanup["containersRemaining"] and not cleanup["volumesRemaining"] and not cleanup["networksRemaining"] and cleanup["durationSeconds"] <= 300
(root / "cleanup.json").write_text(json.dumps(cleanup, indent=2, sort_keys=True) + "\n")
PY
  if ! python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1]))["passed"] else 1)' "$scale_dir/cleanup.json"; then
    printf 'm403a_cleanup_failed scale=%s\n' "$scale" >&2
    exit 1
  fi
  rm -f "$ENV_FILE"
  printf 'm403a_scale_complete scale=%s\n' "$scale"
  ACTIVE_SCALE=""
done

python3 - "$OUTPUT_DIR" "$SCALES" "$REPO_ROOT" <<'PY'
import json
from hashlib import sha256
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1])
scales = sys.argv[2].split(",")
complete_scale_set = scales == ["s0", "s1", "s2"]
repo = Path(sys.argv[3])
reports = {}
all_gates = {}
for scale in scales:
    directory = root / scale
    seed = json.loads((directory / "seed.json").read_text())
    measurement = json.loads((directory / "measurement.json").read_text())
    cleanup = json.loads((directory / "cleanup.json").read_text())
    postgres_resource = json.loads((directory / "postgres-resource.json").read_text())
    resource_passed = (
        postgres_resource["nanoCpus"] == 3_000_000_000
        and postgres_resource["memoryBytes"] == 6 * 1024**3
        and postgres_resource["shmBytes"] == 3 * 1024**3
        and measurement["gates"]["clientResourceLimits"]
    )
    scale_gates = {
        "seed": all(seed["checks"].values()),
        "query": measurement["queryGatePassed"],
        "resources": resource_passed,
        "cleanup": cleanup["passed"],
        "loadAndIndex": seed["loadAndIndexSeconds"] <= 2700 if scale == "s2" else True,
    }
    reports[scale] = {
        "seed": seed,
        "measurement": measurement,
        "postgresResource": postgres_resource,
        "cleanup": cleanup,
        "gates": scale_gates,
        "passed": all(scale_gates.values()),
    }
    all_gates[scale] = reports[scale]["passed"]
source_files = [
    "apps/api/alembic/versions/c9d1e2f3a4b5_migrate_documents_to_assets.py",
    "apps/api/alembic/versions/e1f3a5c7d9b2_add_content_unit_search_vector.py",
    "apps/api/alembic/versions/f2a4c6e8b0d1_add_embedding_current_scope.py",
    "apps/api/scripts/m403a_capacity_acceptance.py",
    "packages/backend-persistence/src/citeframe_persistence/models/content_unit.py",
    "packages/backend-persistence/src/citeframe_persistence/models/content_unit_embedding.py",
    "apps/api/src/ai_pdf_api/services/ingestion.py",
    "apps/api/src/ai_pdf_api/services/retrieval.py",
    "infra/docker/compose.deploy.yml",
    "infra/docker/compose.m403a.yml",
    "infra/scripts/run-m403a-acceptance.sh",
    "apps/api/tests/test_m403a_capacity_acceptance.py",
    "apps/api/tests/test_dense_ann_retrieval.py",
    "apps/api/tests/test_embedding_current_scope.py",
    "specs/v3/multimodal-workspace/spec.md",
    "specs/v3/multimodal-workspace/plan.md",
    "specs/v3/multimodal-workspace/tasks.md",
]
source_hashes = {name: sha256((repo / name).read_bytes()).hexdigest() for name in source_files}
git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
status = subprocess.check_output(["git", "status", "--short"], cwd=repo)
diff = subprocess.check_output(["git", "diff", "--binary", "HEAD", "--", *source_files], cwd=repo)
report = {
    "schemaVersion": "capacity-execution-v2",
    "gitCommit": git_commit,
    "gitStatusSha256": sha256(status).hexdigest(),
    "gitDiffSha256": sha256(diff).hexdigest(),
    "image": json.loads((root / "image.json").read_text()),
    "sourceHashes": source_hashes,
    "scales": reports,
    "gates": {"completeScaleSet": complete_scale_set, **all_gates},
    "debugOnly": not complete_scale_set,
    "productionImageEnabled": False,
    "releaseGatePassed": complete_scale_set and all(all_gates.values()),
}
(root / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
PY

if ! python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1]))["releaseGatePassed"] else 1)' "$OUTPUT_DIR/report.json"; then
  printf 'm403a_release_gate_failed report=%s\n' "$OUTPUT_DIR/report.json" >&2
  exit 1
fi

trap - EXIT INT TERM
printf 'm403a_complete report=%s\n' "$OUTPUT_DIR/report.json"
