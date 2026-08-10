# Document modality fixtures (V5-B Markdown-only)

Ownership: `B-INT-MIXED` / integration-recovery lane.

These fixtures are API-shaped Markdown contract oracles for mixed-workspace lifecycle,
citation/NoteSource projections, fail-closed parse contracts, and restore table presence.
Cross-layer mixed lifecycle integration coverage lives at
`apps/worker/tests/test_v5b_mixed_workspace.py` (Worker project; not API project).
They intentionally do **not** own Worker adapter unit tests (`B-WORKER-DOC`) or Web
renderer production modules (`B-WEB-DOC`).

## Files

| Path | Purpose |
|---|---|
| `markdown-note.md` | Canonical UTF-8 Markdown source bytes |
| `markdown-note.fixture.json` | Source SHA, parser/normalization versions, normalized text, blocks, locator snapshots, retrieval/citation/NoteSource projections, failure contracts, lifecycle invariants |
| `document-citation.json` | Expected Citation envelope projection |
| `document-note-source.json` | Expected NoteSource envelope projection |
| `mixed-workspace.manifest.json` | PDF + Image + Document mixed workspace shape |

## Regeneration note

`markdown-note.fixture.json` block IDs and character ranges must stay aligned with
`document-parser-v1` / `document-normalization-v1`. If the production Markdown parser
changes, regenerate this fixture in the same slice as the parser change and keep the
SHA oracles in the focused integration suite green.

## Failure contracts

Invalid UTF-8, non-Markdown MIME, empty bytes, NUL binary, and binary signatures must
fail **before** derived Representation / ContentUnit / locator persistence. See
`failureContracts` in `markdown-note.fixture.json`.
