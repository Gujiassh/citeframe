# A1b Persistence Implementation Evidence

- Date: 2026-08-20
- Source branch: `work/docs-stale-honesty-20260817`
- Starting ref: `d1b5945e977445e4db6bf56ef54cf61607ead2e2`
- Delivery state: implementer-complete in the existing dirty worktree; no commit and no push
- Review state: **independent A1b Critical review ACCEPT (2026-08-21; High=0, Medium=0, Low=0)**
- Reviewer-owned result: [`a1b-persistence-critical-audit-2026-08-20.md`](a1b-persistence-critical-audit-2026-08-20.md)

## Scope

A1b/A2-foundation relocates the single SQLAlchemy `DeclarativeBase`, metadata identity,
and all existing ORM mappings into `citeframe-backend-persistence` /
`citeframe_persistence`. API model modules remain compatibility aliases to the same
objects. The checked-in PostgreSQL DDL snapshot is the pre-metadata baseline used to
prove zero table/index drift. No migration, schema, API payload, save/replay, permission,
session, transaction, runtime dispatch, or lock-order behavior was changed.

The implementation does not create or expose `citeframe_research_persistence`. The
implementation evidence records rework of stale source oracles and provenance paths; it
does not constitute the independent review. The reviewer-owned follow-up artifact records the
final ACCEPT; the initial REJECT (High=0, Medium=1, Low=0) and earlier network-gated failures
remain historical.

## Implementer Rework

1. M403A source oracle now reads and hashes the neutral ORM implementation under
   `packages/backend-persistence/src/citeframe_persistence/models/{content_unit,content_unit_embedding}.py`;
   migrations, SQL, metrics, and acceptance semantics are unchanged.
2. R803's recursive AST closure now has fixed source roots for `citeframe_contracts` and
   `citeframe_persistence`; the current package provenance and tests describe the runtime
   closure. Scorer, cases, thresholds, and historical campaign artifacts are unchanged.
3. The exact 80-table/93-index DDL baseline is checked into
   `apps/api/tests/fixtures/citeframe-a1b-before-metadata.json` with SHA-256
   `678ad54b9977cc6258639b92fa65e5976d032ac323428c98ed89215cf02167af`; tests no longer
   depend on a `/tmp` file.
4. Alembic `env.py` now imports `Base` and explicitly loads `citeframe_persistence.models`;
   this changes only metadata ownership at the loading seam and does not change migrations
   or schema. A focused test locks out indirect `ai_pdf_api.db.base` / `ai_pdf_api.models`
   loading from the Alembic environment.

## Implementer Verification

- `uv run --project apps/api pytest apps/api/tests/test_persistence_boundary.py apps/api/tests/test_m403a_capacity_acceptance.py -q`: 19 passed, 1 warning after the Alembic seam test rework.
- API deployment/export boundary tests: 6 passed, 1 warning.
- `uv run --project apps/worker pytest apps/worker/tests/test_deploy_dependencies.py apps/worker/tests/test_research_contracts_package.py apps/worker/tests/test_r803_campaign_v5.py -q`: 60 passed.
- Full API suite: 641 passed, 5 skipped, 1 warning.
- Worker fast suite: 171 passed, 153 deselected.
- Worker acceptance suite: 171 passed, 153 deselected.
- Worker evaluation suite: 61 passed, 263 deselected.
- DDL oracle: exactly 80 tables and 93 indexes; fixture SHA-256 matches the value above.
- R803 closure: 95 modules with both neutral package roots included; no scorer/case/threshold changes.
- Compile, Markdown links/fences, shell syntax, frozen export generation, and `git diff --check`: passed before the Alembic seam rework.
- Independent A1b Critical review: **ACCEPT (2026-08-21; High=0, Medium=0, Low=0)** per the reviewer-owned artifact above; this implementation evidence does not impersonate the reviewer.

## Environment Gates

The Docker and real PostgreSQL gates were run separately during this rework. Initial network
failures remain historical; the follow-up clean Worker image and real PostgreSQL gates passed.

- API image: `docker build --target api -f infra/docker/Dockerfile.python -t citeframe-a1b-api:local .` exited `0`; build-time `backend-contracts-persistence-import-smoke=pass`. Runtime command
  `docker run --rm citeframe-a1b-api:local python -c '...'` returned
  `api-final-runtime-import-smoke=pass tables=80`.
- Worker clean image: the initial standard/host-network builds exited `2` during external
  PyPI downloads and remain historical failures. The follow-up clean build passed with image
  SHA-256 `3e0bfa04d2af6650f500387a74c556f7304fcfe8625fa34b488610593bbe128d`; final runtime
  smoke imported Worker, contracts, and neutral persistence, verified path and identity,
  `tables=80`, UID `10001`, and no `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` in final image
  environment. The final smoke is recorded by the reviewer-owned artifact; no proxy variables
  persisted in the clean image.
- Real PostgreSQL/Alembic gate: using an isolated `pgvector/pgvector:pg17` container on host port `55432`, the stable-readiness retry passed:
  `AI_PDF_DATABASE_URL=postgresql+psycopg://ai_pdf:ai_pdf_dev@127.0.0.1:55432/ai_pdf_workspace uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head` completed through `m7a8b9c0d1e2`; the same environment with `alembic check` returned `No new upgrade operations detected` (only the existing computed-default warning). A runtime query found `80` public tables excluding `alembic_version`, exactly equal to the `80` tables in neutral `Base.metadata.tables`; `postgres-a1b-gate=pass`. The first container attempt hit the image init temporary server, so it was discarded and retried after stable readiness. The temporary container was automatically removed.

## Decision

A1b/A2-foundation was independently accepted on **2026-08-21** by the follow-up Critical
review (`High=0`, `Medium=0`, `Low=0`). A2a `citeframe_research_persistence` is the only
next implementation step; R0/R1/R2/W1, schema/API/save/replay/permission changes, and
downstream product work remain blocked.
