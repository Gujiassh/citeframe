# Issue 23 historical workflow and current default acceptance

This feature oracle is separate from the Issue 27 R2 delta manifest.

- A: the frozen baseline's real POST-create endpoint exports its database, workflow/prompt records, proposed revision, object bytes and deterministic fixture counters. The current candidate restores those exact historical columns/rows, installs current v3 alongside them without rewriting frozen release rows, and executes the historical v2 human plan/conflict decisions and final publication. No default registry is replaced.
- A-stored: restore a second baseline checkpoint after its real human approvals. Replay both original keys/bodies and require exact original HTTP response bytes plus unchanged persisted events, decisions and idempotency rows. Resume only the remaining synthesizer and publisher attempts; the only new model invocation is synthesizer. All final state, budget, evidence and report invariants remain compared with the complete historical execution.
- B: an independent process/database installs the current default v3 and uses the actual POST-create endpoint. The Worker automatically approves, researches, verifies, retains the conflict as unresolved, synthesizes and finally publishes. This path sends no manual approval or conflict-resolution requests, and uses no registry override. Its feature assertions are not R2 exceptions.

Each raw report includes frozen workflow ID/version/release, five prompt IDs/versions/hashes, execution snapshot hash, current default workflow/schema and terminal result. The runner records one common candidate SHA. Source snapshots and historical artifacts are not edited. SQL restore is a local SQLite fixture; PostgreSQL migration/recovery and real process/service UI remain separate acceptance gaps.

## F1 versioned public contract

Workflow v2 identity and event schema v2 are independent. Current new human decisions use decisionOrigin=human, actor non-null, policyId=null and event schema2. Their decision DTOs add decisionOrigin=human. The feature oracle checks only those explicitly named fields, the two empty new feature tables, and default human decision_origin storage column; all old fields, actor, hashes, permissions and payloads remain strict. These are not added to the R2 whitelist.

Existing schema1 events and existing idempotency response records must remain unchanged. New consumers parse real production serialization for historical schema1, restored-v2/new-schema2 and current policy schema2 events. Old idempotency responses must not acquire new fields during replay.

The actual restore probe found FastAPI's response-model defaults inserting decisionOrigin into old-key responses. The two decision POST replay branches now validate/serialize the persisted response with per-response exclude_unset, preserving the historical omission and original datetime wire encoding. New requests retain their normal response model. No stored response or event is rewritten; no global exclude_defaults setting is used. Old request-body hashes and authorization checks still run before replay.

## Pending

The new combined candidate requires fixed-SHA execution and Hubble review after the predecessor oracle counterexamples are repaired. No merge acceptance is claimed.
