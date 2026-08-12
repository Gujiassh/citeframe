# D-G6 Empty-target Mixed Compose Report

Date: 2026-08-12  
Source SHA: `07b8833907034441874fb59f157609962ff04980`  
Script: `infra/scripts/run-v5d-mixed-compose-acceptance.sh`  
Artifact: `docs/evals/artifacts/v5d-mixed-compose-20260812-01/`

## Verdict

**pass** for mixed PDF+Image+Markdown empty-target Compose backup/restore.

| Check | Result |
|---|---|
| seed modalities | pdf + image + document |
| empty target after down | true |
| semanticSha256 before/after | `d8563074fd66eddbc70efcd7695cafcd41ef16b614ddad09b60ed2530fa9f3f3` (match) |
| restore verification | passed |
| browser before/after | exit 0 / exit 0 |
| cleanup zero residue | passed |
| deploymentGate | pass |
| releaseGatePassed | true |
| realModelQuality / userValue | false / false |

No business API/save contract change. Reuses `compose.v5b.yml` + shared backup/restore.
