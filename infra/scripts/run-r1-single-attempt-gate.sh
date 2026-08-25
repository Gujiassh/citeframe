#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$ROOT"
R1_START_REF=${R1_START_REF:-8674d4dc407048471f7b14b23b821e72529487bf}

git cat-file -e "${R1_START_REF}^{commit}"

uv lock --project apps/api --check
uv lock --project apps/worker --check

uv run --project apps/worker --frozen python -m compileall -q \
  apps/worker/src/ai_pdf_worker \
  apps/api/src/ai_pdf_api/services/research

uv run --project apps/worker --frozen pytest -q \
  apps/worker/tests/test_research_single_attempt_dispatcher.py \
  apps/worker/tests/test_research_runtime.py \
  apps/worker/tests/test_research_runtime_integration.py \
  apps/worker/tests/test_main.py

uv run --project apps/api --frozen pytest -q \
  apps/api/tests/test_a2a_differential.py \
  apps/api/tests/test_r0_lock_normalization.py \
  apps/api/tests/test_research_worker_budget_recovery.py \
  apps/api/tests/test_research_worker_lease_plan.py

PYTHONPATH="packages/backend-contracts/src:packages/backend-persistence/src:packages/research-persistence/src:apps/api/src:apps/worker/src" \
  uv run --project apps/worker --frozen python - <<'PY'
import sys

import ai_pdf_worker.main
import ai_pdf_worker.research_runtime

assert "langgraph" not in sys.modules
assert "ai_pdf_worker.research_executor_engine" not in sys.modules
print("r1_production_runtime_langgraph_import=absent")
PY

git diff --check "$R1_START_REF"
echo "r1_single_attempt_gate=pass"
