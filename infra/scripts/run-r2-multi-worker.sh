#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
START_SHA=a616eea1350b095c6f229890d2c47e5010902330
POSTGRES_DIGEST=sha256:dd467f03ca5c5581222490e5217e48a262864ccb659be559f8491bbafdc97da0
POSTGRES_IMAGE=${R2_POSTGRES_IMAGE:-pgvector/pgvector:pg17@${POSTGRES_DIGEST}}
POSTGRES_MIRROR_IMAGE=${R2_POSTGRES_MIRROR_IMAGE:-docker.m.daocloud.io/pgvector/pgvector:pg17@${POSTGRES_DIGEST}}
DATABASE_URL=${R2_DATABASE_URL:-}
OUTPUT_PATH=${R2_OUTPUT_PATH:-}
REPORT_ONLY=false
CONTAINER_NAME=""

usage() {
  cat <<'EOF'
Usage: infra/scripts/run-r2-multi-worker.sh [options]

Options:
  --output PATH       Write the immutable JSON evidence report to PATH.
  --report-only       Always exit zero after writing a truthful PASS/FAIL report.
  -h, --help          Show this help.

Environment:
  R2_POSTGRES_IMAGE   Pinned pgvector image. A mirror is allowed only with the exact required digest.
  R2_POSTGRES_MIRROR_IMAGE  Same-digest fallback used only when the official registry fails.
  R2_DATABASE_URL     Use an existing PostgreSQL database; the harness creates an isolated schema.
  R2_OUTPUT_PATH      Same as --output.
EOF
}

while (($#)); do
  case "$1" in
    --output) OUTPUT_PATH=${2:?missing value for --output}; shift 2 ;;
    --report-only) REPORT_ONLY=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'r2_harness error=unknown_argument value=%q\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

command -v uv >/dev/null || { printf 'r2_harness error=missing_uv\n' >&2; exit 1; }
cd "$REPO_ROOT"
ACTUAL_HEAD=$(git rev-parse HEAD)
if [[ "$ACTUAL_HEAD" != "$START_SHA" ]]; then
  printf 'r2_harness error=source_sha_mismatch expected=%s actual=%s\n' "$START_SHA" "$ACTUAL_HEAD" >&2
  exit 1
fi

RUN_TOKEN=$(python3 - <<'PY'
import secrets
print(secrets.token_hex(6))
PY
)
if [[ -z "$OUTPUT_PATH" ]]; then
  OUTPUT_PATH="/tmp/citeframe-r2-multi-worker-${RUN_TOKEN}.json"
fi

cleanup() {
  if [[ -n "$CONTAINER_NAME" ]]; then
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

IMAGE_ID="external-database"
if [[ -z "$DATABASE_URL" ]]; then
  command -v docker >/dev/null || { printf 'r2_harness error=missing_docker\n' >&2; exit 1; }
  docker info >/dev/null
  if [[ "$POSTGRES_IMAGE" != *@"$POSTGRES_DIGEST" ]]; then
    printf 'r2_harness error=postgres_digest_mismatch required=%s image=%s\n' "$POSTGRES_DIGEST" "$POSTGRES_IMAGE" >&2
    exit 1
  fi
  PORT=$(python3 - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)
  CONTAINER_NAME="citeframe-r2-postgres-${RUN_TOKEN}"
  DB_NAME="citeframe_r2_${RUN_TOKEN}"
  DB_USER="citeframe_r2"
  DB_PASSWORD="r2_${RUN_TOKEN}_$(python3 - <<'PY'
import secrets
print(secrets.token_hex(12))
PY
)"
  printf 'r2_harness phase=container_start image=%s container=%s port=%s\n' "$POSTGRES_IMAGE" "$CONTAINER_NAME" "$PORT"
  run_postgres() {
    docker run -d \
      --name "$CONTAINER_NAME" \
      --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=1g \
      -e POSTGRES_DB="$DB_NAME" \
      -e POSTGRES_USER="$DB_USER" \
      -e POSTGRES_PASSWORD="$DB_PASSWORD" \
      -p "127.0.0.1:${PORT}:5432" \
      "$1" >/dev/null
  }
  if ! run_postgres "$POSTGRES_IMAGE"; then
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    if [[ "$POSTGRES_MIRROR_IMAGE" != *@"$POSTGRES_DIGEST" ]]; then
      printf 'r2_harness error=mirror_digest_mismatch required=%s image=%s\n' "$POSTGRES_DIGEST" "$POSTGRES_MIRROR_IMAGE" >&2
      exit 1
    fi
    POSTGRES_IMAGE="$POSTGRES_MIRROR_IMAGE"
    printf 'r2_harness phase=container_retry reason=official_registry_failure image=%s\n' "$POSTGRES_IMAGE"
    run_postgres "$POSTGRES_IMAGE"
  fi
  ready=false
  for _ in $(seq 1 90); do
    if docker exec "$CONTAINER_NAME" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
      ready=true
      break
    fi
    sleep 1
  done
  if [[ "$ready" != true ]]; then
    docker logs "$CONTAINER_NAME" >&2 || true
    printf 'r2_harness error=postgres_not_ready container=%s\n' "$CONTAINER_NAME" >&2
    exit 1
  fi
  DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@127.0.0.1:${PORT}/${DB_NAME}"
  IMAGE_ID=$(docker image inspect "$POSTGRES_IMAGE" --format '{{.Id}}')
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"
ARGS=(
  --output "$OUTPUT_PATH"
  --repo-root "$REPO_ROOT"
  --expected-head "$START_SHA"
  --postgres-image "$POSTGRES_IMAGE"
  --postgres-image-id "$IMAGE_ID"
)
if [[ "$REPORT_ONLY" == true ]]; then
  ARGS+=(--report-only)
fi
printf 'r2_harness phase=baseline_start output=%s report_only=%s\n' "$OUTPUT_PATH" "$REPORT_ONLY"
set +e
R2_INTERNAL_DATABASE_URL="$DATABASE_URL" \
  uv run --project apps/worker --frozen python infra/scripts/run-r2-multi-worker.py "${ARGS[@]}"
STATUS=$?
set -e
printf 'r2_harness phase=baseline_finished status_code=%s report=%s\n' "$STATUS" "$OUTPUT_PATH"
exit "$STATUS"
