# R803 Windows directory-fsync portability implementation

Date: 2026-09-01
Status: **ACCEPT — independent Critical audit complete (Critical=0, High=0, Medium=0, Low=0)**
Delivery: **not committed or pushed**

## Scope

This slice makes the existing R803 immutable-evidence writer executable on native
Windows without weakening its file durability or immutability contracts. It does
not change campaign schemas, scoring, thresholds, provider behavior, evidence
content, external APIs, save/replay semantics, or permissions.

The only production portability exception is the native Windows CRT behavior where
`os.open()` returns `PermissionError(errno.EACCES)` for an existing directory. The
directory durability helper treats exactly that open-time, Windows-only,
real-directory condition as an unsupported directory-fsync capability. Directory
symlinks and Python 3.12 directory junctions are reparse-point boundaries and are
explicitly excluded; an `EACCES` for either still propagates. All other open errors
propagate. If a directory descriptor is obtained, every `os.fsync()` error still
propagates and the descriptor is closed.

The following contracts remain unchanged:

- immutable files use exclusive `xb` creation and refuse overwrite;
- ordinary file content is flushed and `os.fsync()` completes before return;
- returned content hashes remain SHA-256 of the exact written bytes;
- progress JSON keeps temporary-file write, flush, file `fsync`, and atomic replace;
- temporary files are removed after replacement or failure;
- POSIX directory open/fsync behavior is unchanged.

## Frozen-byte checkout contract

R803 and multimodal tests validate a small set of checked-in fixture/evaluation
inputs by exact SHA-256. A Windows checkout with global `core.autocrlf=true` must
therefore not rewrite those bytes. `.gitattributes` enumerates only the text files
whose exact LF bytes are named by checked-in SHA fields:

- `docs/evals/retrieval-v1.jsonl`;
- `docs/evals/multimodal-golden-v1.json`;
- `docs/evals/r100-research-cases-v1.json`;
- `docs/evals/r100-research-cases-v2.json`;
- `docs/evals/r803-release-threshold-v1.json`;
- `docs/fixtures/evidence-contract/pdf-coordinate-fixture.json`;
- `docs/fixtures/evidence-contract/pdf-artifact-matrix-fixture.json`;
- `docs/fixtures/evidence-contract/image-coordinate-fixture.json`;
- `docs/fixtures/document-modality/markdown-note.md`.

This is intentionally not a directory-wide freeze. Ordinary review/log/README,
generator, draft and fixture-manifest files remain `text: unspecified`, as does
the complete `docs/evals/artifacts/` subtree. Binary PDF/image sources require no
text conversion override.

## Verification oracle

The dedicated Windows portability tests cover:

1. native/simulated Windows directory-open `EACCES` for a real directory;
2. non-Windows `EACCES`, Windows `EPERM`, generic `EIO`, non-directory,
   directory-symlink and junction-classified `EACCES` propagation;
3. post-open directory `fsync` failure propagation plus descriptor close;
4. immutable write content, exact hash, ordinary-file `fsync`, directory sync
   call, and overwrite refusal;
5. atomic JSON replacement, exact hash, ordinary-file `fsync`, and temp cleanup.

The independent Critical audit verified the final diff and Windows Worker evidence
and returned **ACCEPT (Critical=0, High=0, Medium=0, Low=0)**. R2 remains the
next separately gated stage; this review does not start or claim R2.

Implementer verification on native Windows:

- `git check-attr text` reports `unset` for all nine enumerated byte-contract
  inputs; ordinary review/log/README/generator/draft/fixture-manifest examples and
  an artifact path all report `unspecified`;
- Ruff reports `All checks passed!` for the changed production and test files;
- the focused portability/regression/campaign matrix reports
  `84 passed, 1 skipped in 50.29s`; the one skip is only the directory-symlink
  propagation case on this Windows account (`WinError 1314`), while the separate
  junction boundary and all non-symlink assertions execute;
- the final repo-root full Worker run reports
  `359 passed, 1 skipped in 176.82s`, with the same symlink-privilege skip.

## Independent Critical verification

The independent reviewer reran the final candidate on native Windows and recorded:

- dedicated portability tests: `9 passed, 1 skipped in 1.45s`;
- focused portability/regression/campaign matrix:
  `84 passed, 1 skipped in 50.75s`;
- repo-root Worker collection: `360` tests;
- repo-root full Worker suite: `359 passed, 1 skipped in 183.53s`;
- Ruff: `All checks passed!`;
- `git diff --check`: exit code `0`.

The only skip in all three pytest runs is
`test_windows_access_denied_for_directory_symlink_propagates`, because the current
Windows account receives `WinError 1314` when creating a directory symlink. The
junction boundary and every non-symlink assertion ran. Final findings are
`Critical=0, High=0, Medium=0, Low=0`; verdict: **ACCEPT**.
