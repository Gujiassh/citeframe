# M42-I1 targeted repair evidence

Status: repaired candidate ready for the original independent reviewer; no self-acceptance. The review artifact is unchanged by this lane.

## Changed composition

Only `routers/memories.py`, `services/memory_management.py`, and dedicated `test_memory_management.py` are changed product/test files in this repair. Error rendering is a single route-local function. The service receives a renderer bound to the already-authenticated request identity. `_read` catches domain errors inside its fresh authorization transaction and constructs the final JSONResponse bytes there. Conflict/terminal metadata uses that same guarded read/render boundary after the original command rollback. The transaction exits before returning the Response for ASGI transmission.

No command/dependency/global handler/shared query/schema/core changes. Auth/validation priority, fixed messages, requestId rules, owner404 behavior, fresh sessions, mutation commit and unknown-outcome recovery are preserved. CI workflow remains at independently accepted SHA-256 `de69b0aaff39849af7f0cab8fe2302685dcac5fd35bd1de3063b1205b523422c`.

## Reverse-race oracle

Ten new real-PG cases cover version_conflict, terminal_memory, erased current, erased history, and erased exact source, each in two orderings:

1. At final target-error `JSONResponse.render`, the actual connection observed executing membership FOR UPDATE remains open/in-transaction. A separate transaction attempts actual membership DELETE with100ms lock timeout and receives PostgreSQL55P03. The original renderer finishes under the guard. At `Response.__call__`, before ASGI send, the guard is released and actual membership deletion commits; response.body equals the already-rendered bytes. The next fresh request returns404 without version metadata.
2. Membership deletion commits after the authentic dependency's member read and before the command/projection guarded read. The target409/410 renderer is never reached. The request returns nondisclosing404 without currentVersion; requestId follows the original rule.

These are real database races using TestClient transport; they are distinct from the live socket evidence. Existing fresh-conflict lookup revocation/role tests remain in the suite.

Dedicated result: **56 passed, zero skipped**,23.50s (`pytest-i1.txt`), including47 PG-backed tests and9 pure DTO tests. Combined result: **1748 passed, zero skipped**,64.00s (`pytest.txt`). The existing standalone `live_http.py` was rerun against the repaired application: **76 live socket HTTP checks passed** with unchanged member/auth dependencies and no mock interface evidence. This includes full lifecycle, admission, conflict/errors, recovery/replay/CAS and source/history. The new timing instrumentation is confined to the dedicated PG tests; it is not claimed as76 live race cases.

## Full API failures and pristine-parent hash inspection

The previous full local API result remains **1011 passed,29 failed,9 skipped**. It is not green. No full-suite passing claim is made by this repair.

`i1_parent_hash_audit.py` reads immutable parent objects for `7d47607778a9212e9f3cb076442cd7c497c1f8ca`, verifies object SHA1 identities, and compares exact parent bytes with current raw/CRLF-normalized bytes. It invokes no Git command or API and writes only lane evidence. `i1-parent-hash-audit.json` records all SHA-256 values.

- The22 M402 failures stop on source/artifact provenance hashes. Pristine-parent frozen worker artifact hashes to the approved `10f59a...`; current CRLF checkout hashes to `4eec7d...`. The pristine real-model artifact matches approved `55d0a5...`; current CRLF checkout does not. Normalizing those checkout bytes reconstructs the pristine bytes exactly. The current worker test source is also semantically identical to the parent after newline normalization; its historical frozen hash differs intentionally and is supported by the existing exact-artifact provenance contract. Checkout artifact byte drift prevents that historical exception.
- The2 R100 failures stop on the failure taxonomy: pristine bytes match expected `b99972...`, while current CRLF checkout hashes to `6d340e...`. Normalizing current bytes reconstructs the parent exactly. The case document and test/service semantics are unchanged from the parent.
- `main.py` differs from the pristine parent by exactly the two router registration lines after newline normalization. The specific failing M402/R100 hash comparisons bind the files listed above, not main.py. These observed failures are checkout-byte drift present independently of the management registration; they are not established pristine-parent failures. No pristine full-suite execution is claimed.
- The3 A2a Windows subprocess/access failures and2 Research SSE missing-tsx failures remain separately recorded in `ci-followup.md`. They are not hash failures and were not repaired here.

Minimal additional owner grant for the demonstrated hash failures: evaluation/artifact owner permission to restore exact pristine bytes of `docs/evals/artifacts/m402-v1/worker-execution.json`, `docs/evals/artifacts/m402-v1/real-model-execution.json`, and `docs/evals/multimodal-failures-v1.json`, then rerun their tests. A durable Windows checkout policy would require a separate narrowly scoped `.gitattributes` grant for byte-pinned artifacts. No historical expected/release hashes, provenance approvals, tests or those three files were changed. Broader failures may become visible after those first checks pass; no blanket fix claim is made.

## Handoff

Exact before/after product hashes and current evidence are in `i1-candidate.json` and refreshed `candidate.json`. Original independent M42-I1 re-review is required. CI wiring acceptance remains separate from hosted CI/merge/release. No Git calls, paid models, private memory, shared workbench or other-worktree writes. Durable write-back is these lane-owned artifacts only.

Cleanup: live HTTP subprocess exited. Fast shutdown of the exact lane-owned disposable PostgreSQL cluster timed out; immediate stop succeeded. Port56542 returned no response and postmaster.pid was absent. Python compilation and direct trailing-whitespace checks passed; no Git command was used for static checks.
