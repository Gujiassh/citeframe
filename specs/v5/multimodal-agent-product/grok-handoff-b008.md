# Grok Handoff: B008 Document Deployment Closure

Date: 2026-08-10
Repository: `/home/cc/code/citeframe`
Canonical branch/ref: `main` at `80d73e3` (`origin/main`)

## Mission

Close the V5-B Markdown-only Document B008 deployment gate using the current
runner and produce a fresh, reviewable isolated Compose artifact. This is a
verification and documentation slice only. Do not change API, database,
save, replay, or payload contracts.

The repository is Python/FastAPI + Python Worker + Next.js/TypeScript; it is
not a Rust repository. The existing worktree contains a large uncommitted
`pi-subagent` V5-B change set. Treat all existing changes as owned work: do not
reset, checkout, clean, rebase, commit, or push them.

## Current Facts

- `docs/evals/artifacts/v5b-document-deployment-v1/` is an older B008 report
  with `deploymentGate=pass`, but it predates runtime container image-binding
  checks added to the runner.
- `docs/evals/artifacts/v5b-document-deployment-v2/` is a fresh run. All real
  deployment, restore, browser, and cleanup checks passed; only the runner's
  runtime match checks failed because the Worker image has no Docker
  healthcheck and the runner incorrectly required `health=healthy` for all
  three services.
- The runner and its static test now allow Worker `health=null` while still
  requiring API/Web health, running status, image tag, resolved image ID, and
  Web command. `v2` remains failure evidence and must not be rewritten.
- `docs/evals/artifacts/v5b-document-deployment-v3/` was started with the
  corrected runner and intentionally interrupted at the user's request. It is
  partial evidence only; do not call it a pass.
- The interrupted run's cleanup report passed: no containers, volumes,
  networks, generated images, or temporary env file remain.

## Scope

### In scope

1. Audit the dirty worktree and preserve unrelated/user changes.
2. Verify the runner correction and its static test.
3. Run one complete fresh isolated deployment into a new, non-existing output
   directory (use `v4` or a timestamped sibling; never overwrite `v1-v3`).
4. Perform an independent Critical review of the resulting report and raw
   manifests/logs.
5. Update the V5 progress/task/workbench records truthfully after the run.

### Out of scope

- Rust conversion or repository migration.
- API, Worker, Web production behavior changes beyond the runner's test-only
  health predicate correction.
- Schema, migration, save payload, replay semantics, auth, permissions, or
  model/provider changes.
- Commit, push, branch rewrite, cleanup of pre-existing dirty files, or
  deletion of failed artifacts.

## Execution Span

### Phase 1: Preflight

- Run `git status --short --branch`, `git remote -v`, and local/global Git
  identity checks. Do not commit.
- Run `python3 /home/cc/code1/dev-workbench/scripts/prepare_session.py --repo-path /home/cc/code/citeframe`.
- Read the current task, `docs/architecture/implementation-progress.md`,
  `specs/v5/multimodal-agent-product/implementation-lanes-v5bc.md`, and this
  handoff.
- Confirm no existing Compose project uses the selected project name or ports.

### Phase 2: Runner/static gates

Run from the repository root:

```bash
bash -n infra/scripts/run-v5b-document-acceptance.sh
uv run --project apps/api pytest apps/api/tests/test_v5b_document_deployment_runner.py
python3 -m compileall -q apps/api/src apps/worker/src
```

The runner test must assert the Worker `health=null` rule and the API/Web
health requirement. Do not loosen the check to accept an unhealthy or missing
API/Web health state.

### Phase 3: Fresh B008 execution

Use a new output directory, for example:

```bash
./infra/scripts/run-v5b-document-acceptance.sh \
  --output-dir docs/evals/artifacts/v5b-document-deployment-v4
```

The run must complete without manual intervention. Preserve all generated
artifacts, including build logs, image manifest, runtime manifests, migration,
backup/restore logs, browser before/after artifacts, verification reports,
checksums, and cleanup evidence.

### Phase 4: Independent Critical review

Review the report as a data contract, not as prose. Every check below must be
true in `report.json` and backed by raw artifacts:

- `builtImagesRecorded=true`: exactly API, Worker, and Web image tags and
  non-empty Docker IDs are recorded.
- `runtimeContainersBeforeMatchBuiltImages=true` and the corresponding
  `After` check are true. Each API/Worker/Web container has the expected tag,
  resolved ID equal to the built manifest, and `status=running`.
- API and Web runtime health is `healthy`; Worker may have `health=null` only
  because the deployment Compose service has no healthcheck. Worker must still
  be running and image-bound.
- Web command is exactly `node apps/web/server.js`.
- Alembic reaches head `f9a1b2c3d4e5`.
- Document seed succeeds and fixture/source SHA-256 values match.
- Browser before and after each pass all four production-start checks, with
  complete JSON/PNG/standalone artifacts and no route interception.
- The seeded Document asset and the browser-created Document asset both have
  live PostgreSQL/MinIO before/after snapshots with equal semantic SHA.
- Backup checksums include both Document asset object prefixes.
- Restore is performed into an empty deployment and reports live PostgreSQL and
  MinIO verification.
- `cleanup.json` has `passed=true`, zero remaining containers/volumes/networks,
  no generated image residue, and `envRemoved=true`.
- `report.json` has `deploymentGate=pass` and `releaseGatePassed=true` only
  after all of the above are true.

Reverse-review question: if the report were falsely marked pass, which raw
artifact would expose it? A reviewer must answer this for image identity,
Document restore identity, browser replay, and cleanup.

### Phase 5: Durable writeback

After a successful fresh run and independent review:

- Update the current Citeframe workbench task/checkpoint from B008 blocked to
  the exact verified state, including the fresh artifact path and command.
- Update `docs/architecture/implementation-progress.md` and the V5 lane/task
  docs so they distinguish old v1, failed v2, interrupted v3, and the accepted
  fresh run.
- Record residual risk: scripted provider proves engineering plumbing only;
  it is not model-quality or user-value evidence. Keep R803/M404 separate.
- Keep all artifact directories; do not replace or delete earlier evidence.

## Acceptance Contract

A Grok delivery is accepted only when all criteria are satisfied:

1. **Scope discipline**: only the runner health predicate, its static test,
   fresh B008 artifacts, and truthful SSoT/workbench updates changed; no API,
   persistence, save, replay, or model contract changed.
2. **Fresh evidence**: a new isolated run completes with a new output path and
   all required raw artifacts, not a copied or edited report.
3. **Image binding**: built API/Worker/Web IDs match both before/after runtime
   container manifests; API/Web are healthy and Worker is running even when
   Docker reports no health field.
4. **Document fidelity**: both Document assets restore from live PostgreSQL and
   MinIO with equal semantic identity; backup checksums cover both assets.
5. **User path**: standalone production browser flow passes before and after
   restore at desktop and mobile coverage recorded by the existing Playwright
   spec, with complete DOM/screenshot artifacts.
6. **Zero residue**: teardown leaves zero project containers, volumes,
   networks, generated images, and temporary environment files.
7. **Reviewability**: static test, compileall, `git diff --check`, report,
   manifests, logs, cleanup report, and an independent Critical review are
   present. No staged files and no commit/push are required.

Required final report shape:

```json
{
  "status": "accepted|blocked",
  "artifact": "docs/evals/artifacts/v5b-document-deployment-vN",
  "runnerFix": "worker-health-null-allowed; api-web-healthy-required",
  "checks": {
    "static": "passed",
    "freshDeployment": "passed|failed",
    "imageBinding": "passed|failed",
    "documentRestore": "passed|failed",
    "browserReplay": "passed|failed",
    "zeroResidue": "passed|failed"
  },
  "changedFiles": [],
  "commandsRun": [],
  "reviewFindings": [],
  "residualRisks": [],
  "noStagedFiles": true,
  "commitPush": "not requested"
}
```
