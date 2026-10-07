# Contributing

Citeframe is in Preview. Reproducible bug reports, documentation fixes, and focused pull requests are welcome.

## Issues

Use the issue templates. Include version/commit, environment, steps, expected/actual behavior, and sanitized logs. Use synthetic source files. Feature requests should explain the user task and expected outcome.

Keep keys, tokens, private documents, personal data, and credentials out of public issues. See [SECURITY](SECURITY.md) for sensitive reports.

## Pull requests

Follow [setup/tests](docs/development/README.md) and [architecture](docs/architecture/README.md). Keep changes focused; test affected behavior and update setup, limits, or contract docs.

Schema/saved-source changes need migration and history/recovery coverage. Providers need protocol/configuration/network/secret tests. Format additions need ingestion, locator, retrieval, viewer, and cleanup coverage.

Run relevant tests/type checks and `git diff --check`. Describe impact, verification commands, limitations, and unrun service/paid-model tests. Preserve frozen evaluation inputs/provenance.

The project uses [Apache 2.0](LICENSE). Contribute only material you have permission to share.
