# Issue44 chat-loop — F44-L4 dedicated CI collection handoff

Date: 2026-09-28. Original reviewer accepted the scoped contract/helper and closed F44-L1/L2/L3. This handoff addresses only F44-L4; original-review CI recheck and hosted execution remain pending.

## Exact change

`.github/workflows/memory-provider.yml`: added one explicit pytest argument:

```python
"packages/memory-service/tests/test_chat_loop_turns.py",
```

No new job, directory-wide collection, PostgreSQL selection or shared ci.yml change. Byte comparison removed precisely this new line and reproduced the prior accepted workflow SHA-256 `0147fb741db6ed737942a258f189b0d561cec77bd1b688ffa247d82a86fa5412`. Every prior workflow byte, including frozen API uv environment, local-contract assertion, application-import/network denial, no-conftest/plugin/cache settings and skip/deselection/zero/xfail guards, is preserved.

Revised workflow SHA-256: `bbef4aed401e013e1e09a0206d2bd8fc01635de1b54b5c7fc3f52974873ec091`.

## Verification

Extracted the embedded Python body directly from the revised workflow, parsed its AST and verified exactly the four explicit test paths. Executed that body unchanged in a fresh Python subprocess using the read-only cached dependency environment already recorded in `lanes/issue44-chat-loop.md` §13. PYTHONDONTWRITEBYTECODE=1, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 and `-B` were active. No dependency install or frozen-lock update occurred.

Result: **181 passed in 0.66s** (64 helper + 86 native provider + 14 counting + 17 wire). The exact workflow body retained all denial and collection guards. This is local execution of the hosted runner body; the Ubuntu/frozen-uv Actions job itself was not run here.

Missing-test negative control: in memory only, substituted the helper argument with the verified-nonexistent `packages/memory-service/tests/test_chat_loop_turns_ABSENT_PROBE.py`, then executed the otherwise identical body in a fresh subprocess. Result: **exit 4**, `ERROR: file or directory not found`, no tests ran. The explicit-path selection fails rather than silently reverting to the old117. No actual test file was renamed/deleted and no workflow negative-control edit was written.

Frozen product/helper SHA-256 verified unchanged:

| File | SHA-256 |
|---|---|
| chat_loop/turns.py | `ebfe72ac945a854866494db0ac52b1f09eed23bae84815463260a9a7639a664b` |
| chat_loop/__init__.py | `10a788b1aeb20eef96f03330329d973e4a4166a814733e251b8db50aa62b3e37` |
| tests/test_chat_loop_turns.py | `c7581f8940686f44e99b7e0695bf4b0e4a77f2fe8e02cbfd9dca03a830bd38bc` |

The accepted lane contract and original reviewer artifact were not edited. Only the workflow's one test-list entry and this scope/evidence log were written. No Git calls, live/paid model calls, application or PostgreSQL tests, private memory reads, provider edits or production-loop activation. Controller retains commit/push/PR/hosted-evidence ownership. Return this candidate to the original reviewer; no independent finding closure is asserted here.
