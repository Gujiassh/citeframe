# Issue44 geometry dedicated CI — frozen candidate

Date:2026-09-29. Scope: NEW `.github/workflows/memory-image-geometry.yml`, this CI evidence, and execution-attribution correction in existing geometry evidence. Product/tests are independently accepted under review `FFBEDACA637148142EA518154ABA6AC31BAE77B560FD705CBB9C1F35ABA4BDF9` and remain byte-frozen. No shared CI, dependency/lock, native/resolver/router, ABI, loader/launcher/build or activation edit.

## Candidate SHA-256

| File | SHA-256 |
|---|---|
| .github/workflows/memory-image-geometry.yml | `82600A9CCA24A89F1FBC70460E9F0F9CBE23A4E1D370FD9AE86B01F16F4C5D26` |
| frozen apps/api/src/ai_pdf_api/modalities/native_image_geometry.py | `62B89093C67B88B16CB926C61A4DC1FC3725341332350B32BD88FFCA4532368C` |
| frozen apps/api/tests/test_native_image_geometry.py | `538AB2C3575E04EDC66BBC2DBC43A573DE05BCB9B07B3598CCADB902FA3B25F2` |
| corrected evidence/issue44-native-image-geometry.md | `5847DE5FB1282D5F4897E714343DE7ADF20D27F3DFB0B5317C7DC8243979C872` |

Evidence path relative to specs/v5/memory-management.

## Workflow behavior

Ubuntu independent native-image-geometry job,10-minute timeout, contents:read only. checkout@v4, setup-python@v5 Python3.12, setup-uv@v6; UV_PYTHON=3.12 and actual `sys.version_info[:2]` assertion. Existing `uv sync --project apps/api --frozen --extra dev` environment and `uv run --project apps/api --frozen --no-sync python` runner; no dependency change or unpinned install step. PYTHONDONTWRITEBYTECODE=1 and PYTEST_DISABLE_PLUGIN_AUTOLOAD=1.

Both pull_request and main-push paths are restricted to the new geometry source/test, actual two old-oracle source files, apps/api/pyproject.toml + uv.lock, four existing local-source package pyproject.toml files needed by frozen sync, and this workflow. Unrelated docs/feature code do not trigger this job. No schedule/manual model execution, secrets or provider calls. Existing neutral/profile/builder/shared jobs are unchanged.

Runner explicitly selects only apps/api/tests/test_native_image_geometry.py with --noconftest --strict-markers -p no:cacheprovider -o pythonpath= -o xfail_strict=true -q. It requires collected==119 and successful call-phase reports==119; collection/runtime skip, wasxfail (including xpass), deselection, missing file and collect-only cannot pass. Normal pytest exit status still governs setup/teardown/test failure. Actual module __file__ must match this workspace's geometry file. MetaPathFinder denies all ai_pdf_api/ai_pdf_worker/citeframe_contracts; socket/socketpair/create_connection and five DNS entrypoints deny external IO. The tests load the real file through file-location import, retaining the previously documented package-initializer limitation.

Linux runner will execute real pinned Pillow/PyMuPDF old-function parity through the unchanged tests, including exact CRLF/LF source hash allowlists. Merely adding this workflow does not establish Linux parity or hosted success.

## Actual local verification and actor attribution

- **Implementation agent:** final actual workflow heredoc extracted unchanged, Windows cached dependencies,119 passed in2.19s, exit0. Its in-memory negative runner controls missing/collect-only/deselect/skip/xfail/xpass/wrong module/wrong Python/API/Worker/contracts/all8 socket-DNS entrypoints all exited1.
- **Developer-root:** independently of the implementation agent execution, ran the same final heredoc unchanged using existing Windows cached dependencies: **119 passed in2.19s, exit0**. Missing-path control exited1; collect-only collected119 but exited1 because no call-phase results. This is still developer evidence, not an independent controller/reviewer execution.
- **Syntax fallback, implementation agent:** PyYAML BaseLoader structure, Python AST and Bash -n on the actual run scalar passed. These are not actionlint.
- **Actionlint: BLOCKED / NOT RUN.** No usable local executable was found on PATH or checked existing tool locations. No download/install, uv command/retry or permission bypass was attempted. Controller must provide an authorized existing actionlint binary/execution or run it against this exact workflow hash before this requested gate is marked passed.
- **Hosted Linux/frozen uv installation: NOT RUN locally.** Local execution reuses existing cached dependencies, not uv. No paid/live model, actual provider connection, Linux launcher or kernel resource test.

Extraction used `textwrap.dedent(workflow_text.split("python - <<'PY'\n",1)[1].rsplit('          PY',1)[0])`, passed verbatim to `[sys.executable,'-B','-c',body]`. Cache interpreter/dependency IDs are recorded in the preceding geometry evidence. Negative controls alter only in-memory runner copies, never product/tests or workflow.

The preceding evidence's119/2.41s run, path/import/network/report guards and per-test collection are now explicitly attributed to **developer-root**. Controller's later APIvenv119/1.45s is separately recorded as controller-reported independent execution, without borrowing developer-root guard claims. Review119/1.50s and extra96PDF/512Decimal/14 rejection probes remain original reviewer evidence. No result or actor is combined to imply stronger execution than observed.

## Handoff

Frozen candidate is ready for the original reviewer's targeted CI inspection, with actionlint explicitly outstanding and hosted Linux execution pending controller push. Product acceptance remains intact. No commit/push/Git calls, no native activation, no change to resource/launcher/ABI permissions. Write-back is these owned evidence files only; no private memory or external workbench write.
