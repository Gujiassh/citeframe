# HTML modality fixtures (V5-F)

Ownership: F-HTML lane.

These fixtures document the sanitizer/resource policy and parse oracle for
`asset_kind=html`. Production catalog enablement is **not** claimed here; see
`S0_HANDOFF.md`.

## Files

| Path | Purpose |
|---|---|
| `note.html` | Canonical UTF-8 HTML source with script that must be stripped |
| `html-note.fixture.json` | Versions, sanitizer policy snapshot, expected block kinds |

## Policy versions

- parser: `html-parser-v1`
- sanitizer: `html-sanitizer-v1`
- normalization: `html-normalization-v1`
- locator: `html_anchor` (`block_id`, `char_start`/`char_end`, `text_sha256`, optional `css_path_hint`)
