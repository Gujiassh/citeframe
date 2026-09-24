# Upload queue runtime

The sidebar's expanded and collapsed upload pickers accept multiple files. The client enqueues files in selection order with a single active upload, and later selections append. The collapsed picker opens the sidebar after selection to show queue status.

Local queue rows use `queued`, `uploading`, `submitted`, and `failed`. Asset ingestion remains a separate backend lifecycle; submitted rows do not imply documents are ready for retrieval. The Asset list continues using the existing polling path.

The queue is owned by the authenticated workspace provider, with workspace IDs captured on enqueue and workspace-filtered display. Workspace switching preserves pending transfers and their original destinations. Logout, authentication owner changes, and unmount abort outstanding requests and release local files. Deleting a workspace removes its queue entries. Files are not persisted or resumable after reload; abort does not roll back a server commit.

Failed rows support explicit retry at the end of the waiting queue. Retained upload sessions avoid creating a second Asset for transfer retries. After an uncertain finalize response, retry reads that Asset's status before attempting finalize again. Already submitted rows have no upload retry action; backend ingestion failures continue through the existing Asset retry flow. An uncertain upload-session creation response can leave a pending server Asset under the existing non-idempotent contract.

No backend schema, API, permission, Evidence, or save contract changes are part of this feature. Existing upload format validation and request payloads are preserved.

Implementation and acceptance ledger: [issue #35](../../specs/v5/post-v5-optimization/issue35-upload-queue-20260924.md). User-visible acceptance remains pending until the controller records the real browser walkthrough.
