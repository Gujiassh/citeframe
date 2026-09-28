# #46 correction successor recovery — narrow UI contract R1

Status: **PROPOSED — awaiting the original independent reviewer. No affected product implementation before approval.**

Base: `6ccd8d8a1de7afeb2c8edb0f3f07d0b9cf0a38e8`; current static candidate is `evidence/issue46/c5-static/candidate-manifest.sha256` (`FC9D6CF10AA26DA589AC2428E41BEF00F6A66ED2CB2A0485954A9474D3E89C7F`). This contract supersedes the C5 pending engineering-choice question. Recovery must carry the existing draft; manual retyping/copy-paste is not the recovery mechanism.

## 1. Outcome and existing API boundary

A definitive correction409 keeps the user's exact draft and its original predecessor identity. The user selects a candidate successor, views an authorized comparison, explicitly adopts the verified successor as the edit target, then separately clicks Save. Only that Save may create a new correction request. Success returns another NEW successor ID; no same-ID active-v2 body mutation is assumed.

Use only existing owner-scoped paged list, current, history and exact-source APIs. `AvailableMemory.supersedesId` supplies the backward relationship; names, timestamps, list order, receipt `resultVersion` and error `currentVersion` do not prove a successor or authorize CAS. No API/schema/core/permission/audience changes, private chat/run mode, shared-output injection or persistence are introduced.

## 2. State and ownership

Feature-local state is owned by a recovery hook mounted inside `MemoryManagement`, above target-keyed `MemoryDetail`. Selecting another row must not unmount/discard the editor's draft. It is not stored in the root session provider, Workspace, local/sessionStorage, a module cache or a URL.

State stores: scope epoch + local draft generation; immutable original predecessor ID/version; exact controlled draft `Statement`; last attempted target ID/version; optional chosen candidate ID; bounded verified chain metadata; current comparison projection; adopted target ID/version. Statement includes kind/content and ALL conditions/effectiveFrom/pinned/validUntil fields. Adoption never silently substitutes the candidate's optional fields. No submitted-body logging.

| State | Permitted transition and effect |
|---|---|
| `editing` | Save explicitly submits the current target/version and exact draft; retain draft until a definitive result. |
| `submitting` / `unknown` | Lock draft/target adoption and other writes. Existing session pending command owns immutable method/path/body/requestId/key. Unknown polling/retry remains unchanged. |
| `conflict` | Only a matching definitive correction `version_conflict`/`terminal_memory`409 opens recovery. Original draft and predecessor remain; Save disabled. Ordinary read/transient failures preserve the draft. Generic PATCH409 cannot silently rebind correction state. |
| `checking(candidate)` | User row selection starts bounded authorized reads; hide prior candidate comparison immediately, retain original draft; Save/adoption disabled. No mutation. |
| `compare-ready` | Show original predecessor ID/version, original draft and verified candidate ID/version/current statement distinctly. Existing history/source access remains exact and guarded. No automatic adoption. |
| `rechecking-adoption` | User clicks “继续编辑此后继 / Continue on this successor”; reread/revalidate before changing target. No mutation. |
| `editing-adopted` | Preserve every draft field, atomically change only edit target to verified successor ID/fresh version, leave predecessor identity visible; user may edit and must separately click Save. |
| `cleared` | Clear protected draft/comparisons on the privacy transitions below; no old response may restore them. |

A correction outcome must match the attempted method/path/requestId, scope epoch and draft generation. It cannot be inferred from one global error flag. After definitive409, the failed pending identity is settled; do not allocate the next pair while selecting/comparing/adopting. After success, clear draft/recovery and select receipt successor under the existing validation. `resultVersion` remains separate from current projection version.

Only one correction draft exists in the mounted Memory view. While conflict/comparison is open, disable unrelated create/deactivate/delete actions until cancel or completion; list paging/selection, Refresh and authorized reads remain available. Cancel is an explicit draft discard. Ordinary feature unmount still clears unsent drafts; this contract adds no restart/Home draft durability. Existing unknown-operation Home/Back lifetime is unchanged.

## 3. Exact user sequence and bounded relationship proof

1. A user edits predecessor P. A competing real correction creates Q and supersedes P. Saving the stale draft to `POST /memories/P/corrections` yields definitive409. Keep the draft and P identity; refresh cannot replace its text or automatically resend.
2. The user browses the existing owner list with explicit pages (limit30) and selects candidate C. No automatic pagination/whole-list scan, name match or “latest” selection. Candidate selection alone does not retarget the draft.
3. Read C by exact ID. Require readable `contentAvailable:true`, exact actor/workspace binding, `intent:active`, and not already suppressed by the feature. A stale list row supplies no CAS. Walk backward using each CURRENT readable DTO's exact `supersedesId` until the original P is reached. Require P and intermediates to be readable superseded records, IDs/relationships bound to the requested endpoints, no cycle/repeated ID, no missing link. C=P is not successor recovery.
4. Hard limit: **8 successor edges / 9 distinct current-record GETs per validation**. Stop at the limit or an invalid link; never fall back to guessing, unbounded traversal, history enumeration or a new endpoint. Ordinary failure/no relation/limit exceeded preserves the user's draft but disables adoption. Show a fixed bounded error and allow another explicit candidate choice or cancel. History/source views inform comparison, not chain discovery.
5. On a valid chain, render `compare-ready`. Keep only required identity/version/link metadata for intermediate nodes; discard their semantic bodies immediately. The original/candidate comparison and draft are view-local. The UI says “selected successor”, not globally “latest”; paged reads do not establish global latest/snapshot completeness.
6. On explicit “Continue on this successor”, repeat the bounded proof and then reread C once at the end: **maximum10 current GETs for this adoption action**, no background retry. Compare the proof with what the user saw: IDs/links/versions/intent/availability plus original and candidate statement/source tuples. If anything differs, replace the comparison with the fresh authorized view and require another explicit adoption click. Do not adopt silently. Clear superseded comparison bytes if authorization/readability was lost.
7. If unchanged and valid, atomically retain the draft and install final C.id/C.version as the next target. A separate Save creates a new requestId/key once and sends `POST /memories/C/corrections` with that CAS and the exact current draft. Adoption performs zero POST/PATCH/DELETE calls. No automatic CAS retry.
8. There is no read-side snapshot/lock guarantee. If C changes after adoption or during reads, the actual command CAS/authorization is authoritative. A new409 retains the draft and returns to explicit recovery; no same-ID rewrite, automatic candidate advancement or automatic new request identity. Preserve the original P identity and record the last attempted target separately; subsequent candidates must still prove the bounded chain to P. Exceeding the bound remains an explicit blocked recovery, never a silent traversal expansion.

## 4. Privacy, cancellation and adverse transitions

Privacy clearing below is triggered by an observed authoritative denial/unavailability, not an inferred cross-session event. Existing APIs offer no multi-record snapshot or push notification: a later unseen ancestor change cannot be claimed as detected by candidate CAS. Re-read proof at adoption narrows that window; a subsequent observed denial always clears the protected recovery state. All comparisons and async checks carry scope epoch + draft generation + candidate generation. Abort old work on scope change, candidate change, cancel or unmount; every success/error/finally setter checks captured generation. Clear before rendering a changed actor/workspace/revoked scope. No stale-response flash.

| Counterexample / event | Required behavior |
|---|---|
| Q is superseded again before selection/adoption; user sees stale active row | Current GET rejects Q as an active target. Retain draft, require explicit selection of another candidate; a candidate R can be proved via R→Q→P within the bound. No automatic follow-forward inference. |
| Candidate version/content/link changes during adoption validation | Return to comparison; no target adoption or mutation until another explicit click. Further change after adoption is caught by actual Save CAS; new409 repeats recovery. |
| Same subject on an unrelated record; cycle; null link before P; chain >8 | No adoption; fixed relationship/limit error, genuine draft preserved. Never choose by title/time/order or edit IDs in a fixture to simulate core behavior. |
| Candidate not yet related returns foreign/missing404 | Do not expose candidate content or adopt it. Preserve the separately authorized original draft; clear candidate view. A random unavailable candidate does not authorize discarding another record's draft. |
| Original P, previously adopted target, or a proven comparison-chain participant becomes source-unavailable/erased/not-found | Invalidate that record through existing feature suppression and clear the protected recovery draft/comparisons/selection proof. No copied editor/list/history/source bytes remain; no reappearance from late reads. True erased410 retains only permitted tombstone metadata and cannot be a recovery target. |
| An unreadable intermediate/new candidate supplies no supersedesId | Relationship cannot be established: no adoption; remove its private projection. If it is already a proven recovery participant, apply the preceding privacy-clear rule. Never derive a relationship from the unavailable DTO. |
| Logout, actor/workspace switch, auth/workspace revocation | Synchronous view/draft clear and epoch fencing. Existing session provider clears pending command under its established rules; late checks/mutations/polls cannot restore state. |
| Unknown acknowledgement after Save, including after adoption | Preserve ONLY the original submitted immutable command for existing original-request polling/explicit retry; no selection/adoption/new write. Same request404 does not settle outcome. Home/Back keeps that command under R2. A source-read denial clears draft/comparison views but does not prove an unknown mutation failed: keep the unresolved command internal and never render its body; do not mint a replacement. Scope/auth revocation still clears it. |
| Ordinary503/read failure or definitive409 without readability denial | Preserve exact unsent draft; show fixed error and require user retry/selection/comparison. Do not use privacy clearing to discard a recoverable conflict draft. |

## 5. Affected files after approval only

| File boundary | Small responsibility |
|---|---|
| NEW `lib/memory/correction-recovery.ts` + `.test.ts` | Local state/types and bounded identity/relationship/comparison rules; no API DTO change. |
| NEW `lib/memory/use-correction-recovery.ts` | Scoped draft lifetime, bounded reads, generations and explicit adoption orchestration. |
| NEW `components/memory/memory-recovery.tsx` | Compact original-draft/candidate comparison and explicit adoption action, using existing design. |
| `components/memory/memory-panel.tsx` | Compose recovery hook/view inside existing feature owner and route candidate selection; no shared-shell ownership change. |
| `memory-detail.tsx`, `memory-form.tsx` | Controlled correction draft/target binding; remove duplicate local correction state, preserve full Statement on adoption; source/history invalidation still reaches one feature boundary. |
| `lib/memory/use-memory-management.ts` | Narrow correlated correction-result notification and invalidation wiring; preserve pending protocol and no-store reads. |
| `lib/i18n-context.tsx` | Minimal action/identity/comparison/error keys only. |
| Dedicated memory unit/E2E files | State/chain/race tests and real correction409→explicit successor adoption→new successor save; original regression oracles retained. |

No layout/session-provider/Workspace/auth/BFF/backend/core/schema changes. No changes to other historical manifests or original reviewer files. Exact implementation diff remains reviewable within the original owned feature; this document authorizes no code before original review approval.

## 6. Original-reviewer approval and later evidence

Review this contract for: (a) exact draft carried without retyping/implicit field merge; (b) bounded proof from explicit candidate to original predecessor; (c) read-only comparison/adoption followed by separately explicit mutation; (d) recurrent conflict/privacy/unknown counterexamples above; (e) feature-local ownership and API sufficiency.

After approval, test oracles must capture a real competing correction, stale correctionPOST409, unchanged draft, C→…→P relation, zero writes during comparison/adoption, fresh C CAS and a NEW successor on explicit Save. Add chain/cycle/limit/no-relation, changes between preview/adopt/save, source erasure and late scope/poll regressions. Pure tests and fixtures remain separate from actual API/visible evidence.

Current browser/network/launch/shutdown refusals remain controlling. This contract task runs none of them and grants no permission to retry. Original reviewer must approve exact contract bytes before implementation; controller relays if reviewer is outside this collaboration tree. No UI acceptance or publishing conclusion follows from this proposal. #46/#41 remain open.
