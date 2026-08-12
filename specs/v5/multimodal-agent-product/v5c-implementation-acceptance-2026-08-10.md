# V5-C Implementation Acceptance Record

Date: 2026-08-10

## Scope

This slice implements the approved V5-C product contract for Research usage,
per-call context/output limits, optional pricing metadata, frozen retrieval
configuration, and strict versioned production Agent I/O. It does not add a
general Agent platform, per-call billing UI, model-quality claims, or M404 user
validation.

## Acceptance Status

**Engineering acceptance: ACCEPT (2026-08-10).** The current v1 registry is
enabled for new runs; the explicit legacy registry remains recovery-only. F1
registry-version mapping drift and F5 historical-row bytes/hash evidence are
Medium follow-up risks and do not block this frozen v1 release gate.

- Production current registry: `research-agent-results-v1`,
  `research-context-policy-v1`, `research-compact-policy-v1`.
- Historical rows: explicit `*-legacy-v0` registry entry; no implicit current
  fallback for recovery.
- `maxInputTokens` and `maxOutputTokens`: per-provider-call context/output
  gates; cumulative totals are telemetry only.
- Missing pricing: Research may start; unknown cost remains `NULL`; Web shows
  usage only.
- Retrieval: Researcher passes frozen `execution.provider.retrievalTopK`.
- Context overflow and truncated output: stable failure codes before publish.

## Evidence

| Gate | Result |
| --- | --- |
| API full suite | `561 passed, 1 warning` |
| Worker full suite | `295 passed` |
| Web unit suite | `130 passed` |
| Research production-start Playwright | `5 passed` |
| V5-C API contract/provider/recovery/evidence focused | `84 passed, 1 warning` |
| Frozen retrieval evidence/V5-A/capability rerun after exact-limit repair | `27 passed, 1 warning` |
| Post-review Worker Agent I/O/runtime focused | `34 passed` |
| R803 campaign regression focused | `55 passed` |
| compileall / diff check | passed |

| PostgreSQL online migration round-trip | passed; `f9a1b2c3d4e5 -> h2b3c4d5e6f7 -> f9a1b2c3d4e5 -> h2b3c4d5e6f7` |
| R800 v6 isolated Compose artifact | `engineeringGate=pass`, `releaseGatePassed=true`, `10/10` scenarios, restore identity and zero-residue cleanup passed |

## Residual Follow-up

- F1: require an executable role/version registry mapping test before enabling a
  future registry version; current frozen v1 mappings are accepted.
- F5: add a live pre-V5-C historical database-row fixture proving unchanged
  finished-artifact bytes/hashes through legacy retry/recovery before enabling a
  future registry version.
- The existing `e6a7b8c9d0f1` offline-incompatible migration still blocks
  `alembic upgrade head --sql`; online PostgreSQL migration is green.
- Do not treat this record as model-quality or user-value evidence; R803/M404
  remain deferred.
- No commit or push in this slice.

## Terr Repair Slice

The Critical review repair slice binds production and legacy role contracts to
actual Worker validators, prompt nodes and runtime adapters. Provider adapters
now require explicit completion metadata; typed compact context has a recursive
lossless decoder and never expands a fitting context; legacy plan/agent readers
use explicit schema-version readers; and `retrievalTopK` mismatches fail closed
before tool reservation. These repairs passed the focused and full API/Worker/Web
static gates, production-start Research, online migration, and the independent
R800 v6 engineering/release gate. The remaining F1/F5 items are Medium
follow-up risks, not blockers for the frozen v1 registry.
