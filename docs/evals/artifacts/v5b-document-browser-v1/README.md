# V5-B Document production-start browser evidence

This directory records the Markdown-only Document live browser gate against:

- the Next.js standalone server entry from `infra/docker/Dockerfile.web`;
- a live FastAPI process;
- a long-running Worker process;
- live PostgreSQL and MinIO;
- the repository's scripted Ollama-compatible provider for engineering-only embeddings.

The scripted provider proves integration behavior only. It is not model-quality evidence.

## Result

The focused Playwright suite completed `4 passed` against `http://localhost:3100`:

1. checked-in Markdown bytes and parser/normalization fixture SHA;
2. upload session, source PUT, exact finalize envelope, Worker completion, ready Asset, normalized content and seven blocks;
3. historical Citation reopen into the Document viewer with the exact generation, block, range, text SHA and visible highlighted span;
4. Dockerfile/standalone entry contract.

`localhost` is intentional. Production session cookies are `Secure`; the browser treats localhost as a local secure context, while plain `http://127.0.0.1` does not reliably return the cookie. The server still binds only to `127.0.0.1`.

## Artifacts

- `production-start-run.json`: code revision, dirty-worktree disclosure, build ID, standalone server SHA, observed process commands/PIDs, readiness, log SHA values, Playwright exit code and clean SIGTERM shutdown.
- `production-start-playwright.log`: exact focused Playwright output.
- `standalone-api.log`, `standalone-worker.log`, `standalone-web.log`, `standalone-provider.log`: process logs used by the run manifest.
- `production-start-upload.json`: exact upload/finalize/job/Asset/Representation/content result.
- `document-historical-citation.json`: frozen Citation and viewer-highlight oracle.
- `document-historical-citation.png`: rendered Document viewer evidence.
- `standalone-entry-check.json`: Dockerfile and local standalone path check.

The private login state contained a synthetic local account and was stored only under `/tmp`; it is not part of this artifact set.

## Relationship To B008

This run provides real standalone browser behavior and process provenance, but the API and Worker ran as host production processes rather than built deployment images in an isolated Compose project. It therefore does not satisfy B008 by itself. The formal isolated gate is now recorded separately in `../v5b-document-deployment-v1/`, including built API/Worker/Web image IDs, dual-asset restore verification, project teardown and zero residue.
