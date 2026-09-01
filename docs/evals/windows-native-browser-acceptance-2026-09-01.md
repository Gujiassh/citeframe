# Windows Native Browser Acceptance — 2026-09-01

## Scope

- Repository baseline: `main@f115846c8da5b0af7deb829d3dff2d2c25073cd5`
- Runtime: Windows native, no Docker and no WSL
- Database: PostgreSQL 17.11 with pgvector 0.8.6 and `pg_trgm` 1.6
- Object storage: MinIO `RELEASE.2025-09-07T16-13-09Z`
- Provider: local deterministic accept stub on `127.0.0.1:18081`
- Fixture: `docs/fixtures/evidence-contract/pdf-coordinate-fixture.pdf` (12 pages)
- Browser: Codex in-app browser against `http://localhost:3000`

The provider is deterministic engineering infrastructure. Its generated wording is not
model-quality evidence.

## Reproduced Startup Defects

The first run and follow-up independent startup audit reproduced four local-start contract
failures before accepting the product flow:

1. `infra/env/accept.env.example` did not define `AI_PDF_SESSION_SECRET`. API registration
   and credential verification succeeded, but the Web BFF returned HTTP 500 while signing
   the session cookie (`AI_PDF_SESSION_SECRET is required for auth session signing`).
2. The Windows guide used `python -m ai_pdf_worker`; the package has no `__main__`, so the
   Worker exited before polling. The executable module is `ai_pdf_worker.main`.
3. The portable MinIO command pointed to `$runtime/minio/minio.exe`, although the documented
   download is stored at `$runtime/downloads/minio.exe` and no `minio` binary directory is
   created.
4. The preview instructions copied `preview.local.env` but did not load it in the three native
   PowerShell terminals. The Web template also used a different internal-token placeholder,
   so a literal copy could not satisfy the BFF/API internal boundary.

The corrected environment example and Worker command were then used for the positive run.
The post-fix BFF login returned HTTP 200 with `Set-Cookie`, and the Worker entered its polling
loop and completed the ingestion job.

## Browser Flow

| Step | Result | Evidence |
| --- | --- | --- |
| Login | Pass | Existing local acceptance account authenticated through the BFF after the session-secret fix. Account registration itself was also exercised against the real local API. |
| Workspace | Pass | Created a new owner Workspace and persisted its purpose text. |
| Settings | Pass | Saved a distinct system prompt; the exact value survived page reload. |
| Upload and ingestion | Pass | Uploaded the 29 KB PDF fixture through the Web file chooser; UI progressed from upload to analysis and then ready. |
| PDF Viewer | Pass | Viewer reported `/ 12`; direct Asset open rendered page 1. |
| Quick Answer | Pass | A real Chat thread streamed the deterministic answer and returned six persisted citations. |
| Citation navigation | Pass | The first citation opened `PDF p.8`; Viewer page input changed to `8 / 12` and displayed the CropBox locator text. |
| Source-linked Note | Pass | Saved a Note from the p.8 citation; title, excerpt, locator attribution, and user conclusion survived reload. |
| Research plan | Pass | Created a Research Run, received plan revision v1, and approved it in the browser. |
| Research DAG | Pass | All eight displayed stages reached completed; usage ended at four model calls, two tool calls, six Evidence items, and two Artifacts. No conflict decision was required for this deterministic run. |
| Research publication | Pass | Published report and report Evidence were visible, including the p.8 frozen locator. |
| Reload recovery | Pass | Asset, Chat, six citations, Note, settings, completed Run, report, usage, and Artifacts remained available after reload. |
| Browser console | Pass | Final pass contained zero warning/error console entries. |

## Automated Regression

`apps/api/tests/test_windows_local_accept_contract.py` locks the startup boundary:

- committed Web `.env.example` contains API base, internal token, and session signing keys;
- preview and accept profiles use the same internal-token placeholder as the Web template;
  preview Web owns its session secret only in `.env.local`, while the isolated portable accept
  profile carries its local session-signing placeholder because that profile is loaded by Web;
- the Windows guide names `python -m ai_pdf_worker.main` and rejects the non-executable
  package-only command;
- the guide loads `preview.local.env` and starts the actual downloaded MinIO binary.

The browser run does not claim R2-K, model quality, provider quality, or complete R2. R2-K
still requires explicit `A-DATA` authorization because its durable publication recovery
design changes persistence semantics.

The repository's ordinary `web-e2e` CI job does not inject authenticated real-stack
credentials or a PDF path; its authenticated smoke therefore remains conditional, while
other Research browser specs use routed fixtures. The real Windows flow above is separate
manual browser evidence and must not be inferred from a green mocked/conditional CI job.
