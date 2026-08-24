#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${repository_root}"

api_image="citeframe-a2a-api-gate:local"
worker_image="citeframe-a2a-worker-gate:local"

echo "a2a-deploy-gate phase=lock-check status=start"
uv lock --project apps/api --check
uv lock --project apps/worker --check

echo "a2a-deploy-gate phase=export status=start"
uv export --project apps/api --frozen --no-dev --format requirements.txt \
  --no-emit-project --no-emit-package citeframe-backend-contracts \
  --no-emit-package citeframe-backend-persistence \
  --no-emit-package citeframe-research-persistence \
  --output-file apps/api/requirements.deploy.txt >/dev/null
uv export --project apps/worker --frozen --no-dev --format requirements.txt \
  --no-emit-project --no-emit-package citeframe-backend-contracts \
  --no-emit-package citeframe-backend-persistence \
  --no-emit-package citeframe-research-persistence \
  --no-emit-package ai-pdf-api \
  --output-file apps/worker/requirements.deploy.txt >/dev/null
git diff --exit-code -- \
  apps/api/uv.lock \
  apps/worker/uv.lock \
  apps/api/requirements.deploy.txt \
  apps/worker/requirements.deploy.txt

echo "a2a-deploy-gate target=api phase=build status=start"
docker build --target api --file infra/docker/Dockerfile.python --tag "${api_image}" .
echo "a2a-deploy-gate target=api phase=smoke status=start"
docker run --rm --entrypoint python "${api_image}" -c '
import importlib.util
import os
from pathlib import Path

import ai_pdf_api
import citeframe_contracts
import citeframe_persistence
import citeframe_research_persistence

assert os.getuid() == 10001, os.getuid()
assert Path.cwd() == Path("/app/apps/api")
assert Path(ai_pdf_api.__file__).resolve().is_relative_to(Path("/app/apps/api/src"))
assert Path(citeframe_contracts.__file__).resolve().is_relative_to(Path("/app/packages/backend-contracts/src"))
assert Path(citeframe_persistence.__file__).resolve().is_relative_to(Path("/app/packages/backend-persistence/src"))
assert Path(citeframe_research_persistence.__file__).resolve().is_relative_to(Path("/app/packages/research-persistence/src"))
assert importlib.util.find_spec("ai_pdf_worker") is None
print("a2a-final-image-smoke target=api status=pass")
'

echo "a2a-deploy-gate target=worker phase=build status=start"
docker build --target worker --file infra/docker/Dockerfile.python --tag "${worker_image}" .
echo "a2a-deploy-gate target=worker phase=smoke status=start"
docker run --rm --entrypoint python "${worker_image}" -c '
import os
from pathlib import Path

import ai_pdf_api
import ai_pdf_worker
import citeframe_contracts
import citeframe_persistence
import citeframe_research_persistence

assert os.getuid() == 10001, os.getuid()
assert Path.cwd() == Path("/app/apps/worker")
assert Path(ai_pdf_api.__file__).resolve().is_relative_to(Path("/app/apps/api/src"))
assert Path(ai_pdf_worker.__file__).resolve().is_relative_to(Path("/app/apps/worker/src"))
assert Path(citeframe_contracts.__file__).resolve().is_relative_to(Path("/app/packages/backend-contracts/src"))
assert Path(citeframe_persistence.__file__).resolve().is_relative_to(Path("/app/packages/backend-persistence/src"))
assert Path(citeframe_research_persistence.__file__).resolve().is_relative_to(Path("/app/packages/research-persistence/src"))
print("a2a-final-image-smoke target=worker status=pass")
'

echo "a2a-deploy-gate status=pass"
