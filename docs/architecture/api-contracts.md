# API contracts

FastAPI business routes use `/v1`; browser requests use Next.js `/api` BFF. The running API exposes generated OpenAPI at `/openapi.json`. [Routers](../../apps/api/src/ai_pdf_api/routers/) and [Pydantic schemas](../../apps/api/src/ai_pdf_api/schemas/) define fields and validation.

## Authentication and scope

BFF authenticates a signed httpOnly session, then forwards `x-user-id` and `x-ai-pdf-internal-token`. FastAPI checks the internal token before accepting user identity. Registration, login, and health endpoints retain public behavior.

Workspace routes validate database membership and stored owner roles. Missing membership uses the existing not-found response to limit enumeration. Resource IDs are scoped to the URL Workspace even when a user belongs to both Workspaces. [Workspace access](workspace-access.md) documents membership helpers, route-specific validation/owner checks, and stream revalidation.

Ordinary business errors use FastAPI `detail`. Research has `error.code/message/requestId/retryable/details`. Model-settings validation/provider failures sanitize secret-bearing input. BFF preserves upstream failure status.

## Assets and jobs

Upload uses three steps: create `/assets/upload-session`, PUT `/{assetId}/upload`, then POST `/{assetId}/finalize-upload`. API validates MIME/signature, declared size, and upload limit. Finalization rechecks immutable source identity and creates an ingestion job.

Workspace-scoped Asset reads expose current processing/index state and errors. File/content routes validate Workspace, Asset, generation, and representation. Retry, reindex, asynchronous delete, and delete-retry return persisted job state. Reindex can preserve a ready Asset while a replacement job runs.

`/jobs/{jobId}` reports processing status. Successful upload does not imply search readiness. See [uploads](../guides/uploads.md).

## Chat, citations, and notes

Chat uses explicit `assetScope` or ready Workspace sources and persists actual scope with messages. Output streams through Chat SSE. Citations carry immutable typed locators, display snapshots, and source versions; indices start at 0 and rendered `[n]` maps to `n - 1`.

Image-region targets bind Asset, processing generation, normalized coordinate space, and regions. The server resolves authoritative representation, excerpt, and orientation from authorized evidence.

Notes copy real Workspace citations or supported explicit targets. Deletion affects availability without rewriting saved locator/title/excerpt. Tags are Workspace scoped. See [Evidence](evidence.md).

## Model settings

`GET/PATCH /v1/workspaces/{workspaceId}/model-settings` is owner-only. Generation/embedding inherit defaults or override an entire connection. PATCH uses `expectedRevision`; saving both is atomic. Responses expose key presence without plaintext/ciphertext. [Model configuration](../guides/model-configuration.md) covers protocols, encryption, network controls, and reindexing.

## Research and Evaluation

All paths below are under `/v1/workspaces/{workspaceId}/research-runs`:

| Method | Suffix | Purpose |
| --- | --- | --- |
| GET / POST | root | List/create runs |
| GET | `/{runId}` | Persisted run/step/decision/artifact view |
| POST | `/{runId}/cancel` | Creator cancellation with version checks |
| POST | `/{runId}/plan-decisions/{decisionId}` | Bound plan decision |
| POST | `/{runId}/conflict-decisions/{decisionId}` | Bound conflict decision |
| POST | `/{runId}/steps/{stepId}/retry` | Retry eligible failed step |
| GET | `/{runId}/events` | Persisted sequence replay with `Last-Event-ID` |
| GET | `/{runId}/artifacts` | Artifact list |
| GET | `/{runId}/artifacts/{artifactId}` | Provenance detail |
| GET | `/{runId}/artifacts/{artifactId}/content` | Hash-checked content |
| GET / PUT | `/{runId}/report-edit` | Separate unverified edition |

Members may read Workspace runs/artifacts. Controls and editing require creator authorization plus state/version checks. Workspace ownership alone does not confer report-creator privileges. Idempotency/frozen hashes prevent concurrent overwrite.

Research SSE is independent of Chat SSE. It replays persisted sequences and revalidates membership with fresh sessions. No database session remains open for the full stream.

Evaluation reads are owner-only with `Cache-Control: no-store`. Browser clients have no Evaluation write endpoint. Trusted offline import writes immutable suite/run/case rows atomically. See [evaluation](../development/evaluation.md).
