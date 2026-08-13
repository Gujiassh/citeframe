# V5-F Plan Audit (Controller Review)

Date: 2026-08-13  
Review class: **Standard → Critical** (Critical once schema/locator enablement starts)  
Subject: modality completion + agent collaboration completion plan

## Verdict

**PROCEED with staged implementation after owner accepts `decision-2026-08-13-v5f-scope.md`.**  
The plan is architecture-aligned. Several items are **blocked on explicit OD freezes** (HTML sanitizer, ASR, Video temporal model). Do not start coding those slices on “intent alone.”

## Checklist

| Area | Verdict | Notes |
|---|---|---|
| Goal alignment | **pass** | Matches owner ask: complete modalities + improve agents; keeps V5-E paid quality deferred |
| Scope control | **pass-with-caution** | “Complete modalities” is large; order HTML→Office→Audio→Video prevents boiling the ocean |
| Architecture / boundaries | **pass** | Reuses modality-extension kernel; agent stays fixed DAG (OD-C7 still rejected) |
| Data contracts | **pass-with-gate** | Additive locators OK; Citation envelope unchanged; any ledger/role version change needs checklist |
| User-visible flow | **pass** | Agent work is multi-modal evidence UX + controls, not a new product story that delays semantic state |
| Security | **pass-with-gate** | HTML/Office macro/script risk called out; must freeze policies before enable |
| Testability | **pass** | Matrix separates engineering vs quality; scripted provider allowed |
| Overdesign risk | **watch** | Separate asset_kinds for office is more work but safer than one mega-adapter |
| Underdesign risk | **watch** | If HTML is forced into Markdown `document` adapter without OD, expect sanitizer leaks |
| Paid spend | **pass** | No R803 required for V5-F engineering |
| Residuals honesty | **pass** | internal_preview remains; quality/user value still not_evaluable |

## Findings

### F1 — High if ignored: OD freezes are prerequisites

HTML (OD-B5), Audio (OD-B6), Video (OD-B7) cannot be “just implemented.”  
**Required rework if skipped:** stop and write approved policy text first.

### F2 — Medium: Office surface area

DOCX/XLSX/PPTX are three products. Parallelism is limited; serial slices reduce contract thrash.  
**Mitigation:** freeze DOCX first; extract shared OOXML only after DOCX ACCEPT.

### F3 — Medium: Agent “completion” must not reopen platform OD

Pressure to add free-form agents is expected. Plan explicitly rejects dynamic DAG/tools.  
**Mitigation:** any new step kind / tool = new OD + possible role-I/O version.

### F4 — Medium: ASR dependency

Audio/Video without real ASR capability either blocks or tempts fake adapters.  
**Mitigation:** F-ASR lane before F-AUDIO; fail-closed when unconfigured.

### F5 — Low: README/progress drift

Older README still describes V5-D mid-flight.  
**Mitigation:** update index/progress when decision approved (this package starts that).

## Reverse review (assume failure)

| Failure | Which oracle should catch it |
|---|---|
| HTML XSS via Viewer | sanitizer fixture + browser CSP/render tests |
| Video registered as audio | registry kind + locator codec tests |
| Research cites wrong kind after restore | mixed restore semantic hash + citation open |
| Final artifact rewritten on retry | F5 historical bytes test |
| Embedding mismatch returns empty silently | V5-A embedding index contract tests |
| Agent becomes dynamic | architecture review vs OD-C7 + no new step kinds in diff |

## Go / No-Go

| Item | Status |
|---|---|
| Write specs/plan (this package) | **GO** (done) |
| Implement HTML | **NO-GO** until OD-B5 approved with sanitizer policy |
| Implement DOCX | **GO** after F-G0 owner accept (lowest policy risk after HTML decision) |
| Implement Audio/Video | **NO-GO** until F-ASR + OD-B6/B7 approved |
| Implement agent multi-modal UX | **GO** for document-family first; full multi-modal after audio/video |
| Paid R803 | **NO-GO** (owner deferred) |

## Recommended first implementation slice after approval

1. Approve this decision.  
2. Freeze HTML sanitizer policy (OD-B5).  
3. Implement F-HTML end-to-end.  
4. In parallel (docs/tests only): F-AGENT multi-document Research fixtures.  
5. Then DOCX.
