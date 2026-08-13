# V5-F Verification Matrix

## Evidence classes

| Class | V5-F may claim |
|---|---|
| Engineering unit/integration | yes |
| Production-start browser | yes (scripted provider allowed) |
| Live restore / compose | yes |
| Model quality | **no** (deferred) |
| User value | **no** (deferred) |

## Gates

| Gate | Meaning | Pass |
|---|---|---|
| F-G0 | decision + lanes + inventory | owner-approved decision; no unknown dirty owner |
| F-G-HTML | HTML vertical loop | tests + browser + restore identity for html |
| F-G-DOCX | DOCX vertical loop | same |
| F-G-XLSX | XLSX vertical loop | same |
| F-G-PPTX | PPTX vertical loop | same |
| F-G-ASR | ASR capability fail-closed + configured path | no fake adapter; secret/timeout/error codes frozen |
| F-G-AUDIO | Audio vertical loop | transcript + audio_range + player |
| F-G-VIDEO | Video vertical loop | range/frame + keyframe + player |
| F-G-AGENT | Multi-modal Research A1–A8 | scripted provider OK |
| F-G-MIX | All-enabled mixed Workspace | no cross-kind leakage; restore identity |
| F-G-FULL | Full API/Worker/Web + Critical | engineering ACCEPT; quality still not_evaluable |

## Mandatory commands (baseline)

```bash
uv run --project apps/api python -m pytest apps/api/tests -q --tb=short
uv run --project apps/worker python -m pytest apps/worker/tests -q --tb=short
pnpm --dir apps/web test
pnpm --dir apps/web lint
pnpm --dir apps/web exec tsc --noEmit
pnpm --dir apps/web build
git diff --check
```

Per modality: focused tests + at least one production-start path + restore oracle covering that kind’s object keys.

## Oracle examples

### No cross-kind leakage

Selected scope `{html}` must never return pdf/image candidates.

### Locator truth

Citation open must resolve the same typed detail fields stored at create time.

### ASR missing

Audio upload/ingest must fail closed with stable code before representation rows if ASR unavailable.

### Agent finished artifact

Retry after complete must not rewrite final_report bytes/sha (retain F5).
