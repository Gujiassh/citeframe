# V5-E Verification Matrix

## Evidence classes

| Class | May set | Source |
|---|---|---|
| Engineering | `engineeringGate` | V5-D suites / compose |
| Live restore | restore identity | D-G6 mixed compose |
| Model quality | `realModelQualityPassed` | formal R803 campaign only |
| User value | `userValuePassed` | M404 only |

## Gates

| Gate | Scope | Pass condition |
|---|---|---|
| E-G0 | package freeze | new campaign dir empty; plan/threshold/package SHAs recorded; history paths untouched |
| E-G1 | formal campaign execution | 5 rounds × suite complete or honest fail with immutable artifact |
| E-G2 | quality judgment | absolute thresholds in `r803-release-threshold-v1` (or successor) evaluated; no winner heuristic |
| E-G3 | M404 protocol | written protocol approved before any user session |
| E-G4 | M404 execution | qualified users complete tasks; adoption metrics recorded |
| E-G5 | release review | independent Critical review of all four evidence classes |

## Mandatory commands (campaign)

Document exact commands in the campaign `campaign-plan.json`. Typical shape:

```bash
# non-formal dry checks only until owner authorizes spend
uv run --project apps/worker python -m pytest apps/worker/tests/test_r803_campaign_v5.py -q
# formal campaign (requires explicit authorization + secrets)
# uv run --project apps/worker python apps/worker/scripts/evaluate_r803_campaign.py ...
```

## Forbidden claims

- Interpreting D-G7 green as model quality
- Resuming `r803-campaign-20260730-v1`
- Setting `userValuePassed` from internal dogfood alone without M404 protocol
