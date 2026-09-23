# Issue31 delivery ledger

- Issue: https://github.com/Gujiassh/citeframe/issues/31
- Parent PR: #26, branch work/research-layout-20260923.
- Exact base: c2639a071dbdc9deb18c46098637c19cfaca88a7.
- Repair branch: work/evaluation-scenario-drivers-20260924 in the same isolated delivery worktree.
- Scope: evaluation driver/evidence/oracles, executed negative controls, bounded Docker recipe, tests and SSoT. No product scheduling changes.

## Proven cause and preserved evidence

Independent review found the original main driver calls one synchronous processor
while demanding >=2 active provider requests. It also found reclaim cleanup ran
after just one global process call, which legitimately completed another step
before the original abandoned step could be consumed again. Old/new scenario
functions were AST-equal across#26. Original runs35892756138 and35894964943,
including their red scenario aggregate, are preserved and not waived.

#26 c2639a's default-registry/backup/restore/normal-Worker/new-HTTP-artifact gate
was independently closed by Hubble (PR comment5799615321). That evidence is not
claimed as validation of this new driver. This PR is stacked and must be reviewed
and merged only through the controller's normal process.

## Implementation and evidence plan

The canonical [SSoT](../../../docs/ssot/research-acceptance.md) specifies consumers,
raw overlap/identity oracles, 30-second same-step recovery, C4 limits, and mutation
controls. Main runtime facts and original/recovered attempt facts are embedded
with their checks for independent replay. A new derived unit fixture selects the
main-run rows from35894964943/before.out and includes source provenance; the
original archive is unchanged.

The Docker workflow preserves the original50af scenario run on the same runner,
then evaluates the new source and records all raw JSON/provider/attempt evidence.
A third fresh project forces serial main consumption and requires observed
concurrency rejection without reclassifying its scenario result as passing.
No skip/continue-on-error is used. Actual new-HEAD runtime and independent review
remain pending until their evidence is produced.

## Local checks

- Focused CLI/acceptance/driver tests: 18 passed before runtime execution.
- Full evaluation and architecture boundary suite: 125 passed, 1 Windows symlink skip.
- Seven Docker harness tests passed; full deployment and serial negative controls pending exact committed SHA.
- New product defects, if proven by correct orchestration, return to Franklin with narrow ownership rather than changing this lane's business code.

