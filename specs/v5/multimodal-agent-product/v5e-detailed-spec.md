# V5-E Detailed Spec: Model Quality and User Value

## 1. Purpose

Define how Citeframe measures **real model quality** (R803 lineage) and
**real user value** (M404) after V5-A–D engineering gates. This stage does not
add product features.

## 2. Prerequisites (already true)

| Gate | Status |
|---|---|
| V5-A provider capability | done |
| V5-B Markdown document | done |
| V5-C multi-agent productization | done |
| V5-D D-G0–D-G7 engineering | done |
| V5-D D-G6 empty-target mixed Compose | done (`v5d-mixed-compose-20260812-01`) |
| R803 formal campaign v1 | immutable **fail** / `not_evaluable` |
| M404 | `not_evaluable` |

## 3. Work packages

### E001 — Re-plan quality suite (this slice)

Deliverables:

- This spec + [`decision-2026-08-12-v5e-scope.md`](decision-2026-08-12-v5e-scope.md)
- Inventory of frozen R803 packages/campaigns (below)
- Verification matrix for V5-E ([`verification-matrix-v5e.md`](verification-matrix-v5e.md))
- Explicit non-resume policy for campaign v1

### E002 — Preserve history

- No write into existing R803 artifact trees
- New runs only under new `r803-campaign-YYYYMMDD-vN/` directories
- Threshold/package SHA binding before first provider call

### E003 — M404 protocol + execution

Blocked until owner supplies:

- target user definition
- task list and success/adoption metrics
- sample size and session protocol
- consent / data handling notes

### E004 — Release judgment

Only after independent engineering, model-quality, and user-value evidence exist.
Possible outcomes: stay `internal_preview`, limited Beta, or public release.
Engineering green alone is never sufficient.

## 4. Frozen inventory (do not mutate)

| Path | Role |
|---|---|
| `docs/evals/artifacts/r803-v1` … `r803-v4` | diagnostic history |
| `docs/evals/artifacts/r803-campaign-20260730-v1` | formal failed campaign |
| `docs/evals/r803-evaluation-package-v5.json` | latest package contract |
| `docs/evals/r803-release-threshold-v1.json` | prospective threshold |
| `docs/evals/r100-research-cases-v2.json` | case suite for package v5 |
| `docs/evals/r803-v5-campaign-threshold.md` | campaign rules |

## 5. Stratified evaluation grid (planned)

Rows = modality × task; columns = provider/model profile.

| Modality | Quick Chat | Research claims | Refusal/conflict |
|---|---|---|---|
| PDF | required | required | required |
| Image | required | required | as covered by suite |
| Markdown Document | required for V5-E extension | required for V5-E extension | as covered by suite |

Current package v5 / cases v2 may still be PDF/Image-heavy. Adding Document
cases requires a **new package version** (v6+) and owner approval; do not
silently stretch v5.

## 6. Runner constraints

- Prefer `apps/worker/scripts/evaluate_r803_campaign.py` and existing
  `r803_evaluation_runtime` contracts
- Formal runs: real configured provider, `provider=None` injection, no test
  provider unless explicitly non-formal
- Persist plan SHA, package SHA, threshold SHA, prompt-binding hashes before
  round-01
- On interrupt: leave partial round markers; never rewrite completed rounds

## 7. Pass language

Allowed after a successful formal campaign (future):

- `modelQualityGate=pass` for the **named package + model + suite only**

Never allowed from V5-D artifacts:

- "product quality passed"
- "users validated"
- "Beta unlocked" without M404

## 8. Open blockers before any paid run

1. Owner cost ceiling and model/profile selection for the campaign
2. Confirm whether Document modality cases need package v6 first
3. Environment secrets for the chosen provider endpoint
4. Explicit "authorize formal R803 campaign" message in an active turn
