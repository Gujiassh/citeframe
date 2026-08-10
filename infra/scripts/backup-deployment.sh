#!/usr/bin/env bash

set -euo pipefail
umask 077

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=compose-common.sh
source "$SCRIPT_DIR/compose-common.sh"

usage() {
  cat <<'EOF'
Usage: backup-deployment.sh --env-file PATH --project NAME --output-dir PATH

Stops Web, API, and Worker during a shared PostgreSQL and MinIO backup window.
EOF
}

OUTPUT_DIR=""
ENV_FILE=""
COMPOSE_PROJECT=""

while [[ $# -gt 0 ]]; do
  if parse_common_option "$@"; then
    case "$1" in
      --output-dir)
        OUTPUT_DIR=${2:-}
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
  else
    consumed=$?
    shift "$consumed"
  fi
done

validate_common_options
if [[ -z "$OUTPUT_DIR" ]]; then
  usage >&2
  exit 2
fi
OUTPUT_DIR=$(realpath -m "$OUTPUT_DIR")
if [[ -e "$OUTPUT_DIR" ]]; then
  printf 'backup_output_exists path=%s\n' "$OUTPUT_DIR" >&2
  exit 1
fi
mkdir -m 700 -p "$OUTPUT_DIR/minio"

POSTGRES_DB=$(strict_key_value "$ENV_FILE" POSTGRES_DB)
POSTGRES_USER=$(strict_key_value "$ENV_FILE" POSTGRES_USER)
MINIO_BUCKET=$(strict_key_value "$ENV_FILE" MINIO_BUCKET)

restart_writers() {
  compose up -d api worker web caddy >/dev/null
}
compose stop -t 300 caddy web api worker >/dev/null
trap restart_writers EXIT

compose exec -T postgres \
  pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format=custom \
  > "$OUTPUT_DIR/postgres.dump"
compose exec -T postgres pg_restore --list < "$OUTPUT_DIR/postgres.dump" >/dev/null

minio_client_shell \
  "$OUTPUT_DIR/minio:/backup" \
  'mc alias set source http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc mirror --overwrite "source/$MINIO_BUCKET" /backup >/dev/null'

cat > "$OUTPUT_DIR/manifest.env" <<EOF
FORMAT_VERSION=2
COMPOSE_PROJECT=$COMPOSE_PROJECT
POSTGRES_DB=$POSTGRES_DB
MINIO_BUCKET=$MINIO_BUCKET
BACKUP_CONTRACT=document-modality-v1
DOCUMENT_TYPED_TABLES=document_normalized_contents,document_blocks,document_locator_details
DOCUMENT_CATALOG_TABLES=asset_types,representation_types,content_unit_types,locator_types
DOCUMENT_OBJECT_LAYOUT=workspaces/{workspace_id}/assets/{asset_id}/
EOF

(
  cd "$OUTPUT_DIR"
  find postgres.dump manifest.env minio -type l -print -quit | grep -q . && {
    printf 'backup_symlink_rejected\n' >&2
    exit 1
  }
  find postgres.dump manifest.env minio -type f -print0 \
    | sort -z \
    | xargs -0 sha256sum > SHA256SUMS
)
chmod -R go-rwx "$OUTPUT_DIR"

restart_writers
trap - EXIT
printf 'backup_complete path=%s\n' "$OUTPUT_DIR"
