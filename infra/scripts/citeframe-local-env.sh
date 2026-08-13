#!/usr/bin/env bash
# Switch Citeframe host processes between local PREVIEW and ACCEPT profiles.
#
#   infra/scripts/citeframe-local-env.sh preview start|stop|status|print
#   infra/scripts/citeframe-local-env.sh accept  start|stop|status|print
#
# preview — real generation provider; product Q&A
# accept  — M403B stub on :18081 for deterministic engineering gates only

set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ENV_DIR="$REPO_ROOT/infra/env"
RUN_DIR="${XDG_RUNTIME_DIR:-/tmp}/citeframe-local"
STUB_SCRIPT="$REPO_ROOT/apps/api/scripts/provider_m403b_stub.py"
STUB_PORT=18081

usage() {
  cat <<'USAGE'
Usage: citeframe-local-env.sh <preview|accept> <start|stop|status|print> [--with-web]

  preview  Daily product preview (real generation; no M403B answer stub)
  accept   Deterministic acceptance (generation+embedding via stub :18081)

  start    Start API + Worker for the profile (and stub when accept/hybrid)
  stop     Stop API + Worker + stub managed by this script
  status   Show profile, PIDs, health, and key endpoints
  print    Print resolved env (secrets redacted)

  --with-web  Also start apps/web production standalone on PORT=3100
USAGE
}

PROFILE="${1:-}"
ACTION="${2:-}"
WITH_WEB=0
if [[ $# -ge 2 ]]; then
  shift 2
else
  shift $#
fi
for arg in "$@"; do
  case "$arg" in
    --with-web) WITH_WEB=1 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'unknown_arg arg=%s\n' "$arg" >&2; usage >&2; exit 2 ;;
  esac
done

case "$PROFILE" in preview|accept) ;; *) usage >&2; exit 2 ;; esac
case "$ACTION" in start|stop|status|print) ;; *) usage >&2; exit 2 ;; esac

mkdir -p "$RUN_DIR"
PROFILE_FILE="$RUN_DIR/active-profile"
API_PID_FILE="$RUN_DIR/api.pid"
WORKER_PID_FILE="$RUN_DIR/worker.pid"
STUB_PID_FILE="$RUN_DIR/stub.pid"
WEB_PID_FILE="$RUN_DIR/web.pid"
API_LOG="$RUN_DIR/api.log"
WORKER_LOG="$RUN_DIR/worker.log"
STUB_LOG="$RUN_DIR/stub.log"
WEB_LOG="$RUN_DIR/web.log"

example_file() { printf '%s/%s.env.example\n' "$ENV_DIR" "$PROFILE"; }
local_file() { printf '%s/%s.local.env\n' "$ENV_DIR" "$PROFILE"; }

load_profile_env() {
  local example localf
  example=$(example_file)
  localf=$(local_file)
  if [[ ! -f "$example" ]]; then
    printf 'missing_example path=%s\n' "$example" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$example"
  if [[ -f "$localf" ]]; then
    # shellcheck disable=SC1090
    source "$localf"
  fi
  if [[ "$PROFILE" == "preview" && -z "${AI_PDF_OPENAI_API_KEY:-}" && -n "${OPENAI_API_KEY:-}" ]]; then
    export AI_PDF_OPENAI_API_KEY="$OPENAI_API_KEY"
  fi
  set +a
  export CITEFRAME_ENV="$PROFILE"
}

redact_print_env() {
  load_profile_env
  env | grep -E '^(CITEFRAME_ENV|AI_PDF_|OPENAI_API_BASE)=' | sort | sed -E 's/(KEY|TOKEN|SECRET|PASSWORD)=.*/\1=<redacted>/'
}

pid_alive() {
  local pid=$1
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

read_pid() {
  local file=$1
  [[ -f "$file" ]] || { echo ""; return; }
  tr -d ' \n' < "$file"
}

stop_pidfile() {
  local file=$1
  local name=$2
  local pid
  pid=$(read_pid "$file")
  if pid_alive "$pid"; then
    kill "$pid" 2>/dev/null || true
    sleep 0.5
    if pid_alive "$pid"; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    printf 'stopped name=%s pid=%s\n' "$name" "$pid"
  fi
  rm -f "$file"
}

port_listening() {
  local port=$1
  ss -lnt | awk '{print $4}' | grep -E ":${port}$" >/dev/null
}

ensure_stub() {
  if port_listening "$STUB_PORT"; then
    printf 'stub_already_up port=%s\n' "$STUB_PORT"
    return 0
  fi
  (
    cd "$REPO_ROOT"
    nohup uv run --project apps/api python "$STUB_SCRIPT" >"$STUB_LOG" 2>&1 &
    echo $! >"$STUB_PID_FILE"
  )
  sleep 0.8
  if port_listening "$STUB_PORT"; then
    printf 'stub_started port=%s pid=%s\n' "$STUB_PORT" "$(read_pid "$STUB_PID_FILE")"
  else
    printf 'stub_start_failed log=%s\n' "$STUB_LOG" >&2
    tail -n 20 "$STUB_LOG" >&2 || true
    exit 1
  fi
}

preview_needs_embed_stub() {
  [[ "${AI_PDF_OLLAMA_BASE_URL:-}" == *":${STUB_PORT}"* ]]
}

start_web() {
  stop_pidfile "$WEB_PID_FILE" web
  local standalone="$REPO_ROOT/apps/web/.next/standalone/apps/web"
  if [[ ! -f "$standalone/server.js" ]]; then
    printf 'web_build_required\n'
    (cd "$REPO_ROOT" && pnpm --dir apps/web build)
  fi
  if [[ ! -d "$standalone/.next/static" ]]; then
    mkdir -p "$standalone/.next"
    cp -a "$REPO_ROOT/apps/web/.next/static" "$standalone/.next/static"
  fi
  (
    set -a
    if [[ -f "$REPO_ROOT/apps/web/.env.local" ]]; then
      # shellcheck disable=SC1091
      source "$REPO_ROOT/apps/web/.env.local"
    fi
    set +a
    cd "$standalone"
    nohup env HOSTNAME=0.0.0.0 PORT=3100 node server.js >"$WEB_LOG" 2>&1 &
    echo $! >"$WEB_PID_FILE"
  )
  sleep 0.8
  printf 'web_url=http://127.0.0.1:3100 pid=%s\n' "$(read_pid "$WEB_PID_FILE")"
}

start_api_worker() {
  load_profile_env
  if [[ "$PROFILE" == "accept" ]]; then
    ensure_stub
  elif preview_needs_embed_stub; then
    printf 'preview_hybrid note=generation_real embedding_via_stub_%s\n' "$STUB_PORT"
    ensure_stub
  fi

  if [[ "$PROFILE" == "preview" ]]; then
    if [[ -z "${AI_PDF_OPENAI_API_KEY:-}${OPENAI_API_KEY:-}" ]]; then
      printf 'preview_missing_key set OPENAI_API_KEY or write AI_PDF_OPENAI_API_KEY in %s\n' "$(local_file)" >&2
      exit 1
    fi
    case "${AI_PDF_OPENAI_API_BASE:-}" in
      *18081*)
        printf 'preview_refuses_stub_generation base=%s\n' "${AI_PDF_OPENAI_API_BASE}" >&2
        exit 1
        ;;
    esac
  fi

  stop_pidfile "$API_PID_FILE" api
  stop_pidfile "$WORKER_PID_FILE" worker

  (
    cd "$REPO_ROOT"
    set -a
    # shellcheck disable=SC1090
    source "$(example_file)"
    if [[ -f "$(local_file)" ]]; then
      # shellcheck disable=SC1090
      source "$(local_file)"
    fi
    if [[ "$PROFILE" == "preview" && -z "${AI_PDF_OPENAI_API_KEY:-}" && -n "${OPENAI_API_KEY:-}" ]]; then
      export AI_PDF_OPENAI_API_KEY="$OPENAI_API_KEY"
    fi
    export CITEFRAME_ENV="$PROFILE"
    set +a
    nohup uv run --project apps/api uvicorn ai_pdf_api.main:app --host 127.0.0.1 --port 8000 \
      >"$API_LOG" 2>&1 &
    echo $! >"$API_PID_FILE"
    nohup uv run --project apps/worker python -m ai_pdf_worker.main \
      >"$WORKER_LOG" 2>&1 &
    echo $! >"$WORKER_PID_FILE"
  )

  echo "$PROFILE" >"$PROFILE_FILE"
  sleep 1.5
  if curl -fsS -m 3 http://127.0.0.1:8000/health >/dev/null; then
    printf 'api_health=ok profile=%s\n' "$PROFILE"
  else
    printf 'api_health=fail log=%s\n' "$API_LOG" >&2
    tail -n 30 "$API_LOG" >&2 || true
    exit 1
  fi
  printf 'worker_pid=%s api_pid=%s\n' "$(read_pid "$WORKER_PID_FILE")" "$(read_pid "$API_PID_FILE")"
  if [[ "$WITH_WEB" -eq 1 ]]; then
    start_web
  fi
}

do_stop() {
  stop_pidfile "$WEB_PID_FILE" web
  stop_pidfile "$API_PID_FILE" api
  stop_pidfile "$WORKER_PID_FILE" worker
  stop_pidfile "$STUB_PID_FILE" stub
  rm -f "$PROFILE_FILE"
  printf 'stopped\n'
}

do_status() {
  local active
  active=$(cat "$PROFILE_FILE" 2>/dev/null || echo none)
  printf 'active_profile=%s requested=%s\n' "$active" "$PROFILE"
  printf 'api_pid=%s worker_pid=%s stub_pid=%s web_pid=%s\n' \
    "$(read_pid "$API_PID_FILE")" "$(read_pid "$WORKER_PID_FILE")" \
    "$(read_pid "$STUB_PID_FILE")" "$(read_pid "$WEB_PID_FILE")"
  if curl -fsS -m 2 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    printf 'api_health=ok\n'
  else
    printf 'api_health=down\n'
  fi
  if port_listening "$STUB_PORT"; then
    printf 'stub_port_%s=up\n' "$STUB_PORT"
  else
    printf 'stub_port_%s=down\n' "$STUB_PORT"
  fi
  if port_listening 3100; then
    printf 'web_port_3100=up\n'
  else
    printf 'web_port_3100=down\n'
  fi
}

case "$ACTION" in
  print) redact_print_env ;;
  start) start_api_worker ;;
  stop) do_stop ;;
  status) do_status ;;
esac
