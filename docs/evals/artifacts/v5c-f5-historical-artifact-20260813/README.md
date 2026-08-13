# F5 historical final-artifact residual closeout

Date: 2026-08-13  
Paid provider calls: **0**

## Oracle

Finished `final_report` bytes/hashes survive manual step retry/recovery requeue
when the execution snapshot carries legacy agent I/O registry versions.

## Evidence

```bash
uv run --project apps/api python -m pytest \
  apps/api/tests/test_research_router_recovery.py::test_f5_historical_final_artifact_bytes_survive_retry_and_recovery -q
```

Result: **1 passed**
