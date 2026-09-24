# Multi-file upload queue — issue #35

Date: 2026-09-24
Issue: https://github.com/Gujiassh/citeframe/issues/35
Status: implementation checks complete; independent review and controller browser acceptance pending.

## Scope and invariants

- Both sidebar file inputs select multiple files. Selection order defines FIFO order; later selections append while one transfer is active.
- A queue row is local runtime state: `queued`, `uploading`, `submitted`, or `failed`. `submitted` means server finalize accepted ingestion, including a reconciled lost response; Asset processing status remains independently polled.
- Each selection captures its workspace ID. Switching workspaces filters the visible queue and assets without retargeting requests. The global queue continues the original workspace's transfers in order.
- Failures expose the server/validation message and explicit retry. Retry appends the failed item after already queued work, retains its session, and skips completed transfer stages. Successful rows cannot be retried.
- After an uncertain finalize response, retry locates the existing Asset in the workspace list (detail representations may not exist before ingestion): accepted ingestion states count as submitted; `pending_upload` retries finalize. No successful file is re-created or re-uploaded for this retry.
- Existing production format validation, authenticated routes, upload-session payload, binary transfer, finalize payload, Asset/Evidence schemas, and worker processing remain unchanged.
- Auth owner changes and provider unmount clear the local queue and abort requests. Workspace deletion removes its queue entries and aborts its active request. Abort cannot roll back a server operation already committed.
- File objects live only in memory and are released after successful submission, logout/unmount, or workspace removal. Reload does not resume uploads. A create-session response lost after server commit can leave an orphan pending Asset because the existing API has no client idempotency key; this slice does not change that contract.

## Implementation boundary

- `assets/upload-queue.ts`: FIFO scheduler and local row state; no Asset or HTTP knowledge.
- `assets/upload-task.ts`: existing upload request sequence with retained per-file retry stages.
- `assets/use-upload-queue.ts`: React/auth lifetime and enqueue workspace capture.
- `use-assets.ts`: merges server Asset summaries into the existing workspace-keyed asset store. Existing polling remains responsible for ingestion status; cancelled polls cannot publish late responses after workspace/auth changes.
- `components/upload-queue-list.tsx`: workspace-filtered queue display and failed-item retry.
- `workspace-sidebar.tsx`: both existing pickers enqueue every file and reset immediately for same-file reselection. Selection from the collapsed rail expands the sidebar to expose queue status.

## Verification ledger

- `pnpm --filter @citeframe/web exec tsx --test src/lib/assets/upload-queue.test.ts src/lib/assets/upload-task.test.ts`: 14 passing focused tests.
- `pnpm --filter @citeframe/web test`: 161 passing tests.
- `pnpm --filter @citeframe/web exec tsc --noEmit`: passed.
- `pnpm lint:web`: passed.
- `pnpm build:web`: passed (Next.js 16.2.10 production compilation, TypeScript, static generation).
- `git diff --check`: passed.
- Unit evidence covers FIFO/single concurrency, append, failure continuation, retry, workspace binding/filtering, workspace deletion, abort/late response, same-file reselection, unchanged request bodies, transfer retry, and uncertain finalize reconciliation.
- This ledger does not claim browser usability acceptance or real model ingestion success. Local model providers remain unavailable; no runtime environment configuration was changed.

## Controller walkthrough before merge

1. In an empty test workspace, use the expanded upload button to select multiple supported files. Observe one uploading row, queued rows, and final submitted rows; confirm the resulting Asset list retains separate ingestion statuses.
2. While a transfer is active, select more files and verify FIFO append. Collapse the sidebar and use its upload icon with multiple files; selection exposes queue status again. Select the same file in a later selection.
3. Introduce one controlled upload failure, verify later files continue and the visible error offers retry. Recover and retry only the failed row; verify successful files are not duplicated.
4. During queued work in workspace A switch to B and enqueue B files. Verify A files never appear in B and requests preserve the enqueue workspace. Switch back to check A queue/assets.
5. Log out with a pending queue and confirm no later file starts; sign back in and confirm old local queue is gone. Reload and confirm server Assets survive while local queue does not resume.
6. Independent reviewer checks the exact PR head and runtime evidence before controller merge. No admin bypass.


## Navigation prerequisite and response-order repair

Related issue: https://github.com/Gujiassh/citeframe/issues/38
Baseline source: `39ea097f78db72a3c5211fa210975e1e565bd685` (PR #37 initial implementation).

- Controller browser evidence on this baseline: choosing workspace B in A's sidebar briefly selected B while the URL remained A; route synchronization restored A. Creating B similarly left the route at A. Both upload pickers accepted multiple files; FIFO, failure continuation, failed-row retry and same-file reselection were observed. This is partial acceptance evidence only.
- Sidebar selection and create-and-enter now use Next client navigation. The route remains the active-workspace authority. `createWorkspace` returns the created ID to the UI; existing server payloads and persisted workspace data are unchanged. The shared root-layout WorkspaceProvider retains queue ownership across client navigation.
- `workspaces/navigation.test.ts` covers route selection, awaiting the exact created ID, and preserving the route on creation failure. Controller browser retest is still required.
- Deterministic baseline race: begin an empty Asset hydrate response, insert a newly uploaded Asset, then release the old response through `replaceAssetsForWorkspace`. Actual baseline result was `afterLateHydrate=[]`, `hasProcessingAsset=false`.
- `assets/list-order.ts` guards hydrate/poll responses using workspace mutation revision and applied-request sequence. Upload, deletion/retry responses and workspace removal invalidate older list requests. This guard discards stale responses without merging list contents. Fresh server snapshots remain authoritative and remove deleted assets.
- `assets/list-order.test.ts` exercises the delayed response with a Promise barrier, preserved processing/poll trigger, authoritative deletion, out-of-order responses, and independent workspace revisions.
- Added an uncertain-finalize regression: lost response, a pending list snapshot, delayed 409 conflict, then explicit retry observes uploaded status. Exact bound: one session creation, one binary transfer, two finalize calls; no automatic retry loop.

Rework verification: full frontend suite 161 passed; focused queue/transport suite 14 passed; TypeScript, lint, production build and diff checks pass. Browser acceptance for switching with pending uploads, logout and a successful recoverable retry remains controller-owned and pending.
