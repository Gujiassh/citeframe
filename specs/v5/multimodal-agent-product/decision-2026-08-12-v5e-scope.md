# Decision: V5-E Model Quality and User Value Scope

Date: 2026-08-12  
Status: **approved for planning / package freeze only**  
Does not authorize a paid provider campaign or M404 user study by itself.

## Context

V5-A through V5-D engineering gates are complete for `internal_preview`.
R803 formal campaign `artifacts/r803-campaign-20260730-v1/` is immutable failed
evidence. M404 has no qualified user evidence. Product stage remains
`internal_preview`.

## Decisions

1. **V5-E is evidence-first, not feature work.** No new modality, registry
   version, provider selector, or save/replay contract is required to enter V5-E.
2. **Immutable history.** Paths under `docs/evals/artifacts/r803-v1/` …
   `r803-v4/` and `docs/evals/artifacts/r803-campaign-20260730-v1/` must not be
   overwritten, resumed, or re-run in place.
3. **New campaign = new directory.** Any future formal R803 attempt uses a new
   artifact root of the form
   `docs/evals/artifacts/r803-campaign-YYYYMMDD-vN/` with a fresh
   `campaign-plan.json` frozen before the first provider call.
4. **Four evidence classes stay distinct:**
   - engineering regression (V5-D already green)
   - live deployment/restore (V5-D D-G6 green)
   - model quality (R803 / successor)
   - user value (M404)
5. **No quality claim from engineering.** Scripted providers, unit suites, and
   compose restore never set `realModelQualityPassed` or `userValuePassed`.
6. **Stratification for the next quality suite (E001):**
   - modality: PDF, Image, Markdown Document (Audio/Video remain out of registry)
   - task: Quick Chat answer, Research plan/claims/artifact, refusal/conflict
   - provider/model: only server-resolved frozen profiles already in V5-A
   - suite: start from `r100-research-cases-v2.json` + package v5; extend only
     with explicit owner approval and new package version
7. **M404 (E003) remains blocked** until a written protocol names target users,
   tasks, sample size, and adoption metrics; no synthetic stand-in is allowed.
8. **Paid provider runs require an explicit owner turn** after package freeze
   and cost ceiling approval. This decision alone does not authorize spend.

## Non-goals

- Resuming failed campaign v1
- Declaring Beta or public release
- Using mixed-compose or D-G7 green as model-quality evidence
- Enabling HTML/Audio/Video under the quality suite without OD-B decisions

## Exit for E001 (this decision)

E001 is complete when the V5-E detailed plan, verification matrix, and frozen
package inventory are committed and linked from `tasks.md` / progress docs.
It is **not** complete when a model run finishes.


## Owner deferral: paid formal R803 (2026-08-13)

Owner decision: **skip paid formal R803 campaign for now**. Do not start
provider-backed quality runs, do not spend on evaluation, and do not treat
engineering green as model quality. Continue free modules (engineering residuals,
modality design only when OD approved, docs/tooling). Re-open only with an
explicit cost ceiling + profile authorization in an active turn.
