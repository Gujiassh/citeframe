# R803 First Real-Model Paired Run

## Decision

The first approved provider-backed R803 run is retained as a failed baseline.
Quick completed all six cases; Research completed four and failed both refusal
cases. R803 remains open, model quality is `not_evaluable`, M404 remains independently
`not_evaluable`, and the product stays `internal_preview`.

The later evaluator-only strict transport and immutable v2-v4 history are documented
in [`r803-strict-structured-output-follow-up.md`](r803-strict-structured-output-follow-up.md).

## Frozen Package

- Provider/model: `openai / gpt-5.5`
- Endpoint/protocol: `https://us-direct-api.sourcesdata.com` / `responses-v1`
- Cases: all 6 cases in `r100-research-cases-v1.json`
- Assets: `pdf-coordinate`, `pdf-artifact-matrix`, `image-coordinate`
- Scorer: `r100-v1`
- Package: [`r803-evaluation-package-v1.json`](r803-evaluation-package-v1.json)
- Canonical reports: [`artifacts/r803-v1/`](artifacts/r803-v1/)

Comparison keys:

```text
fixtureManifestSha256=acc5ca446127d8dbb144f810324c8bb01a5f98cf8f95a672804e46293d32b377
assetScopeSha256=35a2ba92905cd87d5c85a6f86464a297d649e94bb9ab9a3dd7ca75da3f4c06e2
provider=openai
model=gpt-5.5
providerProfileSha256=250a6b422cc64f05839658f3d990279c05e221c1714e01ca58afbfd29e8c1290
scorerVersion=r100-v1
```

The Research binding additionally freezes Workflow V2, all five PromptVersion
hashes, and the evaluator-only `research-agent-results-v1` schema hash. No API key
or Authorization value is persisted.

## Results

| Metric | Quick | Research |
| --- | ---: | ---: |
| Completed cases | 6/6 | 4/6 |
| Engineering gate | pass | fail |
| Provider calls | 6 | 36 |
| Input tokens | 28,154 | 171,661 |
| Output tokens | 931 | 9,926 |
| Wall time | 52.700 s | 443.375 s |
| Cost | USD 0.084350 | USD 0.578043 |
| Claim support | 0.8571 (n=7) | 1.0000 (n=7 completed claims) |
| Evidence recall | 1.0000 (n=6) | 1.0000 (n=4) |
| Evidence precision | 0.9444 (n=6) | 0.7083 (n=4) |
| Locator accuracy | 0.8333 (n=6) | 0.2500 (n=4) |
| Conflict detection | 1.0000 (n=6) | 1.0000 (n=4) |
| Refusal correctness | 1.0000 (n=2) | not evaluable |
| Parallel speedup | not applicable | 1.9900 |

These values are observational. There is one execution per case and mode and no
approved model-quality release threshold, so no Quick-versus-Research quality
winner or release claim is valid.

## Failure

`r100-refuse-energy` and `r100-refuse-customer` failed at the Researcher node with
`researcher_invalid_output`. In the observed pattern, the model emitted one JSON
object resembling a tool request immediately followed by the required Claims JSON
object. The runtime requires exactly one JSON object, so strict `json.loads` rejected
the concatenated payload.

This behavior is intentionally fail closed. The evaluator does not search for a
later object, strip a prefix, silently retry a schema violation, or score the case
as a refusal. The R700 import report uses its closed case-level `scorer_error` value
and the top-level `schema_violation` category; the paired artifact retains the
node-level `researcher_invalid_output` root cause. The next slice must solve
structured output with a properly versioned strict contract and produce a new full
six-pair run without rewriting this evidence.

## Provenance Boundary

The complete output schemas were required to make every real Agent node executable
for this evaluation. They are injected through the evaluator's explicit
`research-agent-results-v1` binding and included in its hash. Production Research
keeps the existing V2 runtime schema values because its immutable ExecutionSnapshot
does not separately freeze this new schema version. This avoids assigning different
effective inference contracts to the same historical PromptVersion IDs.

## Artifact Integrity

```text
paired-quality-report.json  88d32663f7fdc95056f480dc1166a36d21dfec4e5b98c68bf0ee617c8ff9a6fd
quick-evaluation.json        4ee710cb132b36b86385080d48170e8ed9ce393c26e3955193e363271b144e18
research-evaluation.json     ae1b867532629755de9ef7815e4d9eb2631825753f74dc1d42f106307b8f03e5
```

`sha256sum -c SHA256SUMS` passed for all three canonical reports.

## Delivery Verification

- R803/Research focused tests: `31 passed`
- Worker full suite: `154 passed`
- Changed Python modules: Ruff and `compileall` passed
- Repository whitespace gate: `git diff --check` passed
- R700 import parsing: Quick `completed/pass`; Research `failed/fail`; both
  model-quality and user-value gates remained `not_evaluable`
- Comparison-key and Research binding reverse oracle: passed
- Relative Markdown links and fence balance: passed
- API-key/Bearer secret-pattern scan: passed
- Canonical `SHA256SUMS` verification: passed
