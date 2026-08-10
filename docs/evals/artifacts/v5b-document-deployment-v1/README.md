# V5-B Document Formal Deployment Acceptance

This artifact is the canonical B008 isolated deployment evidence for the Markdown-only
`document` v1 slice. It was produced by:

```bash
./infra/scripts/run-v5b-document-acceptance.sh \
  --output-dir docs/evals/artifacts/v5b-document-deployment-v1
```

The run used one isolated Compose project,
`citeframe-v5b-20260808t170050z-3531238`, and built the deployment API, Worker,
and Web images from the current worktree. `report.json` records
`deploymentGate=pass`, `releaseGatePassed=true`, and cleanup with no remaining
containers, volumes, networks, generated image tags, or environment file.

## Built Images

- API: `sha256:3d6747049a4be5905d5374a2157eb16116a125e2cd8720bc3bbae1b60ca5b5ef`
- Worker: `sha256:1b9365f6e760d63a5a452075f624a331677629f32e89f4fa41237839fee77402`
- Web: `sha256:b30bc45188b3568b50a8e43cdcb3cb3233f3c5cb4fb25adaf382e4009a984969`

`image-manifest.json` records the generated tags, creation timestamps, sizes, and
image IDs. The tags were removed during the final cleanup.

## Restore Oracle

The backup was captured after the production browser had created a second
Document asset. The gate verifies both assets independently across a fresh,
empty PostgreSQL/MinIO deployment restore:

- Seed asset with Citation and NoteSource links:
  `e97371d8-88c2-4360-a097-88b15567a403`, semantic SHA
  `a34996f46f01d4d3e6cdb0aa8e79d1fc74db1134b455d2405c4933ffc30e1244`.
- Browser-upload asset without Citation/NoteSource links:
  `ae16b404-bcd7-4f19-ad52-21dcbbaeb85c`, semantic SHA
  `9ff25fb1a9fadb310aa4395798fa07012d19b249c5439ac1905e2b88e173389e`.

For both assets the before and after snapshots contain the same scoped Asset,
Representation, normalized content, block, ContentUnit, embedding, locator, and
MinIO object identities and hashes. The seed oracle additionally requires the
historical Citation and NoteSource chain. The browser-upload oracle explicitly
allows empty evidence links because upload/ingestion does not create those rows.
`backup/SHA256SUMS` contains object prefixes for both assets, and
`verification.json` plus `browser-asset-verification.json` both report
`passed=true`, `livePostgresMinio=true`, and no mismatches.

## Browser Replay

The Web image ran through Caddy using the standalone Next.js server entry from
`infra/docker/Dockerfile.web`. Both pre-restore and post-restore Playwright runs
passed `4/4` tests. The artifacts cover production upload/finalize/Worker ready,
normalized content and blocks, historical Citation reopening, exact range/hash
binding, visible highlighting, and standalone entry provenance.

## Boundaries

This is engineering integration and deployment evidence. The deterministic
provider stub proves provider wiring and fail-closed configuration behavior; it
does not establish model quality or user value. HTML, Office, Audio, Video, ASR,
and temporal locator policies remain outside this Markdown-only slice.
