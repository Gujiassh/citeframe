# Citeframe evaluation tools

Offline paired evaluation, prospective campaign execution and deterministic Research acceptance.
The package depends on product contracts and runtime; production packages never depend on it.

From the repository root:

```bash
uv sync --project tools/evaluation --frozen --dev
uv run --project tools/evaluation citeframe-evaluate --help
uv run --project tools/evaluation citeframe-campaign --help
uv run --project tools/evaluation citeframe-research-acceptance --help
uv run --project tools/evaluation pytest -c pytest.ini tools/evaluation/tests
uv build --project tools/evaluation
```

Equivalent module entry points are `citeframe_evaluation.cli.paired`,
`citeframe_evaluation.cli.campaign` and `citeframe_evaluation.acceptance.cli`.
The paired command requires `--output-dir`; campaign requires `--campaign-dir`.
Acceptance supports `seed`, `run-scenarios`, `snapshot`, `verify`.

When running an installed wheel outside the source tree, set `CITEFRAME_REPO_ROOT`
to the checkout whose implementation, frozen manifests and fixture bytes are being evaluated.
Source installs resolve that checkout directly. Fixtures and reports are not copied into the wheel.
The opt-in Docker `evaluation` target includes the tool and the repository fixture paths;
`compose.r800.yml` selects it for the isolated historical Research acceptance protocol.

The synthetic `FrozenEvidencePort` intentionally ignores the query and issues evidence
from the frozen asset scope in deterministic order. Production retrieval lives in
`ai_pdf_worker.research.adapters.evidence`.

Historical package v4/v5, scorer v1/v2, diagnostic and report versions remain unchanged.
Implementation and evaluator closure hashes describe the current source layout; they cannot
be substituted into an existing frozen campaign. Historical evidence remains immutable.
A new formal campaign requires explicit owner approval and a fresh output directory.
Deterministic tests and the layout parity fixture provide engineering evidence only.

Architecture and migration details: [Worker SSoT](../../docs/ssot/worker-layout.md).
