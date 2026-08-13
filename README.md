# Citeframe

[![CI](https://github.com/Gujiassh/citeframe/actions/workflows/ci.yml/badge.svg)](https://github.com/Gujiassh/citeframe/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Citeframe is a self-hosted multimodal AI knowledge workspace for organizing heterogeneous assets, asking evidence-grounded questions, conducting research, and preserving traceable knowledge.

![Citeframe research workspace](docs/assets/citeframe-research-workspace-en.png)

## What it does

- Organize assets in isolated workspaces with source-linked context.
- Ingest and understand PDFs and PNG, JPEG, and WebP images in the current production baseline.
- Preserve typed evidence locations for pages, regions, and image areas.
- Search across ready assets with PostgreSQL full-text search, pgvector, and reciprocal rank fusion.
- Use Quick Answer for focused questions or bounded multi-agent Research for complex comparisons.
- Save source-linked notes, tags, chat history, and research artifacts.
- Use the current configured generation provider and switch supported embedding providers through server-side configuration; multiple generation profiles are a V5 capability target.
- Extend the same Asset/Evidence contracts to additional document, audio, and video modalities as they are implemented.
- Run the complete stack on your own infrastructure.

The current feature roadmap is maintained in [`specs/v5/multimodal-agent-product/`](specs/v5/multimodal-agent-product/). PDF/Image production support is available now; additional modalities and provider capabilities are delivered incrementally.

## Getting Started

### Requirements

- Node.js 22+
- pnpm 10.33.4
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker with Compose
- An OpenAI-compatible Responses API endpoint for the current generation baseline
- Ollama with `qwen3-embedding:0.6b`, or another configured embedding provider

### Install dependencies

```bash
pnpm install --frozen-lockfile
uv sync --project apps/api --extra dev
uv sync --project apps/worker --dev
```

### Start local services

```bash
docker compose -f infra/docker/compose.yml up -d
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
```

The development Compose file starts PostgreSQL, Redis, and MinIO. The Web, API, and Worker processes run on the host.

### Local environment profiles (preview vs accept)

Do **not** leave daily product Q&A pointed at the M403B acceptance stub (`:18081`).

- **preview** — real generation provider for product use
- **accept** — deterministic stub for engineering gates only

See [`docs/architecture/local-env-profiles.md`](docs/architecture/local-env-profiles.md) and:

```bash
cp infra/env/preview.env.example infra/env/preview.local.env
# edit keys, then:
infra/scripts/citeframe-local-env.sh preview start --with-web
```

### Configure the application

Create the Web environment file:

```bash
cp apps/web/.env.example apps/web/.env.local
```

Set a shared `AI_PDF_API_INTERNAL_TOKEN` for the Web BFF and API, then configure the generation and embedding providers for the API and Worker. The API and Worker must use the same embedding provider, model, and index version.

See [API configuration](apps/api/README.md), [Worker configuration](apps/worker/README.md), and [Docker configuration](infra/docker/README.md) for the available environment variables.

### Run Citeframe

Open three terminals from the repository root:

```bash
pnpm dev:web
```

```bash
pnpm dev:api
```

```bash
pnpm dev:worker
```

Open [http://localhost:3000](http://localhost:3000), create an account, and start a workspace.

## Deployment

The deployment Compose file builds and runs the complete stack behind Caddy.

```bash
cp infra/docker/.env.deploy.example infra/docker/.env.deploy
```

Fill in the passwords, shared token, session secret, model configuration, and site address, then run:

```bash
docker compose \
  --env-file infra/docker/.env.deploy \
  -f infra/docker/compose.deploy.yml \
  up -d --build
```

The [deployment guide](infra/docker/README.md) covers configuration, health checks, logs, metrics, backups, and restores.

## Development

```bash
# Web
pnpm --dir apps/web test
pnpm --dir apps/web lint
pnpm --dir apps/web exec tsc --noEmit

# API and Worker
uv run --project apps/api pytest apps/api/tests
uv run --project apps/worker pytest apps/worker/tests
```

## Repository Layout

```text
apps/web/       Next.js application and BFF
apps/api/       FastAPI service and database migrations
apps/worker/    ingestion, OCR, embeddings, and research jobs
infra/docker/   development and deployment Compose files
packages/       shared TypeScript packages and prompt contracts
docs/           product, architecture, operations, and design notes
specs/          versioned feature specifications
```

## Documentation

- [Product design](docs/ssot/product-design.md)
- [System architecture](docs/ssot/system-architecture.md)
- [Implementation roadmap](docs/architecture/implementation-roadmap.md)
- [Implementation progress](docs/architecture/implementation-progress.md)
- [V5 multimodal and agent plan](specs/v5/multimodal-agent-product/plan.md)
- [Research workflow](docs/architecture/research-workflow-runtime.md)
- [Web development](apps/web/README.md)
- [API development](apps/api/README.md)
- [Worker development](apps/worker/README.md)
- [Deployment](infra/docker/README.md)

## License

Citeframe is licensed under the [Apache License 2.0](LICENSE).
