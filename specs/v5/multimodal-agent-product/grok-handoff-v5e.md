# Grok Handoff: V5-E Model Quality / User Value

## Task

Advance **one** authorized V5-E slice:

1. **E001 docs** (default if no paid-run authorization): keep plan/inventory current
2. **Formal R803 campaign** only after owner authorizes spend and profile
3. **M404** only after protocol approval

## Mandatory reading

1. `decision-2026-08-12-v5e-scope.md`
2. `v5e-detailed-spec.md`
3. `verification-matrix-v5e.md`
4. `docs/evals/r803-v5-campaign-threshold.md`
5. `docs/evals/r803-real-model-first-run.md`

## Hard constraints

- Do not overwrite or resume frozen R803 artifacts
- Do not claim quality from engineering tests
- Do not start paid provider campaigns without an explicit owner message
  in the active turn that names cost ceiling and model/profile
- Do not invent M404 users or synthetic adoption metrics
- English commit messages; commit/push only when the user asks

## Delivery report

1. Slice ID (E001 / campaign / M404)
2. Artifact paths and SHAs
3. Whether any provider call was made (yes/no + count)
4. Gate results with honest `not_evaluable` where applicable
5. Exact next blocker
