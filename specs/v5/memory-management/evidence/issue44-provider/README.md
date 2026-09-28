# Issue44 provider evidence

Candidate HEAD: `a07b881529aded9dfcbead0634ec1eea15a7d36c`, the controller-integrated #42 required redirect-policy correction after scaffold `cfa4ab9a948f447e20964cd42e657f8830bb1615`, on fixed main baseline `8812fda4d69b7f0e654e749c357fa05b5e8da72f`.

Controller rerun: **117 passed in 0.47s**. F44-1's three actual-httpx redirect regressions now pass. F44-3 final message status has six negative and two positive cases; prior protocol tests remain green. F44-2 stays independently closed and unchanged by this rework. Final independent recheck of F44-1/F44-3 is pending; no shipping approval.

All transport fixtures and counter values are synthetic. Socket entry points were denied, API/Worker imports blocked, and the 13 source/test files plus the local shared contract were hash-stable throughout the run. AST parsing and trailing-whitespace checks passed all 14 files. No live model/network request.

## Reproduction command

From `D:/Code/citeframe-lanes/issue44-provider`:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$base='C:/Users/baiao/AppData/Local/uv/cache/archive-v0'
$cached=@('xIlLX82QEusHhXca','RHvkbWyG_J6xPpug','2ITaIXdneZF10lum','L-k_dNEQiegHAoRr','9WszWcRZL3SpM_A6','owHdhenMp3yGpVwQ','IXhh9yEdY9JaYctE','KCmD3SQamalmBs5q','YdsFZR1HrxsPKnB9','Zq2bI9VcljzvcYsS','_RYxQYdcVRNLZyX8','ZDAbANqgonyGTG3i','_9JbTHVRpvVtYE4F','FDG66F5kllj7cINU','K0LZfPUmyexRg91C','sBbxgXf9XB47bNJW')
$env:PYTHONPATH=(( $cached | ForEach-Object { "$base/$_" }) + @("$PWD/packages/memory-service/src","$PWD/packages/backend-contracts/src")) -join ';'
python -m pytest -p no:cacheprovider packages/memory-service/tests -v
```

The cache entries provide pytest 8.4.2 and its dependencies, plus httpx 0.28.1 and its dependencies read-only. They are test-runner dependencies only. With pytest and httpx installed normally, prepend the two local source directories to PYTHONPATH and use the same pytest command. Shared package/deployment dependency integration is owned by #42/controller.

`pytest.txt` captures the complete controller run, including `STABLE_CONTENT True`, `AST_AND_WHITESPACE 14 passed` and `APPLICATION_IMPORTS []`. `sha256.txt` pins the 10 adapter files, 3 test files and the shared contract. Earlier cross-worktree and failing pre-correction runs are superseded.

The recorded controller run used the same environment and pytest arguments through Python stdin with these additional guards: a meta-path finder rejects `ai_pdf_api`/`ai_pdf_worker`; `socket.socket.connect`, `connect_ex` and `socket.create_connection` raise `AssertionError`; SHA-256 maps of the listed files are compared before and after `pytest.main`; each file is AST-parsed and checked for trailing whitespace. These guards do not replace the three actual-httpx MockTransport regressions.

## Evidence limitations

- Shared message DTO is text-only; unsupported multimodal input rejects. No multimodal parity or image accounting claim.
- Injected exact-counter test proves plumbing, profile binding and payload coverage; it does not establish accuracy for a real tokenizer/provider. Character estimation is labeled estimated and requires deployment-specific calibration.
- App-blocked imports prove the neutral boundary; composition roots are not wired here.
- Shared-output private-source exclusion, live loop/compaction, journal recovery, database safety, Research evidence behavior and UI acceptance remain downstream integration gates.
- Assigned independent review is separate; a passing local suite does not establish its approval.
