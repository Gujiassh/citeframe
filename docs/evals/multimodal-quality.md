# PDF/Image internal quality suite

## Purpose

Phase 4 M401 separates three kinds of evidence instead of treating one test set as proof of everything:

- `retrieval`: the approved asset and Evidence location must enter the candidate set under the declared scope.
- `evidence`: the locator must open the approved PDF page/region or Image region without geometry drift.
- `answer`: the answer must contain the approved claims, or refuse when the selected assets contain no evidence.

The 21-case multimodal set is an engineering oracle built from deterministic, non-confidential fixtures. PDF/Image region targets describe the human-approved relevant surface. M402 may accept a production locator whose rendered overlay intersects and covers that surface; it must not require a table/figure/OCR locator to equal a manually drawn relevance box. Native PDF text pages remain `pdf_page` evidence unless the parser actually produces a region ContentUnit. The set does not prove model answer quality or user value. The existing 40-case real PDF retrieval set remains a separately frozen reference baseline, and Beta validation remains M404.

## Canonical files

- `multimodal-golden-v1.json`: fixtures, immutable hashes, scopes, questions, layer, task type, disposition, answer points, and typed Evidence targets.
- `multimodal-failures-v1.json`: frozen failure taxonomy and only those failure samples that have a persisted reproduction test.
- `multimodal-answer-oracle-v1.json`: frozen complete-output allowlists and production prompt constraints for fail-closed answer evaluation.
- `multimodal-quality-v1.json`: deterministic coverage report generated from the two inputs.
- `multimodal-execution-v1.json`: M402 per-case execution report, artifact hashes, and release-gate status.
- `artifacts/m402-v1/`: Worker execution data, no-mock desktop/mobile Playwright measurements and screenshots, plus the immutable real-model execution snapshot.
- `m402-execution-source-provenance-v1.json`: versioned, fail-closed approvals for specific frozen M402 execution artifacts. A historical exception is accepted only when the exact `(executionSchemaVersion, testFile, testFileSha256, executionArtifactPath, artifactSha256)` identity matches; this is a controlled manual runner-identity repin for those path+bytes, not proof that the frozen outcomes were produced by the approved runner bytes. Rewriting frozen artifact hashes to the current harness is forbidden.
- `retrieval-v1.jsonl`: 40-case real PDF retrieval reference baseline; its hash and case count are checked by the multimodal suite.

The v1 taxonomy contains `asset_parse`, `retrieval_candidate`, `rrf_ranking`, `answer_support`, `evidence_localization`, `table_structure`, `visual_semantics`, `false_answer`, `viewer_rendering`, and `workflow`. A taxonomy category may have zero samples; that means no reproducible failure is currently locked for that category, not that the category passed.

## Validation

From the repository root:

```bash
uv run --project apps/api python apps/api/scripts/validate_multimodal_quality.py \
  --output docs/evals/multimodal-quality-v1.json
uv run --project apps/api pytest apps/api/tests/test_multimodal_quality.py -q
uv run --project apps/api python apps/api/scripts/validate_multimodal_execution.py \
  --real-model docs/evals/artifacts/m402-v1/real-model-execution.json \
  --output docs/evals/multimodal-execution-v1.json
uv run --project apps/api pytest apps/api/tests/test_multimodal_execution.py -q
```

Validation fails closed on unknown fields, duplicate IDs, source/manifest/baseline hash drift, path escape, missing files, invalid manifest schema or coordinate geometry, invalid locator shapes, target/manifest disagreement, selected-scope violations, thin layer/modality/task coverage, invented evidence for refusal cases, and failure entries without a real regression test. The 40-case reference reuses the production evaluation label loader. Failure samples persist only `testFile + testName`; the report generates structured `reproductionArgv`, and arbitrary command text is forbidden.

## Current coverage

- 21 multimodal engineering cases: 7 retrieval, 7 evidence, 7 answer.
- Modalities: 11 PDF, 6 Image, 4 mixed.
- Task types: exact fact, cross-asset comparison, method/constraint, table, chart, image, and no-answer.
- 2 explicit no-answer cases.
- 3 deterministic source fixtures plus the frozen 40-case real PDF retrieval baseline.
- 6 regression-locked failures covering parse, candidate scope, RRF limit behavior, PDF localization, table state isolation, and visual caption semantics.

M402 must execute the applicable rows through API/Worker/Web/Playwright and record actual outcomes, including answer support and refusal behavior. M401 `coveragePassed=true` only means the evaluation contract is internally complete and valid.

## Current M402 execution

- The single Worker node directly consumes all 21 golden cases through real PDF/Image adapters, production retrieval scope/Dense/lexical/RRF logic, and Chat orchestration. Its scripted generation proves orchestration only; a separate approved run executes the 7 answer/refusal cases through the configured OpenAI-compatible `gpt-5.5` provider.
- A temporary PostgreSQL/MinIO workspace is opened through the real BFF with no `page.route` interception. All 7 evidence cases and 8 citation targets pass at 1440x1000 and 390x844, producing 16 screenshots.
- PDF checks include the requested page, a nonblank canvas, and rendered overlay intersection. Image checks include the frozen oriented representation, nonblank pixels, and rendered overlay geometry. The mixed case navigates both PDF and Image locators.
- The minimum approved-area coverage ratio is `0.294333`; desktop/mobile runs record 28 successful BFF responses each. This replaces the earlier unsafe intersection/min-area value `0.997906`. The 16 screenshots, 4 raw execution reports, frozen answer oracle, and single-snapshot execution-source provenance contract are SHA-256 registered as 22 artifacts by `multimodal-execution-v1.json`.
- The opt-in Worker runner records the exact golden question, full generation messages and canonical SHA-256, provider/model/output, citation-target coverage, runner source SHA, and per-case diagnostics. The report service independently re-evaluates output against the frozen oracle and rejects forged `matchedAnswerPoints` or `passed` values.
- The answer oracle removes allowed numeric citation tokens, normalizes the complete output, and requires an exact match against a small frozen allowlist. It intentionally prefers false negatives over allowing negation, antonyms, swapped PDF/Image attribution, or refusal text with an added unsupported answer to open the release gate. New paraphrases require explicit human review before entering the allowlist. The prompt validator parses the production `Question + Asset evidence context` contract and binds the system prompt hash, current configured provider/model, golden Asset scope, target locator kinds, and required/forbidden Evidence text.
- Artifact hashes and source binding detect drift inside the controlled acceptance workflow; they are not cryptographic proof that a remote provider produced the file. Resisting an actor who can consistently rewrite the complete raw/report artifact set would require a provider-verifiable receipt or an independent signing service and is outside M402's local evidence threat model.
- Current/newly generated Worker or real-model executions must embed the exact current runner `testFileSha256` and may live at any repository-relative artifact path. The frozen `artifacts/m402-v1` Worker/real-model snapshots may keep a non-current embedded hash only through an explicit provenance entry that binds that exact artifact path and bytes. Git history shows those artifacts first landed in `9aa3bf2` with different embedded hashes; `85305e5` later re-pinned the embedded `testFileSha256` to `fb59...` without re-running outcomes. The contract therefore records `originalArtifactCommit`, `originalEmbeddedTestFileSha256`, `originalEmbeddedRunnerCommit` (or `not-attested`), `approvedRunnerCommit`, and `identityRepinCommit` so approval is not confused with execution-source proof. Unknown schema/path/hash combinations fail closed; path-only, hash-only, or copied-path matches are rejected.
- The pre-call M402 harness passed independent Standard review after adversarial checks for negation, antonyms, modality swaps, unsupported facts appended to refusals, provider failures, zero-call opt-in behavior, prompt provenance, Image-disabled state, and deterministic report replay.
- One explicitly approved run sent exactly 7 non-confidential synthetic prompts to the configured `openai / gpt-5.5` provider. All calls returned without provider errors, all required citation targets were covered, and all 5 answer plus 2 refusal outputs passed independent report-side evaluation after six correct complete-output paraphrases were manually reviewed into the frozen allowlist. The raw output/messages were not rewritten; its capture-time `passed=false` diagnostics remain preserved and do not control the gate.
- Current report state is `engineeringExecutionPassed=true`, `fullStackEvidencePassed=true`, `realModelQualityPassed=true`, and `releaseGatePassed=true`; all 21 cases are `passed` and `pending=[]`. This proves the M402 engineering release contract, not M404 user value.
