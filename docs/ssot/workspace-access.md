# Workspace access dependencies

## Current API boundary

The Web BFF authenticates its session and supplies `x-user-id` and
`x-ai-pdf-internal-token`. FastAPI verifies the internal token before trusting the user ID.
The workspace path is authorized against the database; browser-supplied role or user
headers do not grant membership. Public registration/login and auth-only workspace
creation/listing remain separate from workspace-member routes.

`routers/deps.py` owns the member policy and typed `WorkspaceAccess`:
`user_id`, `workspace_id`, `role`, and the already-loaded `Workspace` ORM object.
`require_workspace_member` excludes archived workspaces and returns the existing
404 `Workspace not found.` response for missing membership. It keeps no cross-request
state. `require_workspace_member_existing_user` preserves the routes that first require
an existing user. In particular, an unknown user receives 401 on workspace detail and
404 on a jobs request with otherwise valid internal authentication.

`require_workspace_owner` is the default owner dependency. `WorkspaceOwnerDependency`
configures the existing route-specific owner error message and shares its `check` method
with validation-first route dependencies. No role values or owner privileges change.

## Validation and request caching

All 56 workspace-path operations in jobs, model settings, workspaces, assets, chat,
notes, research, and evaluation declare a typed access dependency. Simple reads use
the shared member or owner callable directly. Routes with validated body/query inputs
use thin local dependencies returning `WorkspaceRequest[T]`: FastAPI validates those
inputs once, then the dependency applies the shared member/owner policy. The endpoint
consumes those same typed inputs. Existing-user dependencies remain before validation
where the baseline had that order.

This preserves invalid-body/query responses before membership/owner errors. Model
settings retain their secret-safe validation error body; research retains its distinct
error envelope. No permission dependency is blanket-mounted ahead of route validation.
FastAPI's default per-request dependency cache stays enabled. When a router dependency
and a parameter share the same member callable, including a nested owner dependency,
they share one membership query and one access object. Validation-first wrappers must
also be reused as the same callable if mounted in more than one position; do not mount
a separate eager member check on those routes.

SSE validates Accept and Last-Event-ID before its initial member lookup. That lookup
uses a short session from the research event session factory. The handler opens another
short session for the initial scoped run/events read, closing it before streaming.
Polling retains fresh-session membership revalidation. No database session is retained
for the lifetime of a stream.

## Resource and write boundaries

Membership authorization does not authorize arbitrary resource IDs. Jobs, assets,
representations, threads, notes, tags, runs, artifacts, and evaluation resources retain
their workspace-scoped queries and nested-resource checks. A user who belongs to both
A and B cannot address B resources through an A path.

Report editing still checks creator identity, run state, expectedVersion, original
artifact identity/hash, and transactional permission inside
`services/research/research_report_edit.py`. Workspace ownership does not confer report
creator privileges. Shared research-persistence checks, publication/adoption locks,
and Worker runtime revocation behavior remain unchanged. This refactor does not extend
Worker behavior for archived workspaces.

## Evidence and limitations

The scoped implementation/evidence ledger is
[`issue40-workspace-access-dependencies-20260928.md`](../../specs/v5/post-v5-optimization/issue40-workspace-access-dependencies-20260928.md).
It records the baseline HTTP oracle, executable graph/cache/scoped-query tests, isolated
PostgreSQL/MinIO API checks, and completed controller-owned visible-browser acceptance for the recorded paths.
No schema, public payload, policy engine, RLS, billing, or provider behavior changes.
