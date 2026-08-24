#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
POSTGRES_IMAGE=${R0_POSTGRES_IMAGE:-pgvector/pgvector:pg17@sha256:dd467f03ca5c5581222490e5217e48a262864ccb659be559f8491bbafdc97da0}
DATABASE_URL=${R0_DATABASE_URL:-}
OUTPUT_PATH=${R0_OUTPUT_PATH:-}
CONTAINER_NAME=""

usage() {
  cat <<'EOF'
Usage: infra/scripts/run-r0-postgres-contention.sh [options]

Options:
  --database-url URL  Use an existing PostgreSQL database; the harness creates and drops an isolated schema.
  --output PATH       Write the JSON evidence report to PATH.
  -h, --help          Show this help.

Environment:
  R0_POSTGRES_IMAGE   Override the pinned pgvector image used for the isolated container.
  R0_DATABASE_URL     Same as --database-url.
  R0_OUTPUT_PATH      Same as --output.
EOF
}

while (($#)); do
  case "$1" in
    --database-url)
      DATABASE_URL=${2:?missing value for --database-url}
      shift 2
      ;;
    --output)
      OUTPUT_PATH=${2:?missing value for --output}
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'r0_harness error=unknown_argument value=%q\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

command -v uv >/dev/null || { printf 'r0_harness error=missing_uv\n' >&2; exit 1; }

RUN_TOKEN=$(python3 - <<'PY'
import secrets
print(secrets.token_hex(6))
PY
)
if [[ -z "$OUTPUT_PATH" ]]; then
  OUTPUT_PATH="/tmp/citeframe-r0-contention-${RUN_TOKEN}.json"
fi

cleanup() {
  if [[ -n "$CONTAINER_NAME" ]]; then
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

if [[ -z "$DATABASE_URL" ]]; then
  command -v docker >/dev/null || { printf 'r0_harness error=missing_docker\n' >&2; exit 1; }
  docker info >/dev/null
  PORT=$(python3 - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)
  CONTAINER_NAME="citeframe-r0-postgres-${RUN_TOKEN}"
  DB_NAME="citeframe_r0_${RUN_TOKEN}"
  DB_USER="citeframe_r0"
  DB_PASSWORD="r0_${RUN_TOKEN}_$(python3 - <<'PY'
import secrets
print(secrets.token_hex(12))
PY
)"
  printf 'r0_harness phase=container_start image=%s container=%s port=%s\n' \
    "$POSTGRES_IMAGE" "$CONTAINER_NAME" "$PORT"
  docker run -d \
    --name "$CONTAINER_NAME" \
    --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=1g \
    -e POSTGRES_DB="$DB_NAME" \
    -e POSTGRES_USER="$DB_USER" \
    -e POSTGRES_PASSWORD="$DB_PASSWORD" \
    -p "127.0.0.1:${PORT}:5432" \
    "$POSTGRES_IMAGE" >/dev/null

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
    printf 'r0_harness error=postgres_not_ready container=%s\n' "$CONTAINER_NAME" >&2
    exit 1
  fi
  DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@127.0.0.1:${PORT}/${DB_NAME}"
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"
cd "$REPO_ROOT"
printf 'r0_harness phase=contention_start output=%s\n' "$OUTPUT_PATH"
uv run --project apps/api --frozen python infra/scripts/run-r0-postgres-contention.py \
  --database-url "$DATABASE_URL" \
  --output "$OUTPUT_PATH"
printf 'r0_harness status=pass report=%s\n' "$OUTPUT_PATH"
