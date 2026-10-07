# Evaluation inputs

This directory stores versioned case packages, thresholds, artifacts, and hashes used by API/Worker/evaluation tests. [Evaluation](../development/evaluation.md) describes execution and evidence scope.

Keep hash-bound packages/artifacts unchanged and at original paths. `docs/fixtures/` contains parser/locator/viewer fixtures. Historical identifiers select schema versions/test data; use the [documentation index](../README.md) for current setup and features.

Fixed inputs also remain under `specs/`: the deployment product-delta manifest at `specs/v5/worker-layout/integrated-product-delta.json` and `specs/v3/multimodal-workspace/{spec,plan,tasks}.md`, whose bytes are hashed by the retrieval acceptance script. Technical redirects preserve pinned README links and a historical delivery check. Pinned component/deployment READMEs remain unchanged because deployment verification includes their source blobs; current guides are linked from `docs/README.md`.
