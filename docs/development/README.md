# Development

## Setup

Use Node.js 22+, pnpm 10.33.4, Python 3.12+, uv, Docker/Compose v2, and an embedding provider. Default local embedding uses Ollama with `qwen3-embedding:0.6b`. Audio/video needs ASR; optional video keyframes need ffmpeg/ffprobe.

From repository root:

```bash
pnpm install --frozen-lockfile
uv sync --project apps/api --extra dev
uv sync --project apps/worker --dev
cp apps/web/.env.example apps/web/.env.local
cp infra/env/preview.env.example infra/env/preview.local.env
docker compose -f infra/docker/compose.yml up -d
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
```

Share `AI_PDF_API_INTERNAL_TOKEN` between Web and API/Worker. Set independent `AI_PDF_SESSION_SECRET` for Web. API/Worker share database/object storage and model/index bindings. Workspace overrides need the same persistent `AI_PDF_MODEL_CONFIG_ENCRYPTION_KEY` in API/Worker.

See [profiles](../guides/local-environment.md), [model configuration](../guides/model-configuration.md), and [Windows setup](../architecture/windows-local-development.md). Start separate terminals with `pnpm dev:web`, `pnpm dev:api`, and `pnpm dev:worker`.

## Tests

```bash
pnpm --dir apps/web test
pnpm --dir apps/web lint
pnpm --dir apps/web exec tsc --noEmit
pnpm --dir apps/web build

uv run --project apps/api pytest apps/api/tests
uv run --project apps/worker pytest --strict-markers -m "not acceptance and not evaluation" apps/worker/tests
uv run --project apps/worker pytest --strict-markers -m acceptance apps/worker/tests

uv sync --project tools/evaluation --frozen --dev
uv run --project tools/evaluation pytest --strict-markers tools/evaluation/tests
uv run --project apps/api alembic -c apps/api/alembic.ini check

git diff --check
```

API includes PostgreSQL-backed tests; use local database and the explicit configuration required by each module. Deterministic fixtures do not replace PostgreSQL concurrency/recovery. CI builds evaluation images and exercises real service recovery/deployment scripts.

Browser tests:

```bash
pnpm --dir apps/web exec playwright install chromium
pnpm --dir apps/web e2e
```

Inspect [Playwright configuration](../../apps/web/playwright.config.ts) for server/fixture requirements. Real authenticated tests need the corresponding stack.

## Change boundaries

Keep business APIs/auth in FastAPI, UI/session/BFF in Web, ingestion/Research orchestration in Worker, and neutral contracts/persistence in shared packages. See [architecture](../architecture/README.md).

Schema, saved payload, locator, and source-history changes require matching migrations, API/types, tests, and docs. Shared dependency changes must keep three consumers aligned:

```bash
uv lock --project apps/api --check
uv lock --project apps/worker --check
uv lock --project tools/evaluation --check
```

[CONTRIBUTING](../../CONTRIBUTING.md) covers issue/PR expectations. [Evaluation](evaluation.md) describes frozen inputs.
