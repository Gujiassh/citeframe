# A2a Research Persistence Critical Re-Audit

Date: 2026-08-24
Reviewed production snapshot: `215cd52565089138704c6b637350e18bc8705c8b`
Reviewed documentation closure: `95981a499521a28bfd9eb24480d54ef42f485528`
Repair starting snapshot: `a494b8a098cb77cbc22792883d2f27881a650ffb`
Behavioral baseline: `d1b5945e977445e4db6bf56ef54cf61607ead2e2`
Verdict: **ACCEPT (High=0, Medium=0, Low=0)**

## Findings

No remaining High, Medium, or Low findings.

The sole finding raised during this re-audit was durable-delivery drift after the production
candidate became immutable: repository ledgers still described the earlier dirty worktree
and lacked final differential, test, and image evidence. Documentation-only commit
`95981a499521a28bfd9eb24480d54ef42f485528` closes it without changing production code,
tests, CI, dependencies, or runtime behavior. It records repair start and production commit,
`push state=not pushed`, production composition/UoW evidence, final full-suite counts,
official-registry timeout, exact-digest mirror images/smokes, and downstream integration
steps. The 13-file closure is confined to `docs/` and `specs/`, passes links/fences/hygiene,
and contains no stale dirty/`a494`/`1e3c`/one-test/no-image current-state claim.

## Semantic Oracle

A2a remains an extraction slice. Acceptance requires these observable statements:

- schema, API, save, replay, permission, Step/Attempt/Claim, lease/fencing,
  retry/cancel/reclaim/recovery, provider/tool accounting, payload bytes, Event row bytes,
  and terminal outcomes equal `d1b5945`;
- one Worker `process_one` executes planner publication, researcher work, join, verifier,
  critic, conflict wait/resume, synthesis, and final publication using the production
  composition for each snapshot;
- the baseline production composition remains its API Research facade, while the candidate
  production composition uses neutral persistence commands and the actual Research UoW;
- fixed multi-step execution and mixed lock acquisition remain unchanged; A2a does not
  implement R0 or R1;
- `citeframe_research_persistence` is the single DB-transition owner and imports no API or
  Worker implementation; API modules are thin compatibility/composition facades;
- legacy symbol identity and ABI, including positional `db` for `_locked_attempt`, remain
  callable through real planner/publication paths;
- lock/export/Docker/CI/SSoT/spec/workbench/delivery facts describe the same immutable
  candidate.

## Original Finding Closure

| Initial finding | Result | Independent evidence |
| --- | --- | --- |
| High 1: `_locked_attempt` ABI breaks real publication | **pass** | Signature is `_locked_attempt(db, *, attempt_id, lease_token, now)`; positional, keyword, patch-chain, planner, conflict, and final-publication paths pass. Final API suite is `650 passed, 6 skipped`. |
| Medium 1: neutral owner/UoW incomplete and duplicated | **pass** | Neutral commands own plan/completion/publication/retry/cancel/reclaim/provider/tool transitions; API mutation modules are facades/adapters; duplicate API cancellation transition is gone; candidate differential records `commandModule=citeframe_research_persistence.lease` and `uowEnterCount=38`. |
| Medium 2: static golden is not old/new oracle | **pass** | Static JSON golden is deleted. The runner archives exact `d1b5945`, injects one fixture, executes both snapshots, compares 29 transition plus 29 process-one tables, 20 plus 40 exact Event rows, payload bytes, permissions, recovery, and full graph output. API-facade composition mutation exits `2`. |
| Medium 3: Docker/CI evidence is textual/removable | **pass with transport caveat** | CI directly names `infra/scripts/a2a-deploy-gate.sh`; missing script fails the job. Effective-instruction parser ignores comments. Gate builds both targets and runs final-image path/non-root smokes. Independent exact-digest mirror builds and final-image smokes passed; official Docker Hub hostname timed out before build. |
| Medium 4: CI can repair stale locks | **pass** | `uv lock --check` precedes frozen sync; API/Worker syncs use `--frozen`; canonical exports use `--frozen`; four lock/export files are diffed together. Final lock/sync/export/diff passed. |
| Medium 5: durable status/evidence disagree | **pass** | Documentation closure `95981a499521a28bfd9eb24480d54ef42f485528` binds source/start/production commit, no-push state, final differential/full-suite/image evidence, and downstream steps; current-state drift scan is empty. |
| Low 1: legacy symbols missing | **pass** | `_persisted_error_payload`, `_frozen_error`, `_lease_step`, `_queue_ready_dependents`, and `ToolResultCallback` are restored with identity assertions; no missing baseline function/class symbol remains in the audited facade set. |

## Review Matrix

| Area | Result | Evidence |
| --- | --- | --- |
| Goal alignment | **pass** | The change remains the approved A2a extraction plus executable supply proof; no R0/R1 implementation or product scope drift was found. |
| User-visible flow/timing | **pass** | Real planner and fixed graph complete in the same four `process_one` calls around plan/conflict decisions: `[true, true, true, false]`; final Run is `completed`. |
| Architecture boundaries | **pass** | Neutral package imports no API/Worker implementation. API owns compatibility and external adapters; Worker owns orchestration/composition; neutral package owns DB transitions. |
| Data contracts/types | **pass** | Differential rows/payload/Event bytes equal baseline. No schema, public API, save/replay, permission, Step/Attempt/Claim/Event meaning change was observed. |
| Save/commit semantics | **pass** | UoW commit/rollback tests pass; existing specialized idempotency, creator-membership, storage cleanup, and final commit-outcome-unknown semantics remain and pass focused/full suites. |
| Duplicate transitions | **pass** | API cancellation duplication is removed; mutation facades call the neutral owner. Read/storage/capability adapter logic remains outside the neutral package by design. |
| Fixed multi-step graph | **pass** | Provider nodes are `planner`, `researcher`, `verifier`, `critic`, `synthesizer`; DB/Event evidence includes join, conflict wait/resume, synthesis, and final publication. |
| Mixed locks / no R0 or R1 | **pass** | Existing `Step -> Run`, `Attempt -> Step -> Run`, and `Run -> Step` paths remain. No lock normalization or single-attempt dispatcher was introduced. |
| Compatibility facade | **pass** | `_locked_attempt` ABI and missing legacy identities are covered directly; real publication paths pass. |
| Source shape | **pass with residual debt** | Ownership moved along stable responsibilities. `publication.py` (556 lines), `lease.py` (477), and `completion.py` (402) are cohesive transition modules. The 1,041-line differential probe should be split before materially expanding it. |
| Python imports/runtime names | **pass** | API/Worker/neutral `compileall` and import smokes pass; full suites import and execute changed modules. Ruff is not installed in the current uv environments, so no separate Ruff F821 scan was available. |
| Lock/export supply | **pass** | Both lock checks, frozen syncs, frozen exports, and combined four-file diff pass. |
| Docker/runtime packaging | **pass with residual transport risk** | Exact pinned base digest, byte-identical normalized Dockerfile, two final image builds, uid/cwd/path/import isolation, and API no-Worker smoke pass through mirror transport. Official Docker Hub availability remains blocked. |
| CI structure | **pass** | Six jobs remain: API, Worker fast/acceptance/evaluation, Web, Web E2E. Worker marker partitions use strict markers and final counts total 327 without overlap by construction. |
| Tests | **pass** | Final API `650/6 skipped`; Worker fast `174`, acceptance `61`, evaluation `92`; differential/boundary `8`; full old/new oracle equal. |
| SSoT/spec/delivery ledger | **pass** | Docs-only closure `95981a4` records immutable production `215cd52`, repair start, no-push state, final evidence, official-registry caveat, and downstream delivery steps. |
| Future structure | **pass** | A2a leaves R0/R1/R2/W1 isolated and blocked; neutral owner and actual Worker UoW point toward the approved end state. |
| Reverse review | **pass** | API-facade fallback mutation is caught. ABI, payload/Event, image path, and post-commit delivery-status regressions are now covered by executable gates plus immutable production/docs SHAs. |

## Exact Evidence

### Candidate And Differential

```text
productionCandidate=215cd52565089138704c6b637350e18bc8705c8b
documentationClosure=95981a499521a28bfd9eb24480d54ef42f485528
repairStart=a494b8a098cb77cbc22792883d2f27881a650ffb
pushState=not pushed

uv run --project apps/api python infra/scripts/run-a2a-differential.py \
  --root . --output /tmp/a2a-final-215cd525-reaudit.json

status=pass
baseline=d1b5945e977445e4db6bf56ef54cf61607ead2e2
candidate=215cd52565089138704c6b637350e18bc8705c8b
dirty=false
equal=true
baselineComposition=api facade, UoW entries 0
candidateComposition=citeframe_research_persistence.lease, UoW entries 38
transition Events=20; processOne Events=40
transition tables=29; processOne tables=29
semantics sha256=119a36086bfb595ea0882deab719d530ebd0107296cf8033a4f348ef07e7d4c0
report sha256=db1524a8a2604c60c98e1543eded1828cc8f9e23725287cb40d0056cace42bd7
```

The clean-worktree semantic/repair fingerprint is SHA-256 of an empty diff
(`e3b0c442...`); the immutable candidate identity is the Git commit above. The runner also
checks before/after fingerprints and fails if the candidate changes during either probe.

```text
uv run --project apps/api pytest -q \
  apps/api/tests/test_a2a_differential.py \
  apps/api/tests/test_research_persistence_boundary.py

8 passed, 1 warning
```

The focused test includes the `candidate-api-facade` mutation and requires exit code `2`
with the production-composition guard.

### Full Test Matrix

```text
uv run --project apps/api pytest -q apps/api/tests
650 passed, 6 skipped, 1 warning in 493.14s

uv run --project apps/worker pytest --strict-markers -q \
  -m "not acceptance and not evaluation" apps/worker/tests
174 passed, 153 deselected in 20.28s

uv run --project apps/worker pytest --strict-markers -q \
  -m acceptance apps/worker/tests
61 passed, 266 deselected in 372.53s

uv run --project apps/worker pytest --strict-markers -q \
  -m evaluation apps/worker/tests
92 passed, 235 deselected in 75.73s
```

### Lock And Export Gate

```text
uv lock --project apps/api --check
uv lock --project apps/worker --check
uv sync --project apps/api --frozen --extra dev
uv sync --project apps/worker --frozen --dev
uv export --project apps/api --frozen ...
uv export --project apps/worker --frozen ...
git diff --exit-code -- apps/api/uv.lock apps/worker/uv.lock \
  apps/api/requirements.deploy.txt apps/worker/requirements.deploy.txt

final_lock_sync_export_diff=pass
```

API/Worker source and tests plus neutral packages pass `compileall`; API and Worker import
smokes pass.

### Docker Evidence

Official repository Dockerfile attempts, both before any build step:

```text
docker build --target api -f infra/docker/Dockerfile.python ...
Get "https://registry-1.docker.io/v2/":
Client.Timeout exceeded while awaiting headers
exit=1

docker build --target worker -f infra/docker/Dockerfile.python ...
Get "https://registry-1.docker.io/v2/":
Client.Timeout exceeded while awaiting headers
exit=1
```

The reviewer then used `/tmp/citeframe-a2a-Dockerfile.python`, whose only diff replaces the
registry hostname on the `FROM` line. After normalizing that hostname it is byte-identical to
the repository Dockerfile (`sha256=26ce8b48...`), and the mirror reports the same immutable
base digest:

```text
python:3.12-slim@sha256:c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28
docker.m.daocloud.io/library/python@sha256:c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28
```

Final immutable-snapshot builds and smokes:

```text
API image sha256:2437e95e909b2b6d941e58b58b28551f5a09c87d93594ac9e4c80ae9ba7fe70c
a2a-final-image-smoke target=api uid=10001 status=pass
cwd=/app/apps/api; API and three neutral package paths pass; Worker absent

Worker image sha256:17e8f6645b4b7442551ef30bafbd0aab4412d0c98778b3ef6ae9241b56fa9b08
a2a-final-image-smoke target=worker uid=10001 status=pass
cwd=/app/apps/worker; API, Worker, and three neutral package paths pass
```

This is clean-image runtime evidence for the exact source and pinned base digest. It is not
evidence that the official Docker Hub hostname was available during review.

## Documentation Closure

```text
git diff --name-status \
  215cd52565089138704c6b637350e18bc8705c8b..\
  95981a499521a28bfd9eb24480d54ef42f485528

13 modified files, all under docs/ or specs/
production/config/test/CI/dependency files changed=0
git diff --check=pass
changed markdown files including reviewer artifact=14
relative links checked=76
missing links=0
fence/whitespace errors=0
stale current-state claims=0
```

The closure ledger records:

1. PR #20 prerequisite `origin/main@9f40241`, behavioral baseline `d1b5945`, initial
   rejected snapshot `20d411e`, repair start `a494b8a`, and production candidate `215cd52`.
2. Local branch and `push state=not pushed` plus required future push/review-flow steps.
3. Candidate neutral production composition, 38 UoW entries, differential result, full
   API/Worker partitions, frozen lock/export gates, and effective deploy gate.
4. Official Docker Hub timeout as a transport caveat and final exact-digest mirror API
   `2437e95e...` / Worker `17e8f6645...` image/runtime proof.
5. R0/R1/R2/W1 as separate downstream gates, with no schema/API/save/replay/permission or
   mixed-lock reinterpretation.

The dev-workbench state was reconciled before verdict; the controller must append the final
`ACCEPT`, review-artifact commit, push state, and eventual remote/integration SHAs during
delivery. That administrative writeback does not reopen A2a behavior acceptance.

## Next Gate

A2a is **ACCEPTED** at production commit
`215cd52565089138704c6b637350e18bc8705c8b` with documentation closure
`95981a499521a28bfd9eb24480d54ef42f485528`. The controller may record the verdict, commit
this reviewer artifact separately, and deliver through the repository review flow. R0 is
the next separately gated slice; R1/R2/W1 and downstream remain subject to their own named
gates. This verdict does not authorize schema/API/save/replay/permission changes or fold R0
or R1 into A2a.
