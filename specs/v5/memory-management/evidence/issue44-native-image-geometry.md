# Issue44 native image geometry — implementation evidence

## Scope and accepted baseline

Controller activates the two-file geometry implementation lease under exact §12 contract SHA-256 `074C4E95490E190257943C9F1102C54246FFDF88D5C60ADA374FA27779EC7B97`, independently accepted in original review `9AD4D73D3D962A94CCC93BB284F96297F165C1A9C184E2D466E9C0B01F9A57D0`. Controller-reported PR52 baseline is `7d6be8a236d48135460b0a5677b6ea01edd31b4f`. No Git calls used in this slice.

Assigned product files: NEW apps/api/src/ai_pdf_api/modalities/native_image_geometry.py and NEW apps/api/tests/test_native_image_geometry.py. Original implementation owner reused. This evidence file is the only documentation write for this slice; approved contract and original reviewer artifacts stay frozen.

Fixed old oracle source hashes, verified before implementation:
- image_evidence_targets.py: `80A1915CE56EA42CDFB1963724BD5918017274686E8942AC55CCFAE127A26EF7`
- pdf_evidence_targets.py: `9EC66A868D963FAD94ECD594F07D418C5A501B785CEFE7E63DB35351453D3229`

Target is actual strict PNG crop arithmetic and PDF final-transform calculation from numeric tuples, plus real old-function byte/DPI/bbox/order parity on bounded synthetic fixtures. No source reader, supervisor/launcher, lease/budget manager, source authorization, shared image ABI, native/default resolver/router wiring, dependency or CI change. NI1–NI5/full R5 and production activation remain outside this implementation approval. Existing profile/builder/core acceptance is not reopened.


## Frozen implementation candidate — 2026-09-29

| File | SHA-256 |
|---|---|
| apps/api/src/ai_pdf_api/modalities/native_image_geometry.py | `62B89093C67B88B16CB926C61A4DC1FC3725341332350B32BD88FFCA4532368C` |
| apps/api/tests/test_native_image_geometry.py | `538AB2C3575E04EDC66BBC2DBC43A573DE05BCB9B07B3598CCADB902FA3B25F2` |

The actual product implements the approved two pure functions and local frozen PdfRenderPlan. Strict built-in int/float and exact tuple validation precedes native arithmetic. PNG isolates the complete Decimal context (precision28, HALF_EVEN, exponents, flags, traps) and preserves original floor/ceil/clamp. PDF lazily checks PyMuPDF1.28.2 and required primitives, computes first/final bbox using native intersect/transform/round, preserves old matrix multiplication order, and returns dpi150 or matrix/dpi=None as the original branch requires. No PDF open/display-list/pixmap allocation, codec IO or source/budget implementation is present.

Developer-root inspected both actual new files and separately executed the dedicated suite with guards after the implementation agent run. This is developer evidence, not controller-independent verification. No existing native function or default resolver is changed and the test asserts no production source imports the new module.

### Executed evidence

Environment: **Windows, Python3.12.10, PyMuPDF1.28.2, Pillow12.3.0**, read-only cached dependencies. Developer final guarded run: **119 passed in2.37s**. Developer-root separate final guarded run: **119 passed in2.41s**, collected=passed=119, skip/deselect/xfail flags false, exit0. The developer-root run denied all ai_pdf_api/ai_pdf_worker/citeframe_contracts imports with MetaPathFinder and denied socket creation/socketpair/create_connection plus DNS functions. The actual module path was asserted local after execution. No conftest/plugin autoload/cache/bytecode writes.

The119 cases include:
- **48 actual PDF old-oracle matrix cases**,3 sizes×4 rotations×2 cropbox variants×2 regions. Developer-root collected per-test evidence and confirmed **8 downscale branches**. Every case compares actual PNG bytes, first/final bbox, PNG DPI and metadata; candidate renders only final output in the fixture while old oracle uses its original branch.
- **10 bounded complex PDF fixtures**: annotation absence/presence under old default annotations=True, transparency, embedded small image, negative/positive media origin, direct/inherited UserUnit placement, two rounding-edge clips. These pass on this pinned Windows build; no claim that all possible complex PDFs are covered.
- **64 ordered tiny crops each for RGB and RGBA**, preserving actual old-function PNG bytes/dimensions/order. Developer recorded RGB4416bytes (ordered concatenation SHA `3f31e1d2e47899f6483d9578c5890513f32750203c77b8c775a9a21531a2c26d`) and RGBA4480bytes (`96abbf8bfd23e714bbe85454db90cc8cec280fccf217c2cb2ae572d946bb71a0`). These colored fixtures differ from the reviewer's earlier5120-byte fixture; equality is established against their own identical old/new inputs.
- Edge/fractional/very-small PNG regions; ambient Decimal precision/exponent/rounding/traps changed without affecting valid result; strict bool/subclass/custom coercion/overflow/nonfinite/tuple negatives; empty/disjoint/native rounding and unsafe-intermediate safe errors; frozen return record; unknown/missing PDF engine rejects while PNG remains usable.
- During planner invocation, fixture instrumentation forbids fitz.open, Page.get_displaylist, Page/DisplayList.get_pixmap and native pixmap allocation. Fixture setup and old/new render occur outside that guard. Static product-call scan additionally rejects IO/render functions.

Tests record bbox/DPI/PNG digest using pytest user_properties. No fake source/tokenizer/authority or settings substitute is used. The old success oracle is hash-pinned AST extraction from actual native source; the local EvidenceTargetError binding is only an exception stand-in to execute those pure old functions without importing application/DB. Valid parity cases do not use it as a replacement for resource/source authority.

### Reproduction and guard scope

```text
PYTHONDONTWRITEBYTECODE=1
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest --noconftest --strict-markers -p no:cacheprovider
  -o pythonpath= -o xfail_strict=true -q
  apps/api/tests/test_native_image_geometry.py
```

Local PYTHONPATH: apps/api/src plus read-only uv archive directories under C:/Users/baiao/AppData/Local/uv/cache/archive-v0/: `40dO6OBHTHkqR0U3`, `VkeVKl2g50l51Fjc`, `xIlLX82QEusHhXca`, `RHvkbWyG_J6xPpug`, `2ITaIXdneZF10lum`, `L-k_dNEQiegHAoRr`, `9WszWcRZL3SpM_A6`, `owHdhenMp3yGpVwQ`.

For the guarded developer-root run, the same pytest arguments were passed to pytest.main after installing import/network denial and a plugin rejecting collect/runtime skip, deselection and wasxfail; sessionfinish required testscollected==119 and successful call reports==119. A separate test subprocess verifies the real module can load and perform PNG arithmetic with PyMuPDF/Pillow/all application packages unavailable. No package installation or uv sync was performed. No CI edits or hosted collection claim.

### Exact oracle EOL portability

The approved old native files currently have CRLF bytes. Existing .gitattributes does not force LF for these files. The tests accept only the approved exact CRLF hash or the exact LF-only counterpart computed from the same inspected content:

| Source | Approved CRLF | Fixed LF-only equivalent |
|---|---|---|
| image_evidence_targets.py | `80A1915CE56EA42CDFB1963724BD5918017274686E8942AC55CCFAE127A26EF7` | `6E4D4F41B3A9EF5201A8390CDCA9C17AC36FE2E37D5E6A074ADF753035FB6DD8` |
| pdf_evidence_targets.py | `9EC66A868D963FAD94ECD594F07D418C5A501B785CEFE7E63DB35351453D3229` | `A520DA2A374FE5289DDE6A109558E068C78908557F030C32278ED8759426398A` |

This is a two-value byte-exact allowlist, not runtime source normalization or ignored arbitrary source drift. Original files were not modified. This portability detail is included for original code review; it does not claim a Linux execution.

### Known boundary and remaining gates

Actual modalities/__init__.py eagerly imports registry/image-caption/settings and ingestion/models. Under the two-file lease it is untouched. Tests load the **real new module file** by importlib.util.spec_from_file_location and register only that module for dataclass support; no fake package/dependency is installed. The demonstrated independent import applies to this file. Ordinary package-qualified import still executes existing eager package initialization and is not claimed pure. Later native/isolated-child integration must address that package entry under its own owner lease.

Windows parity passed. **Linux pinned-build parity has not run** and is required before production use. No kernel/launcher/reader/resource-limit/source authorization/lease/retained-output integration was implemented or tested. Full R5, original NI1–NI5 resource gates, #42 image ABI and native lifecycle/source integration remain separate. This slice makes no production dispatch/capacity/exact-image-counting claim. It is frozen for the original independent reviewer; developer and developer-root passes do not self-close actual-code review.

Approved contract SHA074C4E95… and original review SHA9AD4D73D… remain unchanged. Old native hash oracles are unchanged; dedicated profile/builder workflow remains354B158C…. No CI/dependency/schema/router/default resolver/ABI/loader/launcher/lease edits. No Git/commit/push, network/provider/model spend or UI46 operation. Write-back is this evidence only; no private memory or external workbench write.


## Subsequent independent acceptance and CI handoff — 2026-09-29

Original reviewer accepted the frozen geometry code/tests in review SHA-256 `FFBEDACA637148142EA518154ABA6AC31BAE77B560FD705CBB9C1F35ABA4BDF9`. Reviewer evidence comprises119 submitted cases plus96 additional PDF/512 Decimal/14 strict rejection probes, with the platform/scope recorded in that review. Those are reviewer executions, not runs performed by this developer-root.

Controller separately reports running the119 cases with the API venv: **119 passed in1.45s**, with product/test hashes62B890…/538AB2… unchanged. This is controller-reported independent evidence; it is distinct from the earlier developer-root119/2.41s run and its guards. The original119/2.37s remains the implementation agent run. Attribution above is corrected accordingly, without changing the actual results or claiming one actor's guards for another actor's command.

Current authorization adds only `.github/workflows/memory-image-geometry.yml` and own CI evidence; geometry product/tests remain frozen. Linux hosted parity will be recorded only after actual Actions execution. No launcher/build/native activation authorization follows from this CI work.
