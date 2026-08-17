**执行入口：** [`current-execution-plan.md`](current-execution-plan.md)

# Decision: V5-F Modality Completion and Agent Collaboration Completion

Date: 2026-08-13  
Status: **approved for staged implementation** (owner 2026-08-13; **implementation not started** — hold until owner says start)  
Source: owner request to complete remaining modalities and improve multi-agent collaboration.  
Owner also approved recommended OD reopen path (HTML/Office kinds/ASR-Audio/Video separate) and deferred paid R803.  
Paid R803 / M404 remain deferred (see V5-E deferral 2026-08-13).

> **Status supersession (2026-08-17):** This file freezes the **2026-08-13 OD / scope decision**.  
> V5-F **engineering implementation completed** on main (S0 nine kinds, F-AGENT, residual P1, PPTX layout).  
> For **current** product status use `docs/architecture/implementation-progress.md` §2–§7 and `S0_HANDOFF.md`.  
> Historical rows below (e.g. “implementation not started”, OD open) are **point-in-time**, not live blockers.


## 1. Intent

V5-A–D delivered an `internal_preview` engineering product with:

- production modalities: `pdf`, `image`, Markdown-only `document`
- fixed Research multi-agent productization
- mixed Workspace engineering gates

V5-F is the **capability completion** phase:

1. **Modality completion** — bring remaining planned media/document kinds onto the same Asset/Evidence kernel, one closed slice at a time.
2. **Agent collaboration completion** — make Research fully work across all enabled modalities and close product/UX gaps **without** becoming a general agent platform.

V5-F is **not** V5-E. No formal model-quality campaign and no M404 claim are required to implement V5-F engineering slices.

## 2. Current baseline (facts)

| Area | Done | Not done |
|---|---|---|
| PDF | production deep | — |
| Image | production deep | — |
| Markdown document | production v1 | HTML/Office not enabled |
| HTML | rejected OD-B5 | sanitizer/resource policy missing |
| Office | not started | brief + kinds + parsers missing |
| Audio | blocked OD-B6 | ASR capability contract missing |
| Video | blocked OD-B7 | temporal + keyframe contracts missing |
| Research multi-agent | fixed DAG productized | not fully multi-modal-aware; no free-form agents |
| Quality/user value | engineering only | R803/M404 deferred |

## 3. Scope decisions (proposed)

### F0 — Product stage

- Product stage remains `internal_preview` until V5-E evidence exists.
- Engineering gates may set `engineeringGate=pass` / `releaseGatePassed=true` for a slice only as **internal-preview engineering**.

### F1 — Modality set for V5-F

Complete these production modalities, in order:

1. **HTML document** (document family; re-open OD-B5 with a strict sanitizer policy)
2. **Office documents** — phase as:
   - F1b: `docx` first
   - F1c: `xlsx`
   - F1d: `pptx`  
   Prefer **separate `asset_kind` values** (`docx`, `xlsx`, `pptx`) over one vague `office` blob kind, so registry/catalog/tests stay exact.
3. **Audio** (`audio`) with typed `audio_range` locator and transcript ContentUnits
4. **Video** (`video`) with typed time/frame locators, transcript + keyframe Representations

Out of V5-F unless owner expands scope later:

- arbitrary binary / CAD / 3D
- live capture / streaming ingest
- full browser sandbox for active HTML scripts
- email/mbox as first-class modality

### F2 — Kernel rules (non-negotiable)

Reuse `docs/architecture/modality-extension-contract.md`:

- closed registry + catalog + contract_version alignment
- no MIME guessing; byte inspector + declared MIME fail-closed
- typed locator detail tables; no free-form JSON as evidence truth
- Citation/NoteSource/Chat envelope unchanged (union expansion only)
- no auto-fallback provider, no silent coercion, no auto-reindex on settings change
- each modality delivers: upload → ingest → Representation/ContentUnit/locator → retrieval → Citation/NoteSource → Viewer → retry/delete/restore

### F3 — Agent collaboration completion (non-platform)

Keep OD-C1 / OD-C7: **fixed DAG only**. Agent completion means:

- Research evidence search/load works for **all enabled** locator kinds
- plan/branches/artifacts can cite multi-modal evidence without kind leakage
- timeline/controls remain understandable with multi-modal evidence bundles
- mixed-modality Research production-start + recovery/restore engineering gates
- role I/O remains versioned production v1 unless a **new registry version** is explicitly approved (default: **no new registry version** in V5-F)

Explicit non-goals (still rejected unless a new OD reopens them):

- dynamic DAG / user-editable graph
- free plugins / shell / arbitrary network tools
- provider/model selector UI
- implicit long-term memory writes
- unlimited recursive agents

### F4 — Open decision disposition (proposed)

| ID | Previous | V5-F proposed |
|---|---|---|
| OD-B5 HTML | `rejected` | **reopen → approve** with sanitizer/resource policy freeze |
| OD-B6 Audio | `open` | **approve** ASR capability contract before registry enable |
| OD-B7 Video | `open` | **approve** separate video kinds + shared text retrieval, not “video = audio” |
| OD-C6 selector | `rejected` | remain rejected |
| OD-C7 platform | `rejected` | remain rejected |
| OD-C8 role I/O | `approved` | remain v1; no new version without checklist |

### F5 — Implementation order

```text
F-G0  baseline + decision freeze + lane map
  -> F-HTML   (document family #2)
  -> F-DOCX
  -> F-XLSX
  -> F-PPTX
  -> F-ASR    (capability contract + fail-closed wiring; no fake ASR)
  -> F-AUDIO
  -> F-VIDEO
  -> F-AGENT  (cross-modal Research completion; can start parallel after F-HTML)
  -> F-MIX    (mixed all-enabled-modality Workspace + Research + restore)
  -> F-ACCEPT (full regression + Critical)
```

`F-AGENT` may start after HTML is green if Research only needs document-family expansion first; full multi-modal agent gates wait until Audio/Video exist.

### F6 — Save / API / schema impact policy

- Additive catalog rows, typed detail tables, OpenAPI discriminator variants: **allowed** after per-slice freeze.
- Changing Citation/NoteSource/Chat columns, Research ledger status sets, or finished artifact bytes: **stop + save-contract-checklist**.
- Enabling a modality requires code module + migration + fixtures + Critical for that slice.

## 4. Success definition

V5-F engineering success:

1. All F1 modalities enabled in production registry with full longitudinal loop.
2. Mixed Workspace can hold PDF + Image + Markdown + HTML + Office + Audio + Video without cross-kind leakage.
3. Research fixed multi-agent flow can plan/search/cite/recover across those modalities.
4. Desktop/mobile production-start evidence and empty-target restore identity for the mixed set.
5. No paid quality claim; product still `internal_preview`.

## 5. Approval gate for this decision

Owner accepted this decision on 2026-08-13. Implementation remains paused until the owner explicitly says to start coding.  
Field-level freezes live in `v5f-detailed-spec.md` and per-modality brief sections; each modality still needs its own implementation gate before registry enablement.
