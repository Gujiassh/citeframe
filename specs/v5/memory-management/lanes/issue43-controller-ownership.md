# Issue43 controller ownership decision

Fixed base2e92876, provider20717ed integrated ascae6379. PR48/49 remain unmerged dependencies; this branch does not claim merged-main status.

The requested NEW compaction DTO/service/model/migration/test files are exclusively Issue43-owned. Controller also grants scoped edits in this isolated branch to `citeframe_persistence/models/memory.py` (source/use extension only), `research_execution.py` (two native Attempt context columns only), and `models/__init__.py` (new model registration). #42 ongoing rework is deployment/migration regression tests only; its product schema is accepted and unchanged. No product overlap with #40 routes/deps.

This is file-ownership authorization, not independent schema approval. Exact delta in issue43-compaction.md still requires assigned reviewer approval before those schema edits. Preserve P1a tables/erasure/confirmation semantics, native raw-record and evidence meanings. Any change to existing contracts memory.py, old migration, public API, shared CI/locks or other tests needs a named narrow handoff first. Future additive-schema boundary tests may be requested once exact schema is approved; do not relax frozen original assertions preemptively.

Reviewer should directly validate source authorization for entire output audience, source deletion/member revocation and complete immutable source/version groups, as well as atomic snapshot/coverage/live-pointer adoption. No private memory calls in shared path. No new audience columns on native chat/research. Every-dispatch runtime wiring and realUI are later dependencies and must remain explicit.

## Selected mutation fence: Option A

Controller selects row-local noncycling revision stamps plus the existing nondeferrable thread FK/parent-row fence (lane contract section4 OptionA), subject to independent exact-delta review and actual PostgreSQL locking/ABA/phantom proof. OptionB global relation locking is not authorized as fallback. CHECK(false)/test-only-DDL activation and credential-retirement architecture are rejected and removed.

Grant two additional narrowly scoped files in this worktree: models/chat_thread.py and models/chat_message.py for the compaction_revision metadata field only, with its new successor migration/row-local assignment triggers and dedicated tests. No native audience/publicDTO/raw-body/output-permission change. Native mapped-field comparison must be explicit and frozen by tests. No system xmin/timestamp revision and no cross-row mutation trigger.

Independent review must first validate actual FK lock semantics, all explicit/implicit lock acquisition order and NOWAIT rollback, bounded complete metadata manifest with no silently omitted rows, same-ID recreation/ABA and native FK cascade behavior. Row caps/transaction timeouts must be explicit operational policy, measured on representative long-thread fixtures; report any supported long-history limit accurately rather than treating an arbitrary test cap as successful general compaction. Summary bodies remain current-branch-only although the concurrency manifest fences the entire thread.

Storage schema authoring remains gated on exact independent APPROVE. Already authorized pure policy/whole-unit algorithms and tests continue now. No router/services/script transfer is needed under selectedA; if realPG proof disproves its safety, stop affected adoption work and surface the failed oracle without silently switchingB. Keep one real checkpoint/coverage/live-pointer transaction.
