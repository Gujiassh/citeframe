# Evaluation and reproducibility

The offline `tools/evaluation` package provides paired Quick/Research evaluation, prospective campaigns, and scenario drivers. Production API/Worker and neutral persistence do not depend on it. Production Docker excludes it; the explicit evaluation target packages its commands.

```bash
uv sync --project tools/evaluation --frozen --dev
uv run --project tools/evaluation citeframe-evaluate --help
uv run --project tools/evaluation citeframe-campaign --help
uv run --project tools/evaluation citeframe-research-acceptance --help
uv run --project tools/evaluation pytest --strict-markers tools/evaluation/tests
```

## Evidence scope

Deterministic providers test state, provenance, concurrency, retry, and recovery. Model quality needs actual model outputs judged against specified cases. Target-user value needs real tasks and repeated use. These are separate measurements.

Campaigns bind package, threshold, scorer, prompt, provider, and implementation-closure hashes before calls. Formal rounds/terminal results are immutable. Injected providers are explicitly non-formal. Failed incomplete campaigns cannot establish quality.

## Scenario invariants

Parallel execution requires distinct consumers/branches and overlapping linked provider intervals. Serial negative controls complete ordinary work while rejecting concurrency.

Recovery must abandon the original Attempt and succeed the next Attempt of the same Step with unchanged Workspace/input/snapshot. Another Step's success is insufficient. Publication is unique and checks creator membership; reservations/ledgers must be complete and scoped.

Snapshot bodies/children are checked against original rows and hashes. Request proofs bind received wire bytes to persisted calls by scope/model/output limit/digest/time window. Every send needs a unique proof; missing/ambiguous/foreign/duplicate/tampered evidence fails. Synthetic proof servers must not receive real user data or production credentials.

## Services and deployment

Locks and multi-consumer recovery use PostgreSQL/object storage. Deployment tests exercise existing backup/restore scripts and ordinary Compose Worker consumption. The product-delta manifest admits exact source blobs/provenance; pinned changes require the existing verification procedure.

[Evaluation inputs](../evals/README.md) retain fixed historical paths, packages, and hashes. Use new output directories and preserve old results.
