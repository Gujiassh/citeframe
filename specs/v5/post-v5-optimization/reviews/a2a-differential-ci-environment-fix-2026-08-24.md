# A2a Differential CI Environment Fix Ledger

Date: 2026-08-24
Status: **implemented and pushed; independent follow-up ACCEPT; PR #21 CI rerun pending**
Pull request context: `Gujiassh/citeframe#21`
Behavioral baseline: `d1b5945e977445e4db6bf56ef54cf61607ead2e2`

## Delivery Status

- Implementation commit: `4b24181a3b2a5fbca3cbf6ee0cf0a3ac0d72ca96` (`4b24181`).
- Push target: `origin/work/research-boundary-runtime-20260824`.
- Pull request: `Gujiassh/citeframe#21`; CI rerun is pending. This ledger does not claim
  CI pass or merge.
- Independent follow-up review: **ACCEPT** with no remaining High or Medium finding for
  this bounded CI-environment repair.
- The exact non-recursive ledger-closure SHA is owned by the external/workbench delivery
  record and is intentionally not self-recorded in this file.

## CI Symptom

The PR #21 API job ran `apps/api/tests/test_a2a_differential.py` from the frozen API
environment. That environment intentionally has no Worker-only LangGraph dependency. The
test launched the differential runner with the API interpreter, and the runner reused that
interpreter when a pre-existing `apps/worker/.venv` was absent. The injected probe then
imported the production Worker runtime and failed with:

```text
ModuleNotFoundError: No module named 'langgraph'
```

Local development had concealed the defect because an already-synchronized Worker venv was
present. The oracle therefore depended on mutable machine state instead of the Worker lock
belonging to each compared snapshot.

## Root Cause

The runner selected a Python executable before extracting the baseline and passed the same
executable to both probes. Its fallback was `sys.executable`, which in the API CI job was the
API-only interpreter. This violated the differential boundary: baseline and candidate
Worker behavior must execute with the frozen Worker environment declared by that exact
snapshot, not with the caller's environment.

No application dependency was missing. Adding LangGraph to the API manifest would have
hidden the orchestration error and incorrectly widened the API runtime contract.

## Bounded Repair

The repair changes only:

- `infra/scripts/run-a2a-differential.py`;
- `apps/api/tests/test_a2a_differential.py`;
- `apps/api/tests/test_a2a_differential_probe.py`;
- this delivery ledger.

For both extracted baseline and live candidate, the runner now executes:

```text
uv run --project <snapshot>/apps/worker --frozen --exact --python 3.12 \
  python -m pytest -q -s <snapshot-probe>
```

The runner clears inherited `VIRTUAL_ENV`, `UV_PROJECT_ENVIRONMENT`, `UV_NO_SYNC`,
`UV_INEXACT`, `PYTEST_ADDOPTS`, and `PYTEST_PLUGINS`, requires `uv`, exact-syncs away
extraneous distributions and plugins, and never falls back to the caller/API interpreter. Existing per-probe timeouts, exact baseline
SHA validation, production composition/UoW evidence, API-facade mutation, exact byte/row
coverage, and semantic/full-repair before-and-after fingerprints remain fail closed.

The probe records its actual Python prefix, LangGraph implementation module, and Worker
source module. The runner rejects reports unless the prefix belongs to the snapshot's
`apps/worker/.venv`, LangGraph resolves from that environment, and Worker source resolves
from that snapshot.

The outer API test independently proves its own interpreter has no `langgraph`, then proves
the full oracle still passes. It also asserts `probeExecution=uv-worker-frozen-exact` and validates
both baseline and candidate Worker-environment evidence.

## Verification Evidence

### Genuinely clean API-only environment

```bash
TMP_ROOT=$(mktemp -d /tmp/citeframe-api-only-XXXXXX)
UV_PROJECT_ENVIRONMENT="$TMP_ROOT/.venv" \
  uv sync --project apps/api --frozen --extra dev --python 3.12
"$TMP_ROOT/.venv/bin/python" -I -c \
  "import importlib.util; assert importlib.util.find_spec('langgraph') is None"
"$TMP_ROOT/.venv/bin/python" -m pytest -q \
  apps/api/tests/test_a2a_differential.py
```

Result:

```text
clean_api_langgraph=absent
3 passed, 1 warning in 21.78s
```

The warning is the existing Starlette/httpx deprecation warning and is unrelated to this
repair.

### Existing frozen API environment

```bash
uv run --project apps/api --frozen python -I -c \
  "import importlib.util; assert importlib.util.find_spec('langgraph') is None"
uv run --project apps/api --frozen pytest -q \
  apps/api/tests/test_a2a_differential.py
```

Result:

```text
langgraph=absent
3 passed, 1 warning in 22.05s
```

### Candidate frozen Worker probe

```bash
env \
  -u VIRTUAL_ENV \
  -u UV_PROJECT_ENVIRONMENT \
  -u UV_NO_SYNC \
  -u UV_INEXACT \
  -u PYTEST_ADDOPTS \
  -u PYTEST_PLUGINS \
  -u AI_PDF_WORKER_INSTANCE_ID \
  A2A_DIFFERENTIAL_PROBE_OUTPUT=/tmp/a2a-worker-env-probe.json \
  A2A_DIFFERENTIAL_LABEL=candidate \
  PYTHONNOUSERSITE=1 \
  PYTHONPATH="$PWD/apps/api/src:$PWD/apps/worker/src:$PWD/packages/backend-contracts/src:$PWD/packages/backend-persistence/src:$PWD/packages/research-persistence/src" \
  AI_PDF_EMBEDDING_PROVIDER=openai \
  AI_PDF_EMBEDDING_MODEL=text-embedding-3-small \
  AI_PDF_EMBEDDING_DIMENSIONS=1024 \
  AI_PDF_EMBEDDING_VERSION=embedding-v1 \
  AI_PDF_OPENAI_API_BASE=https://api.openai.com/v1 \
  AI_PDF_CAPABILITY_FINGERPRINT_PEPPER=local-development-capability-fingerprint-pepper \
  AI_PDF_GENERATION_PROVIDER=openai \
  AI_PDF_GENERATION_MODEL=gpt-5.5 \
  AI_PDF_RETRIEVAL_STRATEGY=hybrid \
  uv run --project apps/worker --frozen --exact --python 3.12 \
    python -m pytest -q -s apps/api/tests/test_a2a_differential_probe.py
```

This is the complete deterministic environment used by the runner; it is directly
executable from the repository root.
Result:

```text
1 passed, 1 warning in 0.71s
pythonPrefix=/home/cc/code/citeframe/apps/worker/.venv
langgraphModule=.../apps/worker/.venv/lib/python3.12/site-packages/langgraph/graph/__init__.py
workerModule=.../apps/worker/src/ai_pdf_worker/__init__.py
candidateComposition=candidate-neutral-research-uow
uowEnterCount=38
```

### API-facade mutation

```bash
python infra/scripts/run-a2a-differential.py --root . \
  --candidate-mutation candidate-api-facade
```

Result:

```text
exit=2
candidate probe failed
candidate production composition must not use API research_worker facade
```

### Persistent Worker-environment pollution REWORK

Independent review found that `--frozen` alone could retain extraneous distributions and
`pytest11` plugins in a persistent Worker venv. The runner now combines `--frozen` with
`--exact` for both snapshots. An executable regression builds and installs a real
`citeframe-a2a-pollution` wheel containing a `pytest11` entry point into the candidate
Worker venv. The test proves the distribution and entry point are discoverable and executes
a smoke test that writes a plugin sentinel. It then runs the oracle and proves all of the
following:

- the oracle still returns baseline/candidate equality;
- the sentinel is not written during the oracle probe;
- the extraneous distribution is absent after candidate exact sync;
- a `finally` exact sync restores the Worker environment even on assertion failure.

Focused pollution execution result:

```text
1 passed, 2 deselected, 1 warning in 8.38s
pollution_distribution=absent after cleanup
```

The complete API differential file, including equality, mutation, and pollution lanes,
passes `3 passed`. This closes the CI environment REWORK without changing any manifest or
lock.

### Static hygiene

The three executable-oracle files pass `python -m py_compile`, targeted
`git diff --check`, and the repository long-line scan. The runner report identifies its
execution mode as `uv-worker-frozen-exact`. The final runner report retains
baseline/candidate equality, exact Event/payload bytes, 29-table normalized snapshots,
lease/fencing, retry/cancel/reclaim/recovery, permission, fixed multi-step `process_one`,
candidate neutral command ownership, and real `ResearchUnitOfWork` execution evidence.

## Contract And Dependency Statement

This repair changes no production source, public API, schema, save/replay/permission
semantics, manifest, lock, frozen export, or Docker dependency. LangGraph remains a Worker
dependency only. The API environment remains intentionally free of LangGraph.
