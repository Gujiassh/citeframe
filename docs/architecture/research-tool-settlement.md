# Research tool settlement

Research tool settlement finishes an existing native tool call and updates its existing attempt and budget ledger. The persistence module exposes the existing public `complete_tool_call` operation and a private `_complete_tool_call_in_transaction` seam for a future caller-owned transaction. The private seam has no current production caller and does not activate Research memory, add a tool kind, change stored fields or create a new API contract.

## ID-based locked chain

Both entry paths accept a tool-call ID and validate terminal status before locating the call. They reacquire the native aggregate in the existing lock order:

```text
ResearchRun -> ResearchStep -> ResearchStepAttempt -> ResearchToolCall -> ResearchBudgetLedger
```

The initial locator runs without autoflush and supplies IDs for locking and validation. Locked queries refresh the Run/Step/Attempt and ToolCall/BudgetLedger rows. The chain validates run, step, attempt, execution-snapshot and workspace relationships, ledger ownership and snapshot existence. It rejects missing or foreign chains and calls already outside `requested`/`running` before invoking the completion callback. Supplying cached ORM rows cannot replace the ID-based entry's locks and checks.

The execution snapshot retains the existing `Session.get` lookup behavior. This seam adds no fresh snapshot authorization or lease-admission guarantee. It uses the settlement chain rather than the separate active-attempt admission path. Membership, lease validity, dispatch permission, source authorization and native lifecycle fences remain obligations of the surrounding validated caller.

## Transaction ownership and errors

| Condition | Existing public operation | Private caller-transaction seam |
|---|---|---|
| Invalid status, invalid chain, already terminal, or failure while acquiring the chain | Propagates before the public rollback catch | Propagates to the transaction owner |
| Completion callback, field mutation or final flush raises an ordinary `Exception` | Calls `Session.rollback()` and re-raises | Propagates without committing or rolling back |
| Successful settlement | Flushes; does not commit | Flushes; caller chooses commit or rollback |
| `BaseException` control flow | Retains the existing propagation policy | Propagates to the caller |

The private entry creates no Session or nested transaction and does not catch caller failures. Its callback must also leave commit/rollback ownership with the caller. The seam still flushes and can issue SQL or fail. The caller must handle transaction recovery, including database errors that leave the Session inactive. Existing autoflush points remain in effect outside the public catch.

Lower-level mutation helpers are internal implementation details. Future composition must enter through the validated ID-based seam and keep settlement in the same caller-owned transaction as the operation whose result it records. Private Python naming is a trusted-code convention and does not create an authorization boundary.

## Result and usage accounting

The completion callback executes before settlement fields change and returns the existing result count. Settlement then records terminal status, result count, error code/message and finished time in the original order. Accepted terminal statuses remain `succeeded`, `failed`, `cancelled` and `abandoned`.

Each settlement releases one reserved tool slot, increments actual tool calls, ledger state version and attempt tool-call count once, and sets ledger update time to the call's finished time. The existing final flush retains database constraints and row locks until the transaction owner finishes. Another settlement must reacquire the chain and reject the now-terminal call before executing its callback again.

There is no second usage ledger, new budget allowance, replay receipt or change to provider-token accounting. Existing execution-snapshot bindings and native budget/lifecycle rules remain authoritative. Settlement alone does not authorize an additional call, new memory callback, source read or saved-result adoption.

## Integration boundary

The dedicated tests preserve a byte-pinned pre-extraction public oracle, signature and transaction observations. They compare native statuses and payloads, lock/flush order, precondition precedence, public rollback behavior, private caller-controlled commit/rollback, cached-row refresh and no-double settlement. PostgreSQL tests use actual native ORM constraints; this is separate from migration upgrade/rollback acceptance.

The dedicated workflow also runs the existing API budget-recovery/persistence-boundary and Worker memory-context checks with checkout-local import and complete-execution guards. Exact integrated-head PostgreSQL and hosted checks remain required after dependency integration. A real native memory caller, validated snapshot/source/lifecycle composition, dispatch/recovery and end-to-end Research behavior require their own acceptance. This settlement seam does not complete parent issue45.

See [tools.py](../../packages/research-persistence/src/citeframe_research_persistence/tools.py) and [settlement tests](../../packages/research-persistence/tests/test_memory_tool_settlement.py).
