# Workspace authorization

## Authentication and membership

The Web BFF authenticates its signed session and supplies `x-user-id` and `x-ai-pdf-internal-token` to FastAPI. In [`routers/deps.py`](../../apps/api/src/ai_pdf_api/routers/deps.py), `require_user_id` depends on `require_internal_api_token`; the token is checked before the forwarded user ID is trusted. A browser-supplied role does not grant membership. Public registration/login and authenticated workspace creation/listing have their own routes.

`base_workspace_query_for_user` joins `Workspace` and `WorkspaceMembership`, filters by user ID, and excludes archived workspaces. `get_accessible_workspace(db, user_id, workspace_id)` adds the workspace ID filter and returns `(workspace, role)`. Missing or inaccessible workspaces return 404 `Workspace not found.`. Routes invoke this helper with their database session; it is an ordinary function, so repeated calls do not share a FastAPI dependency-cache entry.

Some routes also require a persisted User. `require_existing_user` returns 401 `Authenticated user not found.` for an unknown user. Workspace detail explicitly checks that user before membership; the jobs route checks membership without that extra user lookup. These entry points can therefore return different errors for the same unknown identity.

## Owner checks and validation

Handlers apply operation-specific checks after membership lookup. Workspace settings and archival require the stored owner role. Model-settings and evaluation routers have local `_require_owner` helpers with their own 403 messages. Chat thread archival permits a workspace owner or that thread's creator. Resource-level and service-level checks still apply to these operations.

FastAPI validates declared body/query/header inputs, and authentication/database dependencies resolve before endpoint execution. Membership and owner checks in the endpoint body run after that declared input validation. Validation details and any additional user checks remain route-specific; authorization is not mounted as one eager workspace-wide dependency. Model settings use `SecretSafeRoute` to sanitize invalid bodies and model-configuration errors. Research uses its own structured error envelope.

The route implementations are in [workspaces](../../apps/api/src/ai_pdf_api/routers/workspaces.py), [model settings](../../apps/api/src/ai_pdf_api/routers/model_settings.py), [evaluation](../../apps/api/src/ai_pdf_api/routers/evaluation.py), and [chat](../../apps/api/src/ai_pdf_api/routers/chat.py).

## Resource and write scope

Membership authorizes access to a workspace; each requested job, asset, representation, thread, note, tag, run, artifact, or evaluation resource also needs a workspace-scoped lookup. For example, [`jobs.py`](../../apps/api/src/ai_pdf_api/routers/jobs.py) queries both job ID and workspace ID, and [`assets.py`](../../apps/api/src/ai_pdf_api/routers/assets.py) checks asset ID, workspace ID, and deletion state. Membership in workspaces A and B does not make B's resource valid on an A URL.

Report editing additionally checks creator identity, run state, `expectedVersion`, and original artifact identity/hash inside [`research_report_edit.py`](../../apps/api/src/ai_pdf_api/services/research/research_report_edit.py). Workspace ownership does not confer report-creator privileges. Publication/adoption locks, transactional persistence checks, and Worker archive/revocation behavior remain separate from HTTP membership lookup.

## Research event streams

[`research.py`](../../apps/api/src/ai_pdf_api/routers/research.py) validates `Accept` and `Last-Event-ID` before the initial membership lookup. One short session from `RESEARCH_EVENT_SESSION_FACTORY` authorizes the workspace, reads the scoped run and initial events, and closes before `StreamingResponse` is returned.

The polling iterator opens fresh short sessions and revalidates membership before reading further events. It does not retain a database session for the stream's lifetime. Revoked membership or workspace archival is observed through those fresh queries.
