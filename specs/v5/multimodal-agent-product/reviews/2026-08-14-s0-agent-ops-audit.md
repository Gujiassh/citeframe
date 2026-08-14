# Audit: V5-F S0 + F-AGENT + local ops

Date: 2026-08-14  
Auditor: grok-4.5 (controller re-audit, read-only)  
Main HEAD: `d00e433` (includes PR #8 S0, #9 F-AGENT, #10 env docs)

**Verdict: ACCEPT with residuals**

---

## Scope

1. S0 production registry ↔ catalog alignment (PR #8)
2. F-AGENT locator coverage SSE/Research (PR #9)
3. Local ops: alembic head, vision/ASR readiness, env docs (PR #10 + machine config)

Not in scope: R803/M404 quality, Ollama ASR, new features (PV-4, Office canvas, keyframes).

---

## Checklist

| Gate | Result | Evidence |
| --- | --- | --- |
| Production registry kinds | **pass** | `pdf,image,document,docx,xlsx,pptx,html,audio,video` all `enabled` |
| DB alembic head | **pass** | local `m7a8b9c0d1e2` |
| DB asset_types match registry expected | **pass** | `DB_vs_EXPECTED_ASSETS_MATCH True` |
| Locator types present | **pass** | includes `docx_anchor`, `html_anchor`, `audio_range`, `video_range/frame`, office kinds |
| Locator codecs for all catalog locators | **pass** | `CODEC_MISSING []` |
| Vision/caption readiness | **pass** | key configured; status `ok`; model `gpt-5.5`; base CLIProxy `:8317` |
| ASR readiness | **pass** | key configured; status `ok`; model `whisper-1` |
| API focused tests | **pass** | 33 passed (registry + S0 enable + agent coverage + evolvable head) |
| Web SSE/Research/registry tests | **pass** | 20 passed |
| Main CI (PR #8/#9/#10 merge runs) | **pass** | `success` on main for all three merges |
| Docs vs ops | **pass** | `local-env-profiles.md` + preview/accept examples document migrate + ASR/caption |
| Goal alignment (fixed DAG, no agent platform) | **pass** | F-AGENT only expands locator acceptance; no new step kinds |

---

## Findings (severity order)

### Residual (not merge blockers for this audit)

1. **PV-4** — Chat generation attach crop for **PDF** regions still open; image region crops already exist.
2. **Office viewers** — chip/metadata only; not full document canvas.
3. **Video keyframes** — types/catalog present; extraction tooling not wired (`keyframe_count=0` path).
4. **Live provider smoke** — readiness checks configuration/profile only; this audit did **not** call live Whisper/caption against CLIProxy (would spend tokens and depend on proxy model list).
5. **Stale comments** — e.g. `build_html_ready_registry` docstring still says “must not call until S0” while production already enables HTML; cosmetic only.
6. **Embedding** — may still be transitional Ollama/stub per profile docs; orthogonal to S0 catalog.

### No blockers found

- No registry/catalog skew on audited local DB.
- No missing codec for S0 locator kinds.
- No vision/ASR “not_configured” with current local secrets.
- No test regressions in the focused S0/F-AGENT suites re-run for this audit.

---

## Commands / evidence (reproducible)

```bash
uv run --project apps/api alembic -c apps/api/alembic.ini current
# m7a8b9c0d1e2 (head)

uv run --project apps/api --extra dev pytest \
  apps/api/tests/test_s0_agent_locator_coverage.py \
  apps/api/tests/test_modality_registry.py \
  apps/api/tests/test_html_sanitizer.py::test_production_registry_enables_html_after_s0 \
  apps/api/tests/test_audio_modality.py::test_production_registry_enables_audio_after_s0 \
  apps/api/tests/test_video_modality.py::test_production_registry_enables_video_after_s0 \
  apps/api/tests/test_office_ooxml.py::test_production_registry_enables_office_kinds_after_s0 \
  apps/api/tests/test_research_migration.py::test_alembic_has_one_evolvable_head_after_prompt_v2 -q
# 33 passed

pnpm --dir apps/web exec tsx --test \
  src/lib/chat/sse.test.ts src/lib/research/client.test.ts src/lib/evidence/registry.test.ts
# 20 passed

gh run list --branch main --limit 3
# PR #8 #9 #10 merge CI: success
```

---

## Verdict detail

**ACCEPT with residuals** for engineering + local ops closeout of V5-F multimodal enablement and agent locator coverage.

Safe to treat as:

- S0 production enablement: **done and consistent**
- F-AGENT locator path: **done for protocol/UI validation**
- Local DB + vision/ASR keys: **ready for preview** (restart API/Worker if not yet)

Do **not** claim R803/M404 quality pass. Do **not** claim full Office canvas or video keyframe product completeness.
