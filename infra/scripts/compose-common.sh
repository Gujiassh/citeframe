#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
COMPOSE_FILE="$REPO_ROOT/infra/docker/compose.deploy.yml"
POSTGRES_IMAGE=pgvector/pgvector:pg17@sha256:dd467f03ca5c5581222490e5217e48a262864ccb659be559f8491bbafdc97da0
MINIO_MC_IMAGE=${MINIO_MC_IMAGE:-quay.io/minio/mc:RELEASE.2025-08-13T08-35-41Z@sha256:a7fe349ef4bd8521fb8497f55c6042871b2ae640607cf99d9bede5e9bdf11727}

usage_common() {
  cat <<'EOF'
Required options:
  --env-file PATH   Deployment environment file with strict unquoted values.
  --project NAME    Explicit Docker Compose project name.
EOF
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'missing_required_command command=%s\n' "$1" >&2
    exit 1
  fi
}

require_file() {
  if [[ ! -f "$1" ]]; then
    printf 'required_file_missing path=%s\n' "$1" >&2
    exit 1
  fi
}

validate_project_name() {
  if [[ ! "$1" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
    printf 'invalid_compose_project project=%s\n' "$1" >&2
    exit 1
  fi
}

compose() {
  local compose_files=(-f "$COMPOSE_FILE")
  if [[ -n "${COMPOSE_OVERRIDE_FILE:-}" ]]; then
    compose_files+=(-f "$COMPOSE_OVERRIDE_FILE")
  fi
  docker-compose \
    --project-name "$COMPOSE_PROJECT" \
    --env-file "$ENV_FILE" \
    "${compose_files[@]}" \
    "$@"
}

strict_key_value() {
  local file=$1
  local key=$2
  local count value
  count=$(grep -c "^${key}=" "$file" || true)
  if [[ "$count" -ne 1 ]]; then
    printf 'strict_value_count_invalid file=%s key=%s count=%s\n' "$file" "$key" "$count" >&2
    exit 1
  fi
  value=$(sed -n "s/^${key}=//p" "$file")
  if [[ -z "$value" || "$value" =~ [[:space:]#\"\'] ]]; then
    printf 'strict_value_invalid file=%s key=%s\n' "$file" "$key" >&2
    exit 1
  fi
  printf '%s' "$value"
}

wait_for_service_health() {
  local service=$1
  local attempts=${2:-60}
  local container status has_health
  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    container=$(compose ps -q "$service")
    if [[ -n "$container" ]]; then
      has_health=$(docker inspect --format '{{if .State.Health}}yes{{else}}no{{end}}' "$container")
      status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container")
      if [[ "$status" == "healthy" || ( "$has_health" == "no" && "$status" == "running" ) ]]; then
        return 0
      fi
    fi
    sleep 1
  done
  printf 'service_health_timeout project=%s service=%s\n' "$COMPOSE_PROJECT" "$service" >&2
  exit 1
}

wait_for_postgres_sql() {
  local attempts=${1:-60}
  local user database
  user=$(strict_key_value "$ENV_FILE" POSTGRES_USER)
  database=$(strict_key_value "$ENV_FILE" POSTGRES_DB)
  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    if compose exec -T postgres psql \
      --username "$user" \
      --dbname "$database" \
      --no-psqlrc \
      --tuples-only \
      --no-align \
      -c 'SELECT 1' 2>/dev/null | tr -d '[:space:]' | grep -qx '1'; then
      return 0
    fi
    sleep 1
  done
  printf 'postgres_sql_timeout project=%s\n' "$COMPOSE_PROJECT" >&2
  exit 1
}

minio_client_shell() {
  local volume=$1
  local command=$2
  local minio_container user password bucket
  minio_container=$(compose ps -q minio)
  if [[ -z "$minio_container" ]]; then
    printf 'minio_container_not_running project=%s\n' "$COMPOSE_PROJECT" >&2
    exit 1
  fi
  user=$(strict_key_value "$ENV_FILE" MINIO_ROOT_USER)
  password=$(strict_key_value "$ENV_FILE" MINIO_ROOT_PASSWORD)
  bucket=$(strict_key_value "$ENV_FILE" MINIO_BUCKET)
  docker run --rm \
    --network "container:$minio_container" \
    --user "$(id -u):$(id -g)" \
    --env "MINIO_ROOT_USER=$user" \
    --env "MINIO_ROOT_PASSWORD=$password" \
    --env "MINIO_BUCKET=$bucket" \
    --env "EXPECTED_OBJECT_COUNT=${EXPECTED_OBJECT_COUNT:-}" \
    --env "MC_CONFIG_DIR=/tmp/mc-config" \
    --volume "$volume" \
    --entrypoint /bin/sh \
    "$MINIO_MC_IMAGE" \
    -c "$command"
}

parse_common_option() {
  case "$1" in
    --env-file)
      ENV_FILE=${2:-}
      return 2
      ;;
    --project)
      COMPOSE_PROJECT=${2:-}
      return 2
      ;;
  esac
  return 0
}

validate_common_options() {
  if [[ -z "${ENV_FILE:-}" || -z "${COMPOSE_PROJECT:-}" ]]; then
    usage_common >&2
    exit 2
  fi
  ENV_FILE=$(realpath "$ENV_FILE")
  require_file "$ENV_FILE"
  validate_project_name "$COMPOSE_PROJECT"
  require_command docker
  require_command docker-compose
  require_command sha256sum
}
