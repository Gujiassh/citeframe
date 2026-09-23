# Issue33: publication storage deadline admission

## Scope and invariant

This repair is stacked on PR28 at `e8f71d8a0fbdd37cbca8b2701b87054d4c69c013`. It changes only publication child admission, its focused regressions and this contract. The frozen PR28/29 browser fixtures and PR30 feature branch are unchanged.

The supervisor computes one absolute monotonic deadline before spawning the storage child. Bootstrap time and watchdog startup consume that same budget. A child that observes `now >= deadline` must exit124 without entering its operation callback:

1. Check at child entry, before allocating/starting the watchdog.
2. Check again after watchdog startup, immediately before operation admission.

The independent watchdog continues to supervise admitted operations. The20s hard deadline,2s terminate grace,2s kill grace,30s orphan observation, parent-death monitoring, process cleanup, error sanitization and generation ownership contracts remain unchanged.

Previously, `watchdog.start()` could return before that thread checked the deadline, allowing an already-expired child to enter the callback. This is inherited R2 behavior, not a PR30 regression. A synchronous check prevents knowingly expired admission; it does not cancel an already-sent remote request or provide a hard real-time scheduling guarantee between instructions. No late remote S3 write is established by the local evidence. Historical Windows DuplicateHandle failures remain separately attributed.

## Verification

`apps/api/tests/test_storage_deadline_admission.py` exercises the production entrypoint:

- Already-expired and exactly-expired entry: no watchdog allocation or callback.
- Budget expires during watchdog startup: no callback.
- Valid budget: callback exactly once, existing watchdog cleanup.
- Callback failure: original exception and cleanup preserved.
- Two spawned child cases with the actual `os._exit` and watchdog: intentionally delayed watchdog scheduling, local pipe-only callback; already-expired/startup-expired callbacks remain unentered and exit124.

The spawned tests do not create a storage client, network request, database connection or object-store mutation. Their5s join is a test-process safety bound; no production or existing lifecycle threshold changes.

Observed local differential using Python3.12 and explicit source PYTHONPATH:

| Source | New admission tests | Existing storage lifecycle tests |
|---|---|---|
| Unmodified e8 parent |6failed /2passed, including both real-process callback-not-entered assertions RED | Unchanged |
| Candidate |8passed |24passed; combined32passed/7.53s |

The existing module covers parent hard timeout/reaping, child monotonic deadline, supervisor death, no delayed local side effect, multipart bound, payload limit and secret-safe errors. Its thresholds and source remain byte-for-byte unchanged.

Reproduce the candidate narrow suite from the repository root with its dependencies installed:

```sh
uv run --project apps/api pytest apps/api/tests/test_storage_deadline_admission.py apps/api/tests/test_storage_metrics.py -q
```

For a parent RED check, run the same new test file while pointing imports at the unmodified e8 source and verify `storage.__file__` before execution. Keep that parent checkout read-only.

Independent review and same-HEAD CI are separate gates. This narrow repair does not reclassify pending browser gates or establish additional external storage effects.
