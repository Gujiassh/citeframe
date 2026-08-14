# Plan audit: Office canvas + Video keyframe + PV-4

Date: 2026-08-14  
Auditor: grok-4.5  
Plan: `plan-office-canvas-keyframe-pv4.md`

**Verdict: ACCEPT** — proceed with lane-pair execution.

## Checklist

| Gate | Result |
| --- | --- |
| Goal alignment | **pass** — three residuals only; fixed DAG/agent platform not reopened |
| Smallest safe change | **pass** — PV-4 reuses generation `image_payloads`; Office mirrors document content API; keyframe soft-skip |
| Contracts | **pass** — additive EvidenceTarget kind; no locator meaning change; no fake frames |
| Parallel ownership | **pass** — non-overlapping primary files; merge A→C→B or A∥C then B |
| Fail-closed | **pass** — soft-skip ffmpeg; crop errors stable codes |
| Test plan | **pass** — unit/contract per lane |
| Residuals explicit | **pass** — retrieval auto-crop P1; PPTX graphics text-first |

## Findings

None blocking. Notes:
1. Confirm `pymupdf` available to `apps/api` before PV-4 (else vendor thin crop helper carefully).
2. CI: mock ffmpeg; document host dependency.
3. Cap crop resolution to bound generation payload size.

## Decision defaults confirmed

- Keyframe without ffmpeg: soft-skip  
- PV-4 v1: explicit `pdf_region` targets only  
- Office: text canvas + highlight  

