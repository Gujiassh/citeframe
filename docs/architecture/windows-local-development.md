# Windows local development

This is the Windows entry point for the existing local-development contracts. It does not
replace [`local-env-profiles.md`](local-env-profiles.md) or the component READMEs.

## Required tools

- Node.js 22+ and pnpm 10.33.4
- Python 3.12+ and `uv`
- Docker Desktop with Compose v2
- Ollama with `qwen3-embedding:0.6b` for the normal `preview` embedding path
- Git and GitHub CLI (`C:\Program Files\GitHub CLI\gh.exe` is a common install path)
- ffmpeg only for video keyframes and audio/video paths that require local media handling

Verify that PowerShell resolves real executables rather than Microsoft Store aliases:

```powershell
node --version
pnpm --version
python --version
uv --version
docker compose version
ollama --version
& 'C:\Program Files\GitHub CLI\gh.exe' auth status
```

## Install and start

From the repository root:

```powershell
pnpm install --frozen-lockfile
uv sync --project apps/api --extra dev
uv sync --project apps/worker --dev
Copy-Item apps/web/.env.example apps/web/.env.local
Copy-Item infra/env/preview.env.example infra/env/preview.local.env
docker compose -f infra/docker/compose.yml up -d
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
```

Replace the Web session signing placeholder in `apps/web/.env.local`. Keep
`AI_PDF_API_INTERNAL_TOKEN` identical in `apps/web/.env.local` and
`infra/env/preview.local.env`.

For native PowerShell, start Web in one terminal without importing the backend profile; Next
loads `apps/web/.env.local` itself:

```powershell
pnpm dev:web
```

In the API and Worker terminals, load `infra/env/preview.local.env` before starting the
process. Run one of the final two commands per terminal:

```powershell
$profile = Resolve-Path infra/env/preview.local.env
Get-Content $profile | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } | ForEach-Object { $k,$v=$_.Split('=',2); Set-Item "Env:$k" $v }

# Run one of these per terminal after loading the backend profile:
pnpm dev:api
pnpm dev:worker
```

The Bash profile helper under `infra/scripts/citeframe-local-env.sh` requires Git Bash or
WSL. Native PowerShell users may start the three host processes directly as above. Keep the
internal token identical between Web and the API/Worker profile; keep provider/model/index
settings identical between API and Worker. `apps/web/.env.local` must define its own
`AI_PDF_SESSION_SECRET`; otherwise a valid API login reaches the BFF but session-cookie signing
fails closed with HTTP 500. Do not export a second Web session secret from the preview backend
profile because process environment would override Next's `.env.local`.

Open <http://localhost:3000>, register a user, create a workspace, upload a fixture from
`docs/fixtures/`, wait for ingestion to become ready, ask a scoped question, open its
Evidence, save a source-linked note, and verify the item survives a page reload.

## Provider profiles

- `preview` uses real Ollama embeddings. A generation key is optional; generation, caption,
  and ASR fail closed when their capability is not configured.
- `preview` must never point generation at the acceptance stub on port `18081`.
- `accept` may use the deterministic stub for engineering gates, but its answers are not
  model-quality evidence.

See [`local-env-profiles.md`](local-env-profiles.md) before switching profiles or reindexing
data created with another embedding fingerprint.

## Gates

```powershell
pnpm --dir apps/web test
pnpm --dir apps/web lint
pnpm --dir apps/web exec tsc --noEmit
pnpm --dir apps/web build
powershell -NoProfile -File infra/scripts/check-r1-delivery-truth.ps1
git diff --check
```

API, Worker, migration, and browser E2E gates additionally require the services above.
SQLite or an in-memory fake cannot replace PostgreSQL for the R2 multi-Worker Critical gate.

## Portable native stack (no administrator access)

When Docker Desktop cannot be installed, the host processes can use a user-owned native
stack without changing application contracts. The verified Windows baseline on 2026-08-31
is:

| Service | Verified build | Endpoint |
| --- | --- | --- |
| PostgreSQL | official EDB 17.11-1 x64 portable binaries | `127.0.0.1:5432` |
| pgvector | 0.8.6, PG17 x64 community CI binary | PostgreSQL extension |
| pg_trgm | PostgreSQL 17 bundled extension 1.6 | PostgreSQL extension |
| MinIO | `RELEASE.2025-09-07T16-13-09Z` Windows x64 | API `9010`, console `9011` |
| accept provider | `apps/api/scripts/provider_m403b_stub.py` | `127.0.0.1:18081` |

Put downloads, binaries, and data below `.local-runtime/` (gitignored). The verified
PostgreSQL archive SHA-256 is
`6EABDF00D2893713B75DB4336A23C3FDF505F056E217EC6E2E95D901750CFEA3`; the verified
pgvector archive SHA-256 is
`E3EC526435674CFDA4C89D719C5745DC5B578B7559A6EAA5C79D2D41BCED9FA8`.
The pgvector artifact is not an official PostgreSQL distribution, so verify its digest and
prove the ABI by executing `CREATE EXTENSION vector` before running migrations.

Initialize PostgreSQL with `initdb --auth=trust --encoding=UTF8 --no-locale`, start it with
`pg_ctl`, then create the Compose-equivalent `ai_pdf` login and `ai_pdf_workspace` database.
The local `ai_pdf` role must be a superuser, matching the Compose `POSTGRES_USER` bootstrap
semantics, because Alembic creates `vector` and `pg_trgm`. Verify both extensions and run:

```powershell
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api alembic -c apps/api/alembic.ini current
```

The expected head is `m7a8b9c0d1e2`. Start MinIO with `--address :9010
--console-address :9011`, load `infra/env/accept.env.example` into the Web, API, and Worker
process environments, and start the accept provider separately. Redis is part of the
deployment Compose baseline, but the current local business path uses PostgreSQL jobs and
does not require Redis to complete the authenticated accept flow. This does not remove
Redis from the deployment contract.

The acceptance provider supports deterministic Quick Answer, embedding, caption, and the
five fixed Research roles. Its structured Research output is plumbing evidence only and
must never be reported as model quality.

Verified native acceptance evidence on 2026-08-31:

- API live and ready passed all database, catalog, object-storage, embedding, generation,
  and image-caption checks.
- Worker ingested the 12-page PDF fixture into PostgreSQL/MinIO.
- Browser flow passed registration, login, workspace creation, settings persistence, PDF
  rendering, Quick Answer with citations, citation navigation, and source-linked note save.
- Fixed-DAG Research completed after plan approval with 4 deterministic model calls, 2 tool
  calls, 6 Evidence items, and 2 Artifacts. This is engineering evidence, not quality evidence.

### Reproduce the verified portable stack

The evidence above was produced from worktree base
`a616eea1350b095c6f229890d2c47e5010902330`. Download PostgreSQL from
`https://get.enterprisedb.com/postgresql/postgresql-17.11-1-windows-x64-binaries.zip`,
pgvector PG17 x64 from the `czkwg8/pgvector-windows-binary` 0.8.6 GitHub release, and
MinIO from `https://dl.min.io/server/minio/release/windows-amd64/minio.exe`. Do not continue
unless the archive digests match those recorded above.

```powershell
$runtime = (New-Item -ItemType Directory -Force .local-runtime).FullName
Expand-Archive .local-runtime/downloads/postgresql-17.11-1-windows-x64-binaries.zip $runtime/postgresql
Expand-Archive .local-runtime/downloads/pgvector-pg17-x64.zip $runtime/pgvector
Copy-Item $runtime/pgvector/vector.dll $runtime/postgresql/pgsql/lib/
Copy-Item $runtime/pgvector/vector.control,$runtime/pgvector/vector--*.sql $runtime/postgresql/pgsql/share/extension/
& $runtime/postgresql/pgsql/bin/initdb.exe -D $runtime/data/postgres --auth=trust --encoding=UTF8 --no-locale
& $runtime/postgresql/pgsql/bin/pg_ctl.exe -D $runtime/data/postgres -l $runtime/data/postgres.log start
& $runtime/postgresql/pgsql/bin/psql.exe -d postgres -c "CREATE ROLE ai_pdf LOGIN SUPERUSER PASSWORD 'ai_pdf_dev'"
& $runtime/postgresql/pgsql/bin/createdb.exe -O ai_pdf ai_pdf_workspace
& $runtime/postgresql/pgsql/bin/psql.exe -d ai_pdf_workspace -c "CREATE EXTENSION vector; CREATE EXTENSION pg_trgm; SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector','pg_trgm') ORDER BY extname"
```

`SUPERUSER` is strictly a **local acceptance bootstrap equivalence** for Compose's initial
`POSTGRES_USER`; it is not a production-role recommendation. Load the accept environment
in every PowerShell that launches Web, API, or Worker. The example contains only local
acceptance placeholders, including the Web session-signing value; do not reuse them outside
an isolated local acceptance environment. Then launch each foreground process:

```powershell
Get-Content infra/env/accept.env.example | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } | ForEach-Object { $k,$v=$_.Split('=',2); Set-Item "Env:$k" $v }
$env:DATABASE_URL='postgresql+psycopg://ai_pdf:ai_pdf_dev@127.0.0.1:5432/ai_pdf_workspace'
$env:AI_PDF_DATABASE_URL=$env:DATABASE_URL
uv run --project apps/api python apps/api/scripts/provider_m403b_stub.py
uv run --project apps/api uvicorn ai_pdf_api.main:app --app-dir apps/api/src --host 127.0.0.1 --port 8000
uv run --project apps/worker python -m ai_pdf_worker.main
pnpm --dir apps/web dev
& $runtime/downloads/minio.exe server $runtime/data/minio --address :9010 --console-address :9011
```

Stop foreground processes with `Ctrl+C`, then stop PostgreSQL with:

```powershell
& $runtime/postgresql/pgsql/bin/pg_ctl.exe -D $runtime/data/postgres stop -m fast
```

Re-run evidence with the commands in **Gates**, the authenticated Playwright command in the
repository task ledger, and both offline and `-Online` R1 delivery-truth checks. The terminal
pass summaries are the test artifacts; no screenshot or deterministic-stub output is a model
quality artifact.

For the Windows LF portability gate, the verified no-admin tool was Git for Windows
`PortableGit-2.55.0.5-64-bit.7z.exe`, downloaded from
`https://github.com/git-for-windows/git/releases/download/v2.55.0.windows.5/PortableGit-2.55.0.5-64-bit.7z.exe`
with SHA-256 `5AA8A20F6E9ABB2C755F0E73C91C687701A46B309AD84A0CA6509380FA4AE290`.
It was extracted below `.local-runtime/portable-git` and its `usr/bin/bash.exe` passed
`bash -n` plus LF-only `file` assertions for the R0 and R1 gates. Nothing was installed
system-wide.
