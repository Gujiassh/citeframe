# Issue 27 publication adoption repair

## Scope and invariants

The initial prerequisite commit 131ab0ce contains exactly the approved 41 paths. The subsequent repair is limited to publication adoption and its regression tests. Canonical dirty work and architecture PR #26 remain untouched.

- Lock order for adoption: Run → Step → Attempt → publication intent → creator membership. The membership row remains locked through commit. A deletion committed before the membership lock is observed must prevent publication; a concurrent deletion after this lock waits for adoption. Recheck the publication fence and DB wall clock after the membership lock wait.
- Missing membership requests cancellation and enters existing compensation. It cannot create a user final Artifact or run_completed event. Reconciliation uses the same adoption gate; cleanup needs no current creator membership.
- A successful evidence search may originate from a terminated earlier attempt of the same Step and immutable input. Workspace, run, execution snapshot, owner Step, successful tool status, tool version/name and source attempt must remain valid. No request hash checks are disabled.

## Evidence

`test_research_publication_adoption.py`: 10 fixture tests passed. Publisher and reconciler each cover revocation before/after PUT. Retry coverage uses production failure, claim, search/load replay and completion APIs before final publication, with a seeded downstream claim/verification graph. Foreign Step/snapshot, failed tools, changed attempt input and nonterminal origin attempts fail closed. Storage is an in-memory test double; no paid provider is invoked.

The fixed candidate's initial API CI failed in the historical A2 differential harness: its Python clock is frozen at 2026-08-24 while the new saga samples SQL wall time. Do not relax production lease validation to make that harness pass. Adaptation and negative controls still require validation.

## Pending acceptance

Independent fixed-HEAD rereview, PostgreSQL multi-connection revocation/adoption ordering, object-store/process restart/concurrent-idempotency evidence and visible real-service UI remain pending. Passing fixture tests does not close these runtime gates. Do not merge.
