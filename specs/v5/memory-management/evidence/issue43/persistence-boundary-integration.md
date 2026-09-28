# Persistence boundary integration

Scope: `apps/api/tests/test_persistence_boundary.py` only, plus this new report. Entry/final observed HEAD0315a735bc6206b87a2e9e49d3ecd72a56f9205b. No product, migration, workflow, shared snapshot, prior fixture or prior report edits; no Git/network/model/private/global/canonical writes.

## Exact compatibility change

The neutral-only additions are explicitly partitioned into the original six memory models and four approved compaction models: ChatMemoryExecution/chat_memory_executions, MemoryCall/memory_calls, TaskMemorySnapshot/task_memory_snapshots and TaskMemoryCoverage/task_memory_coverage. Export set/order, object identity, module/table mapping and single metadata identity remain strict. The isolated interpreter still denies API/Worker import paths and now expects precisely95 tables with10 neutral additions, leaving85 native tables.

The original native oracle remains byte-identical: snapshot SHA-256 `100C42F7BDCDB3E816FF780E25260EBEA66E889917293E2154CD9FF12585B55E`. Existing autonomy/adaptive/conflict/model-settings delta artifacts and their validation remain unchanged. The full native projection still compares85 PostgreSQL table definitions and97 indexes exactly.

Projection removes only independently hardcoded, approved column declarations, requiring exactly one occurrence of each before removal:
- chat_messages.compaction_revision BIGINT DEFAULT1 NOT NULL with ck_chatmessage_compaction_revision >0;
- chat_threads.compaction_revision BIGINT DEFAULT1 NOT NULL with ck_chatthread_compaction_revision >0;
- research_step_attempts.memory_context_version BIGINT DEFAULT0 NOT NULL with ck_research_attempt_memory_version >=0;
- research_step_attempts.memory_checkpoint_id nullable VARCHAR(36).

Everything else stays in the actual DDL and must match the original native oracle plus existing approved deltas. Missing/duplicate/wrong-type/wrong-default/wrong-nullability declarations fail projection. An unexpected extra native field survives projection and fails exact baseline equality. Six dedicated mutation oracles exercise these cases without editing models.

ResearchAttempt's complete use_alter FK set is pinned to the historical checkpoint_artifact FK and new memory_checkpoint FK. Both have exact names, source/target columns, default update/delete/deferrability options and compiled ALTER TABLE SQL. An unexpected additional use_alter FK fails. No product/schema mismatch outside the approved changes was found.

## Actual developer verification

- Original RED: **2 failed,5deselected in0.18s**. Neutral exports had four approved additions beyond the old six-only expectation; table count was95 versus91.
- Initial correction:19passed/1failed1.97s. New FK-set test initially omitted the existing checkpoint_artifact use_alter FK. Corrected the explicit expected set to retain both old and new relationships; no product change.
- Final complete persistence boundary plus neighboring research persistence boundary: **20 passed in1.74s**, zero skips, one existing Starlette/httpx deprecation warning. Includes isolated import subprocess and six negative projection cases.

Executor: `/root/core_implementation`, developer-side only. No PostgreSQL is needed for these compiled-DDL/import/dependency oracles; no PostgreSQL service was started for this slice. Real migrated-schema evidence remains separately scoped in approved core/fixture reports. No hosted CI or whole-Issue acceptance is implied.

```text
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=<all packages/*/src;apps/api/src;apps/worker/src>
D:/Code/citeframe/apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_persistence_boundary.py apps/api/tests/test_research_persistence_boundary.py -q --tb=short -p no:cacheprovider --basetemp=.local-runtime/boundary-final
```

## Frozen identities

- Changed boundary test: `5FC30A4EA01F30429BE583AEB6C3D1835AE8B3F7E2B937D47AD66BD8EA9E5935`.
- Prior instruction fixture retained: `E6A33A6461785F3AFB371B647C0DCF28776DEA46310A76C7FB06C975ED5D2AED`.
- Prior fixture report retained: `35BF79917315FCDA0766E281BF70651B0814E0BF208D5A4A9F42D1D65B878C49`.
- Approved45 manifest:zero mismatches.
- Scoped diff-check clean. Prior two head-test files remain unchanged.

Developer-root separately executed the complete boundary, research boundary, research migration and instruction neutral-import selections: **35 passed in2.83s**, exit0, one existing Starlette warning. No PostgreSQL, network or uv execution. The boundary test was unchanged during this run. This is developer-root verification; original independent review remains required. This report supersedes the earlier boundary2-failure blocker only for this tested candidate and scope; historical failure reports remain intact.
