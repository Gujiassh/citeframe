# Real-service Research acceptance

## Scope and fixtures

`infra/testing/test_research_services.py` uses migrated disposable PostgreSQL databases named `pr28_<random>` and corresponding dedicated S3 buckets. It calls the production Research API via TestClient and launches independent OS processes running the production `ResearchWorkProcessor`. Model generation and embedding vectors use deterministic synthetic capabilities; retrieval uses the production PostgreSQL query path. No paid provider is called. The service suite is separate from the historical A2 oracle.

The publication crash hook exits the entire Worker with code 86 after a successful production S3 PUT and before the saga marks the object uploaded. Recovery observes the unmodified 60-second publication claim and 300-second attempt leases against real database time. A claim takeover while the attempt lease remains valid must not publish. The suite records before/after Research-domain rows, object keys/hashes, timestamps, process IDs, exit codes and logs. It checks one final artifact/event, unchanged provider calls/budgets, cancellation and creator revocation compensation, and unrelated object preservation.

The positive restore path performs actual pg_dump/pg_restore into a second empty database, copies synthetic objects into its separate bucket, validates the original report, then creates a distinct task through the API and completes it with new Worker processes. An injected publication transport failure must leave no final artifact before a later recovery.

## Reproduction

Provide `CITEFRAME_SERVICE_ADMIN_URL` (disposable PG17 cluster with pgvector), `AI_PDF_DATABASE_URL` (initial admin connection), `AI_PDF_MINIO_ENDPOINT`, `AI_PDF_MINIO_ACCESS_KEY`, `AI_PDF_MINIO_SECRET_KEY`, and matching PostgreSQL17 client binaries on PATH. The role needs CREATE DATABASE only in that isolated cluster. Set PYTHONPATH to repository `apps/api/src`, `apps/worker/src`, all three backend package `src` directories and `infra/testing` using the OS path separator. Run:

```sh
uv sync --project apps/api --frozen --extra dev
uv run --project apps/api pytest -q infra/testing/test_research_services.py --basetemp service-evidence
```

`.github/workflows/research-services.yml` provisions its own PG17 and digest-pinned MinIO; checkout is the PR head SHA, not the synthetic merge commit. It uploads the isolated evidence directory, including synthetic restore dump. Local runs retain uniquely named resources for diagnosis; never point the suite at a shared application database. Review the run SHA and actual assertions before accepting a gate.

## Current verification boundary

Implementation and local execution are in progress. No same-HEAD service PASS is recorded yet. Browser-visible UI, workspace-switch behavior, live HTTP server transport and paid model quality are not covered by this suite. Report-edit two-connection acceptance belongs to the stacked #29 delta.

## Recovered step error repair

Real cross-process recovery identified that a reclaimed Step retained lease_expired after a new attempt succeeded, which correctly caused strict final-publication provenance validation to reject that Step. The minimal production delta clears only Step.error_code/error_message inside the successful new-attempt lease transaction. Prior Attempt errors and abandonment events remain unchanged. No publication success predicate, fixture history, timeout or oracle is relaxed. Dedicated regression exercises reclaim, second lease and completion; downstream #25 supplies the full recovered-gate PG/S3 chain.

Local development evidence: both cancel/revoke after-PUT crash compensation cases passed against real PG/S3. Positive original-run recovery and dump/restore succeeded; the initial post-restore test exposed an expected due terminal sweep preceding new-intent recovery. The harness now explicitly drains the original terminal maintenance schedule to idle before restore; exact-HEAD CI still must pass.
