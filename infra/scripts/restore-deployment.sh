#!/usr/bin/env bash

set -euo pipefail
umask 077

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=compose-common.sh
source "$SCRIPT_DIR/compose-common.sh"

usage() {
  cat <<'EOF'
Usage: restore-deployment.sh --env-file PATH --project NAME --backup-dir PATH --confirm

Restores only into an empty deployment database and bucket. All validation is
performed before Web, API, or Worker are started.
EOF
}

BACKUP_DIR=""
ENV_FILE=""
COMPOSE_PROJECT=""
CONFIRM=false

while [[ $# -gt 0 ]]; do
  if parse_common_option "$@"; then
    case "$1" in
      --backup-dir)
        BACKUP_DIR=${2:-}
        shift 2
        ;;
      --confirm)
        CONFIRM=true
        shift
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
if [[ -z "$BACKUP_DIR" ]]; then
  usage >&2
  exit 2
fi
if [[ "$CONFIRM" != true ]]; then
  printf 'restore_confirmation_required flag=--confirm\n' >&2
  exit 2
fi

BACKUP_DIR=$(realpath "$BACKUP_DIR")
require_file "$BACKUP_DIR/postgres.dump"
require_file "$BACKUP_DIR/manifest.env"
require_file "$BACKUP_DIR/SHA256SUMS"

TARGET_POSTGRES_DB=$(strict_key_value "$ENV_FILE" POSTGRES_DB)
POSTGRES_USER=$(strict_key_value "$ENV_FILE" POSTGRES_USER)
TARGET_MINIO_BUCKET=$(strict_key_value "$ENV_FILE" MINIO_BUCKET)
BACKUP_FORMAT_VERSION=$(strict_key_value "$BACKUP_DIR/manifest.env" FORMAT_VERSION)
if [[ "$BACKUP_FORMAT_VERSION" == "1" ]]; then
  printf 'backup_format_unsupported version=1 required=2 message=create_a_new_format_2_backup\n' >&2
  exit 1
fi
if [[ "$BACKUP_FORMAT_VERSION" != "2" ]]; then
  printf 'backup_format_unsupported version=%s required=2\n' "$BACKUP_FORMAT_VERSION" >&2
  exit 1
fi
[[ "$(strict_key_value "$BACKUP_DIR/manifest.env" COMPOSE_PROJECT)" == "$COMPOSE_PROJECT" ]] || {
  printf 'backup_project_mismatch\n' >&2
  exit 1
}
[[ "$(strict_key_value "$BACKUP_DIR/manifest.env" POSTGRES_DB)" == "$TARGET_POSTGRES_DB" ]] || {
  printf 'backup_database_mismatch\n' >&2
  exit 1
}
[[ "$(strict_key_value "$BACKUP_DIR/manifest.env" MINIO_BUCKET)" == "$TARGET_MINIO_BUCKET" ]] || {
  printf 'backup_bucket_mismatch\n' >&2
  exit 1
}
BACKUP_CONTRACT=$(strict_key_value "$BACKUP_DIR/manifest.env" BACKUP_CONTRACT)
DOCUMENT_TYPED_TABLES=$(strict_key_value "$BACKUP_DIR/manifest.env" DOCUMENT_TYPED_TABLES)
DOCUMENT_CATALOG_TABLES=$(strict_key_value "$BACKUP_DIR/manifest.env" DOCUMENT_CATALOG_TABLES)
DOCUMENT_OBJECT_LAYOUT=$(strict_key_value "$BACKUP_DIR/manifest.env" DOCUMENT_OBJECT_LAYOUT)
[[ "$BACKUP_CONTRACT" == "document-modality-v1" ]] || {
  printf 'backup_contract_mismatch key=BACKUP_CONTRACT expected=document-modality-v1\n' >&2
  exit 1
}
[[ "$DOCUMENT_TYPED_TABLES" == "document_normalized_contents,document_blocks,document_locator_details" ]] || {
  printf 'backup_contract_mismatch key=DOCUMENT_TYPED_TABLES\n' >&2
  exit 1
}
[[ "$DOCUMENT_CATALOG_TABLES" == "asset_types,representation_types,content_unit_types,locator_types" ]] || {
  printf 'backup_contract_mismatch key=DOCUMENT_CATALOG_TABLES\n' >&2
  exit 1
}
[[ "$DOCUMENT_OBJECT_LAYOUT" == "workspaces/{workspace_id}/assets/{asset_id}/" ]] || {
  printf 'backup_contract_mismatch key=DOCUMENT_OBJECT_LAYOUT\n' >&2
  exit 1
}

(
  cd "$BACKUP_DIR"
  listed_files=$(mktemp)
  actual_files=$(mktemp)
  trap 'rm -f "$listed_files" "$actual_files"' EXIT
  if find postgres.dump manifest.env minio -type l -print -quit | grep -q .; then
    printf 'backup_symlink_rejected\n' >&2
    exit 1
  fi
  if find postgres.dump manifest.env minio \! -type f \! -type d -print -quit | grep -q .; then
    printf 'backup_special_file_rejected\n' >&2
    exit 1
  fi
  awk '{print $2}' SHA256SUMS | LC_ALL=C sort > "$listed_files"
  if [[ "$(wc -l < "$listed_files")" -ne "$(LC_ALL=C sort -u "$listed_files" | wc -l)" ]]; then
    printf 'backup_duplicate_checksum_path\n' >&2
    exit 1
  fi
  if grep -Eq '(^/|(^|/)\.\.(/|$))' "$listed_files"; then
    printf 'backup_checksum_path_invalid\n' >&2
    exit 1
  fi
  find postgres.dump manifest.env minio -type f -printf '%p\n' | LC_ALL=C sort > "$actual_files"
  diff -u "$actual_files" "$listed_files" >/dev/null || {
    printf 'backup_file_set_mismatch\n' >&2
    exit 1
  }
  sha256sum --check --strict SHA256SUMS >/dev/null
)

EXPECTED_OBJECT_COUNT=$(find "$BACKUP_DIR/minio" -type f | wc -l)
export EXPECTED_OBJECT_COUNT

# Archive structure is checked before any service or persistent data is touched.
docker run --rm -i "$POSTGRES_IMAGE" pg_restore --list < "$BACKUP_DIR/postgres.dump" >/dev/null

# Restore targets are intentionally limited to freshly created empty data volumes.
if compose ps -q caddy web api worker provider-stub redis | grep -q .; then
  printf 'restore_application_services_present project=%s\n' "$COMPOSE_PROJECT" >&2
  exit 1
fi
compose up -d postgres minio redis
wait_for_service_health postgres
wait_for_postgres_sql
wait_for_service_health minio
wait_for_service_health redis

database_object_count=$(compose exec -T postgres psql \
  --username "$POSTGRES_USER" \
  --dbname "$TARGET_POSTGRES_DB" \
  --tuples-only \
  --no-align \
  -c "
    with user_schemas as (
      select oid, nspname
      from pg_namespace
      where nspname not in ('pg_catalog', 'information_schema')
        and nspname !~ '^pg_toast'
        and nspname !~ '^pg_temp_'
    ), user_objects as (
      select 1 from user_schemas where nspname <> 'public'
      union all
      select 1 from pg_class c join user_schemas n on n.oid = c.relnamespace
        where c.relkind in ('r', 'p', 'v', 'm', 'S', 'f')
      union all
      select 1 from pg_proc p join user_schemas n on n.oid = p.pronamespace
      union all
      select 1 from pg_type t join user_schemas n on n.oid = t.typnamespace
        where t.typtype in ('c', 'd', 'e', 'r', 'm') and t.typrelid = 0
      union all
      select 1 from pg_extension where extname <> 'plpgsql'
    )
    select count(*) from user_objects
  " | tr -d '[:space:]')
if [[ "$database_object_count" != "0" ]]; then
  printf 'restore_database_not_empty objects=%s\n' "$database_object_count" >&2
  exit 1
fi
redis_key_count=$(compose exec -T redis redis-cli DBSIZE | tr -d '[:space:]')
if [[ "$redis_key_count" != "0" ]]; then
  printf 'restore_redis_not_empty keys=%s\n' "$redis_key_count" >&2
  exit 1
fi
target_object_count=$(minio_client_shell \
  "$BACKUP_DIR/minio:/restore:ro" \
  'set -eu
   mc alias set target http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
   object_list=$(mktemp)
   trap '\''rm -f "$object_list"'\'' EXIT
   bucket_list=$(mc ls target)
   case "$bucket_list" in
     *" $MINIO_BUCKET/"*) mc find "target/$MINIO_BUCKET" --print x > "$object_list" ;;
     *) : > "$object_list" ;;
   esac
   wc -l < "$object_list"')
target_object_count=$(printf '%s' "$target_object_count" | tr -d '[:space:]')
if [[ "$target_object_count" != "0" ]]; then
  printf 'restore_bucket_not_empty objects=%s\n' "$target_object_count" >&2
  exit 1
fi

compose exec -T postgres pg_restore \
  --username "$POSTGRES_USER" \
  --dbname "$TARGET_POSTGRES_DB" \
  --no-owner \
  --no-privileges \
  --exit-on-error \
  --single-transaction \
  < "$BACKUP_DIR/postgres.dump"
restored_object_count=$(minio_client_shell \
  "$BACKUP_DIR/minio:/restore:ro" \
  'set -eu
   mc alias set target http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
   mc mb --ignore-existing "target/$MINIO_BUCKET" >/dev/null
   mc mirror --overwrite --remove /restore "target/$MINIO_BUCKET" >/dev/null
   object_list=$(mktemp)
   trap '\''rm -f "$object_list"'\'' EXIT
   mc find "target/$MINIO_BUCKET" --print x > "$object_list"
   wc -l < "$object_list"')
restored_object_count=$(printf '%s' "$restored_object_count" | tr -d '[:space:]')
if [[ "$restored_object_count" != "$EXPECTED_OBJECT_COUNT" ]]; then
  printf 'restore_object_count_mismatch expected=%s actual=%s\n' "$EXPECTED_OBJECT_COUNT" "$restored_object_count" >&2
  exit 1
fi

VERIFY_DIR=$(mktemp -d)
trap 'rm -rf "$VERIFY_DIR"' EXIT
minio_client_shell \
  "$VERIFY_DIR:/verify" \
  'mc alias set target http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc mirror "target/$MINIO_BUCKET" /verify >/dev/null'
diff -qr "$BACKUP_DIR/minio" "$VERIFY_DIR" >/dev/null || {
  printf 'restore_object_verification_failed\n' >&2
  exit 1
}
rm -rf "$VERIFY_DIR"
trap - EXIT

compose run --rm migration
compose up -d api worker web caddy
for service in postgres minio redis api worker web caddy; do
  wait_for_service_health "$service"
done
printf 'restore_complete project=%s backup=%s\n' "$COMPOSE_PROJECT" "$BACKUP_DIR"
