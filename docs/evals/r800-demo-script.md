# R800 Five-Minute Demo Script

## Demo Boundary

This demo presents the V4 Research engineering workflow. The canonical evidence is
[`artifacts/r800-v1/deployment-20260728-v4/`](artifacts/r800-v1/deployment-20260728-v4/).
The provider is deterministic, so do not describe the run as proof of model quality
or user value.

## Pre-Demo

Open these files before the timer starts:

- `report.json`
- `scenarios.json`
- `verification.json`
- `provider-timeline.json`
- `before.json`

For a live rerun, use the command in
[`../architecture/research-workflow-runtime.md`](../architecture/research-workflow-runtime.md).
Build plus backup/restore takes longer than five minutes; the timed demo uses the
retained canonical evidence.

## 0:00-0:45 - Product Flow

Show the explicit Quick/Research selector and the Research run panel. Explain only
the user-visible sequence:

1. the creator starts Research with a frozen Asset scope;
2. the plan is shown before execution and requires approval;
3. bounded Researcher branches execute in parallel;
4. unsupported claims are withheld;
5. conflicts pause for a creator decision;
6. the final report links back to immutable Evidence.

Quick Chat remains the default and uses its existing request, SSE, Citation, and
save contracts.

## 0:45-1:45 - Persistent Truth

Show `report.json` and `scenarios.json`:

```bash
jq '{engineeringGate,releaseGatePassed,modelQualityGate,userValueGate}' \
  docs/evals/artifacts/r800-v1/deployment-20260728-v4/report.json
jq '.checks | with_entries(.value = {status:.value.status,evidence:.value.evidence})' \
  docs/evals/artifacts/r800-v1/deployment-20260728-v4/scenarios.json
```

Point out `mainCompleted=pass`, `parallelFanout.maxActive=2`, one submitted conflict
decision, three unsupported claims with zero final links, and exactly one final
Artifact.

## 1:45-2:35 - Failure And Recovery

Use the same scenario evidence to show:

- one scripted provider 503 produced one failed attempt and one retry;
- an expired lease became abandoned and attempt 2 completed;
- SSE replay resumed after the recorded cursor without gaps;
- cancellation committed without a final Artifact;
- creator membership removal stopped work and ended the Run as cancelled.

Emphasize that these are persisted state transitions, not UI-only simulations.

## 2:35-3:25 - Concurrency And Budget Safety

Show the provider timeline and explain the lock invariant:

```text
Attempt -> Step -> Run -> Provider/Tool call -> Budget ledger
```

The timeline proves real overlap while the ledger and Run state remain consistent.
Already-sent provider usage is reconciled after cancellation; a reserved call cannot
be sent after cancellation.

## 3:25-4:15 - Backup And Restore

Show `verification.json`:

```bash
jq .verification \
  docs/evals/artifacts/r800-v1/deployment-20260728-v4/verification.json
```

The before/after semantic SHA is
`a60fa5eaf70a86e47d3de1b17a7c49561a2c6cfbc369554fc1d94a9567bab6a8`, with no
mismatches. PostgreSQL rows and MinIO object bytes/hashes were restored into an
empty deployment.

## 4:15-5:00 - Honest Close

Show the cleanup and evidence gates:

```bash
jq '{cleanup,modelQualityGate,userValueGate}' \
  docs/evals/artifacts/r800-v1/deployment-20260728-v4/report.json
```

Close with three statements:

1. The deterministic engineering release gate passed and left no container, volume,
   network, or secret-file residue.
2. Real-model paired quality remains `not_evaluable`; R803 is still open.
3. User value remains `not_evaluable` until M404 has qualified target-user evidence,
   so the product remains `internal_preview`.
