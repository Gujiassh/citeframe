# Issue41 controller brief

Authority: effective spec v4, including external proposal v2 section12 and final A1 choice2. Issues42–46 remain required; partial foundation PRs do not close their parent issues.

## Current product boundary

Owner-private memory supports storage and user management. Shared chat and Research exclude private content, including the requester’s own records, across prompts, tools, history/source reads, planning, summaries/checkpoints, streaming and derived output. No private thread/run mode, native audience column, permission expansion or automatic sharing is included. A1 is resolved.

Automatic compaction checks before every main-model dispatch, including tool continuation, role changes and recovery. Checkpoint, coverage and live pointer commit in one CAS transaction. Same-run continuation preserves budgets, cancellation, completed side effects and publication state. Research evidence scope remains frozen; uncertain research facts remain task memory. Ambiguous inferred long-term candidates are excluded.

## Active delivery lanes

- #42 P1a: isolated `work/issue42-memory-persistence`, starting `8812fda4d69b7f0e654e749c357fa05b5e8da72f`. Developer `agt_3a16f73b` (astra medium), reviewer `agt_a74ed9c2` (astra high). Six additive instruction-only tables, fail-closed owner management, CAS/idempotency, erasure and migration guards. Independent bounded ACCEPT with 57 real-PG/boundary tests; hosted CI/final-image gates outstanding. No mounted API/UI or compaction activation.
- #44 provider: isolated `work/issue44-memory-provider`, same fixed start. Developer `agt_1a6e6798` (astra medium), reviewer `agt_1b9ce005` (astra high). Neutral adapters/counting/protocol only. Original developer reworking redirect denial and incomplete Responses status; independent re-review required.
- Sole shared DTO/ports/package/dependency owner is #42; #44 owns adapters and dedicated tests. Shared contract commits are recorded in delivery.md.

## Dependencies and remaining acceptance

Neutral provider + atomic checkpoint storage enable #43 compaction. #44 chat loop and #45 Research consume that gate; #46 supplies management UI and visible continuation/recovery acceptance. Checkpoint/coverage/live-pointer transaction must not be split at PR boundaries. #40 gates dependent route integration only; canonical #40 and historic worktrees remain untouched.

PR47 is still open with no merged baseline handoff. Its external pinned-image failure is tracked by #40. Isolated foundation coding proceeds independently. Each PR requires its own developer, independent review, original-developer rework, hosted gates and controller acceptance before merge.

Engineering/runtime, semantic-quality and real visible UI evidence are separate. No paid model evaluation is authorized. Full #41 remains open until all scoped PRs merge and the required end-to-end behavior is verified.
