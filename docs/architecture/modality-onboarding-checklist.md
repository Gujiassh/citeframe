# New modality onboarding checklist

Use this when adding a production `asset_kind`. Shared Chat / retrieval fusion / Citation envelope must **not** grow kind-specific business branches; put behavior in modality modules, codecs, adapters, resolvers, and web renderers.

## Checklist

1. **ModalityModule** — `asset_kind`, MIME set, `byteInspector`, `enabled` flag, metrics namespace.
2. **Catalog migration** — `asset_types` / representation / content_unit / locator type rows + `contract_version`; app startup must match registry.
3. **Representations & ContentUnits** — immutable representations, typed units, cleanup policy.
4. **Locator detail table + codec** — typed detail (not free-form JSON truth); serialize/clone/retrieval_key; SSE/DTO union if new kind.
5. **Worker adapter** — parse → units/locators/manifest; no direct commit ownership outside orchestrator rules.
6. **Retrieval channel signatures** — exact `(asset_kind, unit_kind, representation_kind, locator_kind)` tuples.
7. **Web production-registry** — upload accept, renderer binding, locator summary.
8. **Evidence targets / visual enrichers** (optional) — register resolvers or `VisualEvidenceEnricher` implementations; do not special-case inside `services/chat.py`.
9. **Tests** — upload/MIME, parse, codec, retrieval scope, citation clone, viewer parse, delete/restore as applicable.
10. **S0 enable** — catalog `enabled=true` only with code module; readiness fails on drift.

## Forbidden in shared layers

- `if asset_kind == "..."` business rules in Chat prompt assembly or retrieval RRF core (dispatch via registry only).
- Guessing unknown locator kinds into page/image/text.
- Fake ASR/caption/keyframe bytes when capability missing (fail-closed or soft-skip with stable codes).

## References

- [`modality-extension-contract.md`](modality-extension-contract.md)
- [`specs/v5/architecture-hardening/`](../../specs/v5/architecture-hardening/)
