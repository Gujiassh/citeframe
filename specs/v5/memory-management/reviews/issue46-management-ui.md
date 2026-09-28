# Issue #46 management UI — independent Critical review

## C6 — successor-recovery implementation recheck (2026-09-29, 00:46 +08:00)

**PASS at inspected code/static/pure-local-unit scope. No new blocking implementation finding in this bounded review; no C6 rework requested on the executed evidence. Browser/component integration, real API recovery, visible usability, build and full #46 acceptance remain pending.** The React hook was additionally exercised with dependency doubles, not a real React renderer or browser. This disposition must not be described as a usable or completed feature.

### Exact candidate / ownership

- `evidence/issue46/c6-successor/candidate-manifest.sha256` independently hashes to **60E1DFC70C24E47538C59424E2210F80B7E3B7A156C8957CDF06ED28839D06AC**; **41/41 hashes match before and after review/testing**.
- Approved contract remains exact **7B3E17EBB977CEFF298EAD762C8BCF49111E989075D404CE47603F81D55E8BFA**. Governing oracle is selection at most9 actual GETs/9 distinct records/8 edges; adoption at most10 actual GETs/9 distinct records/8 edges, including final fresh C.
- Exactly11 paths differ from frozen C5: four new recovery rule/test/hook/view files; panel/detail/form/management-hook/i18n; both memory E2E definitions. Verified no layout/provider/session-state/BFF/client/DTO/backend delta within the manifests. Read C6 README and recorded commands; no runtime/credential file was opened.

### Actual implementation judgments

| Invariant | Inspected implementation / direct local evidence |
|---|---|
| One complete draft above keyed detail | `useCorrectionRecovery` is composed inside existing `MemoryManagement`; keyed detail no longer owns correction editor state. `MemoryForm` accepts a controlled Statement and copies changed fields without substituting candidate metadata. EffectiveFrom/pinned/validUntil are preserved and displayed in the draft and comparison. Independent hook-double flow deliberately changes all optional values in the candidate; adopted draft remains byte/value-equivalent and the later submitted body retains the original edited Statement. |
| Separate identities and correlated409 | Recovery separates original P, target, lastAttempted, attempted request/path/generation and chosen candidate. `notifyCorrection` emits only correction POST outcomes. `correctionOutcome` rejects mismatched epoch, generation, method/path/requestId; a matching version_conflict/terminal_memory opens recovery. Global read/PATCH errors do not rebind it. Existing pure tests plus original reviewer target-binding assertions pass against current source. |
| Explicit relationship and bounded reads | `proveSuccessor` follows exact supersedesId backwards, requires active C and superseded ancestors/P, rejects same identity/repeats/cycles/null links/incorrect intent, and stops before a tenth distinct read. The hook wraps reads in endpoint/owner/workspace DTO validation and readability/suppression checks. No list scanning, guessed latest target or new endpoint exists. Intermediate proof nodes contain metadata only. |
| Adoption and changed projections | `recheckSuccessor` repeats bounded proof then rereads C; validates final identity/active intent/link. Equality covers nodes, original/candidate complete Statement and exact source tuples. Changed authorized projection returns compare-ready with a changed error; changed final link rejects proof without chasing it. Pure budget tests pass at exactly9 selection and10 adoption calls, with9 distinct records; over-limit stops at9. |
| No mutation until separate Save | Choose/adopt only perform reads and state updates. On unchanged adoption only target ID/version changes. `submit` later calls the existing mutation preparation once with the full draft and target CAS. Independent hook-double checks assert no write during preview/adopt, then a second explicit POST to Q/corrections, fresh Q CAS1 and new requestId/key. No same-ID body rewrite was introduced. |
| Recurrent conflict | After a Q-target409, original P and full draft survive; explicit R selection proves R→Q→P, and explicit adoption selects R. Independent hook-double recurrence passed without an automatic mutation or resetting the original-predecessor anchor. |
| List and participant privacy | Existing list ingestion populates `unavailable`; recovery's render-time participant check consumes it as well as explicit current/history/source invalidation. Participant IDs retain original, current target and proven ancestors. Loss aborts work, hides recovery immediately and clears selected comparison where needed. Hook-double tests cover original loss while adoption is held, proven intermediate loss through list DTO, and proven candidate loss after unknown Save. Late successful read cannot restore the cleared draft. |
| Unrelated candidate failure | An unrelated/unproven missing candidate is invalidated but does not join the protected participant set. The draft stays intact and adoption remains blocked; another explicit valid candidate can be checked. Independent404 probe passes this exact preserve-versus-clear distinction. |
| Unknown original identity | Existing session provider/client preparation remain unchanged. New hook preserves attempted identity in unknown state and locks selection/adoption/new writes. Source loss clears recovery views without clearing the externally owned unresolved command. The dependency-double probe retained the identical pending object; unchanged client/session pure units still verify exact body/key/requestId and Home/Back helper behavior. Actual Home/Back rendering/polling was not run. |
| Detail/history/source and stale work | Managed proof projections suppress duplicate automatic current GETs in `MemoryDetail`; explicit exact-source/history reads retain existing invalidation paths. Projection/revision/lifetime changes abort old reads and clear secondary views. Recovery checks use epoch/draft/candidate generations plus controller identity; cancelled/replaced checks cannot commit old proof. Independent held-candidate/cancel/replacement probes pass. Full detail-to-hook DOM/lifecycle behavior remains an unexecuted integration gate. |
| Scope/auth boundaries | Existing actor/workspace/epoch keyed owner and provider revocation behavior remain unchanged. Recovery adds no persistent/global private store, body logging, client authority, shared-output reuse or new permission surface. Browser-level logout/revocation rendering is not claimed from this static/pure review. |

The approved participation/readability limits remain: observed authoritative denial clears protected state; no claim of unseen ancestor-change detection, multi-record snapshot or cross-session push invalidation is made. Candidate Save still relies on authoritative API CAS/auth for races after adoption.

### Independently executed evidence

| Evidence class | Result |
|---|---|
| Whole-web strict TypeScript | **exit0**, `node apps/web/node_modules/typescript/bin/tsc --noEmit --incremental false -p apps/web/tsconfig.json`; no E2E exclusion, separate unresolved-identifier/import check |
| Whole source/E2E/scripts/config ESLint | **exit0**, from apps/web: `node node_modules/eslint/bin/eslint.js src e2e scripts next.config.ts playwright.config.ts eslint.config.mjs postcss.config.mjs` |
| Current feature unit suites | **40/40 pass**, including all11 recovery tests |
| Original reviewer helper assertions | **4/4 pass**, current source; combined current-suite run **44/44**, exit0 |
| Additional reviewer hook-orchestration dependency-double probes | **8/8 pass**, exit0; cases below |
| Intercepted browser E2E | **Not executed**; definitions inspected only |
| Live browser / actual BFF/API / PostgreSQL / network | **Not executed**; no actual running evidence added |
| Production build | **Not run / not accepted**; previous Geist/Geist Mono fetch failure remains |

All pure tests loaded fresh current TypeScript in memory using local TypeScript `transpileModule` with CommonJS output. Original reviewer helper imports were redirected in memory to current source, avoiding stale compiled C3 code. Default global fetch was replaced with a throwing no-network function; feature units used injected/in-process responses. The separate whole-web tsc check supplies type validation for this transpilation-based run. No compiled output, test file or scratch log was written; execution results are in the tool transcript.

The eight added probes loaded the actual `use-correction-recovery.ts` with local state/ref/effect/session/client doubles and deterministic rerender/microtask flushing:

1. Complete optional draft survives a changed comparison and another explicit adoption; no mutation until separate Save; new Q path/CAS/requestId/key asserted.
2. Recurrent correction conflict retains original P and draft, then explicitly checks/adopts R through Q.
3. Authoritative original-participant list loss aborts a held adoption; late body cannot restore recovery.
4. Unrelated candidate404 preserves draft and permits a later explicit valid selection.
5. Proven candidate source loss clears views during unknown outcome while retaining the same pending command object.
6. Cancel fences a held candidate response; no resurrection or write.
7. New candidate selection fences an old held candidate response; no stale proof/error replacement.
8. Proven intermediate unavailable list projection clears draft/proof/selection.

**Harness limit:** these exercise hook code and its callbacks with dependency doubles. They do not execute React reconciliation/effect scheduling, the actual provider, DOM controls, native navigation, BFF transport or authorization. They support the local state judgment and cannot replace the authored browser races or real signed-session workflow.

### Test-only definitions and remaining acceptance

Static inspection of the changed E2Es confirms the successor scenario now uses a competing correction creating a distinct Q, a stale correction POST409 to P, retained draft, explicit selected-successor comparison/adoption, zero intervening memory writes, then separate Save to Q yielding another distinct successor. The live definition also adds exact predecessor revision/source checks and current/history/source refusal after predecessor deletion. Intercepted definitions include full optional values, recurrent conflicts, unrelated/foreign/cyclic/terminal candidates, list/detail/history/source loss, held-read races,9/10 call counts and predecessor reads that do not retarget the draft.

**None of those browser assertions ran in this review, and the C6 handoff explicitly reports them unexecuted.** C3's previously executed browser results do not validate the new C6 component composition. Existing live unknown-navigation/revocation definitions remain test-only here. Real owner/member permission isolation, committed-lost-ack recovery, complete visible draft/compare/adopt/save behavior, actual request counts and mobile/accessibility/readability still require permitted execution against the integrated API.

### Original-developer handoff / scope

No new C6 code/static/pure-unit correction is requested of the original developer on this evidence. Preserve the exact reviewed candidate for later original-reviewer component/runtime validation; any rework remains with that same developer. Do not mark the feature usable, close #46/#41, or convert the local pass into API/UI acceptance. Later compaction/continuation/end-to-end work remains open.

Only this original review artifact was written. Frozen product41-file hashes were rechecked after testing, with0 mismatches. No product/test/scratch/Git/model/private-memory/shared-workbench write. No browser, CDP, Playwright, HTTP readiness, service/proxy start/stop, credential access or denied-operation workaround occurred. Runtime restrictions remain controlling. Write-back check: this artifact records the verified local results and limits without a duplicate profile-memory entry.

---
## Successor-recovery contract R1 — exact implementation-scope approval (2026-09-29, 00:06 +08:00)

**APPROVED FOR LOCAL FEATURE IMPLEMENTATION** against exact contract `lanes/issue46-successor-recovery.md`, SHA256 **7B3E17EBB977CEFF298EAD762C8BCF49111E989075D404CE47603F81D55E8BFA**. **M46-SR1 is closed by the controller's explicit engineering-budget grant.** No other design blocker remains from this review. This grants the contract's bounded feature implementation scope only; it does not accept implemented behavior, runtime integration, UI usability, production build or full #46 completion.

### Governing request-count oracle

The controller has explicitly approved the original §3.6 semantics. The numerical ceiling is a controller-selected engineering boundary, not an end-user requirement imposing9 requests on adoption. This clarification supersedes the earlier ceiling interpretation and alternative traversal recommendation below; the contract bytes need no amendment for SR1.

- **Candidate-selection validation:** at most **8 successor edges**, **9 distinct records**, **9 actual current-record GET requests**.
- **Each explicit adoption action:** repeat the bounded proof and retain the final fresh C read; at most **10 actual current-record GET requests** over at most **9 distinct records**, with the same **8-edge** chain ceiling. The repeated C read consumes a request even though it adds no distinct record.
- No extra chain depth, automatic retry, extra follow-link traversal, automatic list scan, or new API/permission is authorized. The tenth-request allowance is for the stipulated final C read; it does not permit a tenth distinct node or another edge.
- Selection/comparison/adoption perform no mutation and allocate no new mutation identity. Only the later explicit Save submits the preserved draft to the adopted target using fresh CAS and one new requestId/key. An existing unknown command continues original-identity reconciliation and cannot be redirected.

Reverified the contract hash above and frozen C5 manifest **FC9D6CF10AA26DA589AC2428E41BEF00F6A66ED2CB2A0485954A9474D3E89C7F**: **37/37 files still match**, with no product implementation change observed at this approval checkpoint.

### Scope and retained obligations

Implementation may proceed within contract §5: new feature-local recovery rules/tests, hook and compact comparison view; narrow panel/detail/form, correlated mutation-result/invalidation, minimal i18n and dedicated test changes. No layout/session-provider/Workspace/auth/BFF/backend/core/schema ownership expansion is granted.

All other preceding design judgments and adverse oracles remain operative, including:

- Full exact Statement preservation and explicit comparison of optional fields; separate original predecessor, attempted target, selected candidate and adopted target.
- Matching correction outcome/path/requestId/scope/draft-generation correlation; recurring409 returns to explicit bounded recovery to the original P.
- Fresh authorized relationship/readability/content/source revalidation, another explicit comparison/adoption after changes, and final fresh C read before installing target/CAS.
- Authoritative participant unavailability observed through **list ingestion as well as detail/history/source invalidation** clears protected recovery state. Unrelated candidate404 preserves the independently authorized original draft.
- Synchronous scope/logout/revocation clearing, generation fencing, terminal410 nonresurrection, and unresolved-command privacy/identity handling.
- Boundary tests must now assert **selection9 / adoption10 actual requests**, at most9 distinct records and8 edges, including no mutation during adoption and no retries/scans beyond those limits.

**Original-developer handoff:** the exact7B3E17EB contract is approved for this local feature implementation. The earlier instruction to wait for a revised contract hash is superseded. Return the implemented candidate and evidence to the same reviewer; do not generalize this design approval into running acceptance. C3 R1–R5 and the bounded C4 conclusions are unchanged.

Only this original review artifact was written. No product/test/scratch/Git/private-memory/shared-workbench/model write or runtime action. Browser/network/exec launch/shutdown refusals remain in force; this approval grants no retry or bypass permission. Real API/visible workflow evidence is still missing, production build remains at the last known font-fetch failure, and #46/#41/later compaction/continuation remain open. Write-back check: the verified decision and scope are recorded here.

---
## Successor-recovery contract R1 — original independent design review (2026-09-29, 00:01 +08:00)

**EXACT CONTRACT APPROVAL WITHHELD: one bounded-request-budget discrepancy, M46-SR1 below. The recovery architecture, existing API sufficiency and proposed feature-local file boundary are implementable at design/static scope. Resolve the exact GET ceiling before implementing the affected recovery contract; no backend/provider expansion is needed. This is not an implementation or runtime acceptance. C3 R1–R5 and the bounded C4 activation disposition remain unchanged.**

### Reviewed identities and actual baseline

- Contract: `lanes/issue46-successor-recovery.md`, independently verified SHA256 **7B3E17EBB977CEFF298EAD762C8BCF49111E989075D404CE47603F81D55E8BFA**.
- Frozen C5: `evidence/issue46/c5-static/candidate-manifest.sha256`, independently verified SHA256 **FC9D6CF10AA26DA589AC2428E41BEF00F6A66ED2CB2A0485954A9474D3E89C7F**; **37/37 current file hashes match**. This is a design review against those bytes, not approval of the whole C5 live-test candidate.
- Read current `memory-panel`, `memory-detail`, `memory-form`, `use-memory-management`, Statement/DTO types and record renderer. Rechecked integrated API service/core/query source; applicable web AGENTS and installed Next16 Client Component/context-placement guidance remain satisfied. No network/server/browser/runtime operation was performed.

Current code explains why the recovery needs the proposed narrow change:

1. `memory-panel.tsx:52` keys `MemoryDetail` by selected ID. `memory-detail.tsx` holds `edit` locally and `memory-form.tsx:10–13` holds the editable fields locally. Selecting another row currently unmounts that draft. Moving the single correction draft above the keyed detail is necessary; moving it into the root/session provider is unnecessary.
2. Current comparison only offers `setEdit(current)` for a readable **active same-ID** head with a new version. Integrated `commands.py:170–173` checks stale CAS then terminal state; correction subsequently appends a superseded predecessor and creates a NEW record with the backward supersedes link. Refreshing the real predecessor therefore cannot make the old same-ID fixture into a successful correction-resave workflow.
3. `memory-form.tsx:17` currently takes effectiveFrom/pinned/validUntil from `original` at submission, while content/kind/subject/applicability live in controlled state. Merely replacing `original` with a candidate could silently replace optional fields. The contract correctly requires an independent complete Statement draft and explicit full-field comparison; changing only the target/version must not replace draft metadata.
4. `memory-panel.tsx:52` currently derives conflict from a shared error flag, and `use-memory-management.ts:83–101` clears definitive pending failures without a correction-specific result event. The proposed correlated result notification is necessary to distinguish correction POST409 from PATCH errors, read failures, older drafts and settled requests.
5. Current list ingestion (`use-memory-management.ts:59`) also records authoritative unavailability, separately from `invalidate`. Recovery clearing must observe both paths, plus detail/history/exact-source failures. Wiring only the detail callback would leave the proposed participant-privacy rule incomplete. This is an implementation obligation already covered by the contract's invalidation/clearing boundary, not a reason to modify backend or provider ownership.

### M46-SR1 — P2: adoption request budget exceeds the latest specified ceiling

**Contract locations:** §3.4 line39 and §3.6 line41.

The latest controller instruction says at most **8 edges / 9 GETs**. Line39 gives8 edges /9 distinct current-record GETs for validation. Line41 explicitly repeats that proof and rereads C, allowing **10 GETs for one adoption action**. At the supported eight-edge boundary, `C → N7 → … → N1 → P` consumes9 calls, then the final C read is call10. Nine distinct identities do not mean nine requests.

This is an explicit budget discrepancy, not an observed security leak or a request for a larger architecture. The reviewer cannot silently approve10 under a9-request instruction. The exact proposed hash is therefore not yet authorized for affected implementation.

**Smallest resolution consistent with the9-GET ceiling:** keep the candidate-selection proof at at most8 edges/9 current GETs. At adoption, use the already verified bounded identity path and reread its nodes in reverse order, **P first and C last**, each once; validate every fresh child.supersedesId against the preceding expected parent, plus authorized identity, readability, lifecycle/version and comparison tuples. C's final read supplies the fresh target/CAS. Reject changed/missing relationships rather than chasing replacement links or doing a tenth automatic read. Valid but changed authorized projections return to explicit comparison; invalid/denied projections follow the existing failure/privacy rules. This permits a final fresh C read within9 requests without inventing a snapshot guarantee.

Alternatively, if the controller intentionally wants9 proof GETs plus one additional final C GET, obtain an explicit revised10-request adoption limit and align the contract/oracles. That change is not inferred from the current instruction. In either resolution, count actual invocations, not distinct IDs; no automatic retries, duplicate recovery/detail fetches hidden outside the count, or pagination/scan fallback to escape the bound. Return revised contract bytes/hash to the same reviewer.

### Bounded design judgments retained independently of SR1

| Area | Judgment / implementation obligation |
|---|---|
| Draft lifetime and state | Proposed hook within `MemoryManagement`, above keyed detail and inside the existing actor/workspace/epoch scope, is sufficient. Separate immutable original P identity, mutable exact draft, last attempted target, chosen candidate and adopted target. Candidate selection is not target adoption. Ordinary view unmount clears unsent drafts; unknown command Home/Back lifetime remains in the existing provider. |
| Outcome correlation | Only the matching correction POST/path/requestId/scope/draft generation can enter correction recovery on definitive version_conflict/terminal_memory409. Capture operation identity before clearing pending; do not infer it later from global error state. A PATCH409, old completion, read failure or operation_not_found poll must not rebind a draft. |
| Existing API / relationship proof | Readable current DTOs expose exact backward `supersedesId`; owner/workspace and endpoint-ID checks remain in the existing BFF/API. Candidate must be active/readable/not suppressed; P and intermediates must be readable superseded records. No relation can be recovered from unavailable DTOs. Exact IDs and links, not names/updatedAt/list ordering/resultVersion/error currentVersion, prove the selected chain. No forward/latest endpoint is required. |
| Recurrent conflict | If Q became superseded, its current GET cannot authorize adoption. User explicitly selects R and proves R→Q→P. After an adopted target loses another race, keep the same full draft and immutable original P, record the last attempted target, and repeat explicit recovery to P within the fixed bound. Do not restart the bound from a newer intermediate to evade the maximum. |
| Readability and content changes | Candidate/original statement and complete source tuples must be compared in addition to IDs/links/version/intent/availability. An unchanged version alone does not establish unchanged present source readability. Authorized change requires fresh comparison and another click; denial for P/adopted/proven participants clears protected recovery state. Unrelated candidate404 clears that candidate view while preserving the independently authorized original draft. |
| Optional Statement fidelity | Preserve and compare kind, content, subject, applicability, effectiveFrom, pinned and validUntil, including explicit null/false values and exact Unicode text. Candidate metadata is never an implicit merge source. Existing `MemoryRecord` omits optional-field comparison, so the new compact recovery view must render them explicitly where needed; it does not require new pin/expiry editing controls. |
| Adoption versus Save | Selection/proof/comparison/adoption allocate no new request pair and perform no mutation. Adoption atomically changes only target ID/fresh CAS. A separately clicked Save allocates one new requestId/key and submits the preserved current draft to that target's corrections endpoint. Success selects the new receipt successor, not a rewritten predecessor. |
| Unknown result | An uncertain original or adopted-target command retains its exact original path/body/key/requestId. It cannot be moved to a selected successor. Poll404 remains inconclusive. A content/source denial clears visible draft/comparisons but retains the unresolved command internally for original-pair reconciliation; scope/auth revocation retains its established pending-clear behavior. No command body is reconstructed into a new editor after denial. |
| Privacy/race fencing | Scope epoch, draft generation and candidate generation fence success/error/finally; cancellation/candidate replacement/unmount abort work. Synchronous scope change clears views before render. Observed participant suppression from list/current/history/source must clear all recovery projections and fence late responses. No multi-record snapshot, push erasure detection, or ancestor-change detection by candidate CAS is claimed. |

No additional architectural blocker was found in the exact contract's state, privacy or existing-API plan. These are design judgments; the recovery hook/component does not yet exist in the frozen product and no behavior is reported as executed.

### Required bounded implementation oracles

Use pure rules/state tests and intercepted component tests first, labeled separately from later authorized actual API/visible evidence:

- Realistic lineage: P→Q correction, stale correction POST to P409, exact draft retained; explicit select Q/compare/adopt yields **zero mutations**, separate Save to Q produces NEW R with fresh Q CAS/new pair. Repeat with R superseded before adoption or before Save. Never simulate success by changing P's active body in place.
- Bounds: one edge, exactly8 edges, ninth edge rejected before extra fetch; cycle/self/repeated ID, null/missing link, unrelated same-subject record, wrong endpoint ID/actor/workspace, unreadable intermediate. Assert request counts at both preview and adoption under the reconciled limit.
- Full draft: all optional values differ between draft and candidate; verify displayed comparison and unchanged draft after adoption. Refresh/reselection/cancel/new-draft generations must not silently exchange fields. Preserve whitespace/Unicode and explicit null/false.
- Recheck races: mutate candidate version/link/statement/source tuple between preview and adoption; active→inactive/superseded; source unavailability with no version increment; P or proven intermediate410; failed current GET. No silent adoption, no mutation, correct preserve-versus-clear behavior.
- Correlation: PATCH409, nonmatching request/path, stale draft completion, old candidate success/error/finally, duplicate adoption click, scope/logout/revoke during each check, late mutation/poll. One generation's callback cannot update another draft/target.
- Unknown after adopted Save: exact original submitted pair through retry/poll/HomeBack; adoption/new writes locked; read denial clears visible semantic state without falsely settling unknown; auth/scope revocation clears and fences pending under R2.
- Regression: retain R1–R5 suppression/body-free lifecycle/history and original identity oracles; ordinary unavailable unrelated candidate must not erase a genuine conflict draft.

The same scenarios still need the permitted real BFF/API chain and visible workflow after implementation and restored runtime authorization. No test count can substitute for that outcome.

### Minimal ownership / handoff

The §5 boundaries are adequate: new pure recovery rules/tests, feature hook and compact recovery view; narrow edits to panel/detail/form, correlated mutation-result and invalidation wiring in `use-memory-management`, minimal i18n, dedicated tests. Remove superseded duplicate local correction state rather than leaving two draft owners. Do not enlarge layout/session-provider/Workspace/auth/BFF/backend/core/schema ownership. Keep proof orchestration cohesive and capped; no generic graph crawler, new cache, persistence or discovery service.

**Return to original developer/controller:** resolve SR1's9-versus10 request ceiling in the contract and resubmit its exact hash. No affected successor-recovery implementation is approved by this review yet. The reviewed architecture/file boundary can be retained; this finding does not reopen unrelated accepted C3/C4 work.

Only this original review was written. Product and the37-file C5 manifest were read-only. No unit/TS/build rerun was needed to adjudicate this unimplemented design; no new runtime claims. Browser/network/exec launch/shutdown refusals remain in force and were not retried or bypassed. Actual recovery acceptance, production build (last known Google Fonts failure), full #46/#41 and later compaction/continuation remain open. Write-back check: this artifact records the durable decision; no private-memory/shared-workbench/scratch/Git/model write.

---
## C4 — activation checkpoint, code/static/pure-unit recheck (2026-09-28, 23:24 +08:00)

**PASS for the inspected activation code/static/pure-unit delta only. No new blocking product-code finding in this bounded recheck. C3 R1–R5 dispositions are retained. This is not usability, real integration, browser, production-build or full #46 acceptance. The concurrently edited live E2E supplement is not accepted by this checkpoint.**

### Identity and review boundary

- Checkpoint manifest `evidence/issue46/c4/checkpoint-manifest.sha256` hashes to **78280352E9AF9FD58D594DA2F31E69C2C2BD9C573F5DA5243CC96BC0174493BB**. At inspection start, **37/37 files matched**. Read-only `git rev-parse HEAD` independently returned **6ccd8d8a1de7afeb2c8edb0f3f07d0b9cf0a38e8**, the integrated PR50 base.
- Four files differ from C3: `lib/memory/activation.ts`, `lib/memory/proxy.test.ts`, `e2e/memory-management.spec.ts`, and new `e2e/memory-management-live.spec.ts`. The sole production delta is the activation constant/comment; provider, hook, forms, BFF/auth implementation, response validation and layout retain C3 bytes.
- During this review the original developer began the announced live-test supplement. At final check, **36/37 entries still match**; only `e2e/memory-management-live.spec.ts` differs. The manifest file itself is unchanged. This review's static observations of that file refer to the initially matching checkpoint content; later work requires a new manifest and recheck. No assertion of a final frozen37-file working tree is made.
- Governing lane contract currently hashes to **AF82373EB17AE00C5EC24D0BBEB9E19ED40297205263A699DC5BE4D96804AAC7**. Inspected actual lane-local integrated API router, strict schemas, service composition and relevant core command paths, as static corroboration of the consumer contract. Upstream API/PG/CI acceptance remains controller-reported, not newly executed here.
- Read `apps/web/AGENTS.md` and relevant installed Next16 Route Handler/BFF documentation again. Public Route Handlers still require server authentication; activation changes no such boundary.

### Activation / actual API contract checks

| Area | Current-code judgment and evidence scope |
|---|---|
| Create/correct activation | `memoryAdmissionEnabled=true` is consumed by the existing form and BFF gate. Actual mounted POST create/corrections routes return201 with MutationReceipt/CorrectionReceipt. UI create sends workspace scope, empty sourceRefs, exact statement/conditions and runtime requestId; correction sends expectedVersion plus statement and no client source/authority claims. API service supplies server-only management/private context and invokes shared remember/correct commands. No new admission implementation or unsupported active/pin/expiry/search/index control was added. |
| Trusted actor / private data | `server-route.ts` still takes the signed server session and server-built API headers. Client actor/token/authorization headers are not forwarded. Body/query allowlists remain active after activation; available receipt validation checks workspace/owner. Explicit unit attacks against both newly enabled endpoints rejected forged authority/unsupported scope/source fields and foreign owner/workspace success projections without returning semantic bytes. Upstream API ownership/revocation is corroborated statically; real session/BFF/API enforcement is still unverified by this review. |
| CAS and correction identity | Correction body preserves expectedVersion; actual core checks current version and terminal state, creates a distinct successor and supersedes the predecessor. BFF validates201, successor/predecessor correlation and current authorized projection. Ordinary definitive409 releases the failed pending operation while retaining draft; explicit comparison updates version without replacing controlled form text. These existing mechanisms are unchanged. |
| Unknown acknowledgement / replay | Both enabled POSTs use the same immutable runtime requestId/key/path/method/serialized-body mechanism as C3. Mocked failures produce one upstream attempt per explicit invocation, sanitized503 outcome_unknown with the original ID, no automatic resend/new pair. Additional pure-unit probes pass the same operation object through Home/Back session alignment and explicitly retry the identical body/key, including correction CAS7. This is helper/state evidence, not browser-navigation or durable-commit evidence. |
| Polling / present projection | Existing polling uses the retained requestId; operation404 does not prove rollback. Content-free operation DTO validation, resultVersion/currentVersion distinction, current authorized resource refresh and scope/epoch fences remain unchanged. API operation projection statically reads the present head; no historical receipt body is treated as current state. |
| Private state and logging | Activation adds no persistence, global private cache, console logging, shared-chat consumer or model call. Existing private/no-store BFF responses and no-store fetch behavior remain intact. Unresolved POST body lifetime remains scoped runtime memory only. |

### E2E source observations — unexecuted in this review

The initially matching live test uses normal sign-in and workspace → Settings → Memory navigation, separate browser contexts for owner/member/other, and signed-context BFF requests for concurrent mutation and cross-owner denial. It contains no intercepted-response fallback. `MEMORY_LIVE=1` gates execution; trace/video/automatic screenshots are disabled and explicit screenshots are post-auth. The inspected network recorder stores actor labels/method/path/status rather than authentication headers, credentials or submitted bodies. No credential/runtime configuration file was read by this reviewer.

The checkpoint authors lifecycle/source, successful correction, member-own creation, cross-owner404, a real concurrent PATCH409 with retained correction draft, deletion410 and list tombstone checks. These are authored assertions, not executed evidence. Specific limits remain:

- The live409 scenario is a stale **Deactivate PATCH**, followed by retained draft, refresh and disabled Save on an inactive head. It does not exercise a failed correction POST followed by a successful resave.
- The new intercepted correction fixture returns an active same-ID version2 with changed wording before a successor save. The actual integrated correct command creates a new identity and supersedes the old one; that fixture tests component comparison mechanics and cannot establish the real API's concurrent-correction transition. Preserve this distinction in any later acceptance report.
- The checkpoint live history assertion checks successor-history visibility; it does not assert exact predecessor revision contents/source identity across correction or body-free history/source denial after deletion. Such runtime fidelity evidence remains outstanding.
- Live unknown Home/Back and revocation-race supplements were explicitly unfinished and are being edited by the original developer. They are excluded from this disposition. Do not infer their behavior from the checkpoint or C3 fixtures.

These are evidence-scope limits for the checkpoint, not invented live failures. No live request, browser action or API race was attempted here.

### Independently executed local evidence

| Check | Result / limits |
|---|---|
| Initial whole-web TypeScript | `node apps/web/node_modules/typescript/bin/tsc --noEmit --incremental false -p apps/web/tsconfig.json` exited0. The subsequent live-file edit means this is not a final all-files freeze check. |
| Current stable-source TypeScript | Pure in-memory TypeScript program from the same tsconfig, excluding only the concurrently edited `e2e/memory-management-live.spec.ts`, noEmit/incremental false: **0 diagnostics**, exit0. Includes unresolved identifiers/imports; no output files written. |
| Whole-web ESLint attempt | Exit1: parser error at live spec line17, `';' expected`, while that file was being edited (malformed BOM-stripping expression). This observation belongs to the nonfrozen supplement, not the initially matching checkpoint. Reviewer did not modify it or adjudicate the unfinished work as a final candidate. |
| Stable-source ESLint | Same full source/E2E/scripts/config command with `--ignore-pattern e2e/memory-management-live.spec.ts`: exit0. No claim of final full-suite lint pass. |
| Current unit/helper suites | **33/33 pass**: 29 current feature tests plus the four unchanged original reviewer R3/R4 assertions. Source transpiled in memory; stale C3 compiled JS was not reused. |
| Additional activation adverse units | **6/6 pass**: for each of create/correct, exact unresolved POST identity/body/key across pure Home/Back state alignment; authority/query/CAS rejection before upstream; foreign owner/workspace receipt suppression. Combined Node result **39/39**, exit0. |
| Browser / real HTTP / API / PostgreSQL | **Not run.** No Playwright invocation, browser/CDP/HTTP fallback, service/proxy launch or readiness request. |
| Production build | **Not run; remains unaccepted.** Last C3 evidence is the Google Geist/Geist Mono font-fetch failure. |

Units were executed with a PowerShell stdin Node harness: a local TypeScript `transpileModule` CommonJS `.ts` loader; current `validation`, `proxy`, `client`, `response`, `session-state`, `body-free` test modules; original reviewer assertion imports redirected in memory to current source; six added in-memory activation assertions. Global fetch default was replaced with a throwing no-network function; tests used injected/mock fetches and standard in-memory Request/Response objects. No network, DB or server module was invoked. Harnesses, build output, logs and product/test files were not written; the tool execution transcript holds the39-pass output.

The stable-source lint invocation, from `apps/web`, was:

```powershell
node node_modules/eslint/bin/eslint.js src e2e scripts next.config.ts playwright.config.ts eslint.config.mjs postcss.config.mjs --ignore-pattern e2e/memory-management-live.spec.ts
```

Developer-reported C4 **27/27 intercepted-browser** passes occurred before the denial; they were not independently rerun in this review and do not count as real API/browser acceptance.

### Remaining gate / original-developer handoff

Activation product delta has no new code/static/unit blocker within this review. **No usable/complete/real-integration disposition is granted.** The reported localhost3246 browser-security denial and exec proxy-start rejection remain controlling boundaries. No alternative browser, CDP, Playwright, direct HTTP, proxy or launch syntax was used to bypass either refusal. Controller must resolve runtime authorization before any real-path continuation.

The signed-cookie → Next BFF → actual API → PostgreSQL chain, actual owner/member privacy, real committed-lost-ack recovery, visible draft/CAS behavior, source/history fidelity and permanent erasure still lack this lane's real running evidence. Await the original developer's finished live supplement and replacement manifest; then review those bytes and, only after permission is restored, separately adjudicate actual network/manual workflow/screenshots. Production build and full #46/#41, later compaction/continuation remain open.

Only this original review artifact was written. No product/test/scratch, Git, model, credential, private MEMORY, shared-workbench or old-tree write. Write-back check: durable scope/results/limits are recorded here; no duplicate profile-memory entry. C3 findings remain closed at their prior scope; this C4 checkpoint does not enlarge those acceptance claims.

---
## C3 — original-reviewer R5 recheck (2026-09-28, 22:41 +08:00)

**PASS for the frozen C3 code/static/fixture slice. M46-R5 is closed; M46-R1–R4 remain closed at their recorded scope. No new blocking finding in this targeted recheck. Actual integrated API, visible-browser usability, production build and full #46 acceptance remain open.**

The reviewed user outcome is continued authorized management of an owned nondeleted record when its semantic content is unavailable: safe Delete/Deactivate/history, current-version CAS, no restoration of old private bytes and no resurrection after terminal erasure. This disposition covers the inspected implementation and executed synthetic interleavings. It does not establish real owner isolation or a completed live user workflow.

### Frozen scope and prerequisite evidence

- Manifest `evidence/issue46/c3/candidate-manifest.sha256` independently hashes to **F22DBC12D98C4CC1D6022B1A5428D898019D1BCD9921AAE31590F607575C8CE8**; **36/36 listed files match**, including the final post-test check.
- Exactly six product/test files differ from C2: `memory-detail.tsx`, `memory-panel.tsx`, `use-memory-management.ts`, new `body-free.ts` and its unit test, and `e2e/memory-management.spec.ts`. Provider/layout, BFF, activation and contract are unchanged. Base remains the recorded `9cd93ec1aa70ea803401a88c55834de1593f0aeb`.
- Governing contract remains `lanes/issue42-management.md`, SHA256 `2EBF5D6BD9A9C298D21253C50A9ECAA869AD9AC2A437BFEDF354BF0A961F2802`, with full v4/A1 context from the original review. Rechecked the current/history/unavailable DTO, lifecycle/CAS, exact-source and erasure clauses against C3.
- `apps/web/AGENTS.md` and installed Next16 docs prerequisite remains satisfied. Provider/pathname guidance was reread; prior BFF/route/auth/fetch guidance and provider-placement review remain applicable. The approved one-import/provider layout placement is unchanged. `memoryAdmissionEnabled=false` is verified in current source.

### M46-R5 closure and retained protections

| Invariant | Inspected implementation and independent runtime evidence |
|---|---|
| Body-free lifecycle management | `MemoryDetail` renders current identity/version/intent/validity/display metadata without requiring readable content. Delete is available for nondeleted current records; Deactivate requires current active intent. Both unchanged original active/inactive R5 Delete fixtures pass with expectedVersion2. |
| Fresh current CAS | Source/history-only unavailability removes copied editor/current/source semantics, then fetches current metadata before offering lifecycle actions. Current state and historical page are separate. Developer probes independently rerun with history version2/current version8 and inactive head9; outgoing Delete uses8/9. Source-failure fresh current7 uses7. Reviewer reselection probe advances head7 to11 while list remains stale version1 and history is2; outgoing PATCH uses11. |
| Safe history projection | `bodyFree` explicitly whitelists id/version/intent/validity/displayStatus/contentAvailable/reason. Per-revision version, intent, validity and reason survive; conditions, body and source references/hashes do not. Mixed available/unavailable pages are conservatively body-free during suppression. Opaque history cursor paging remains usable; historical version is never installed as current CAS. |
| No old semantic-byte restoration | Suppression is retained across refresh/reselection in this feature scope; readable later responses are rendered body-free. Original copied-draft/source suppression fixtures pass. Additional reviewer stale-list/reselection probe finds no old subject/body, Correct or exact-source controls after suppression. |
| Terminal410 | Current/history erasure uses the terminal parent view, removes list identity/body and unmounts lifecycle controls. Developer fresh-metadata→410 and late-list probes pass. Additional reviewer history410→Refresh→All probe returns stale readable list/current fixtures and proves no old row/body/Delete and no new current read are restored in that mounted scope. |
| Pending-operation safety | Unavailable lifecycle actions lock while an outcome is unknown; history remains readable. R2 provider/runtime scope is unchanged. Original Home/Back and expanded exact requestId/key/serialized-body retry, workspace/actor/logout/revocation late-response tests pass again. No persistent body store or new global cache is introduced. |
| Ordinary409 | Existing comparison/draft fixture passes again. Its actual scope remains a PATCH conflict with a correction draft open while admission is disabled; live correction/resave acceptance remains pending. |

M46-R1–R4 closures from C2 stand: three unchanged original browser probes and all four original R3/R4 helper assertions pass against C3. Fresh compilation also reran current body/query/response allowlists, trusted-server-identity/no-store, target binding, enum primitives and stable unknown-operation identity tests. C3 does not modify those BFF boundaries or assert new backend authorization evidence.

### C3 independent execution ledger

| Evidence class | Reviewer result |
|---|---|
| Whole-web TypeScript | `tsc --noEmit --incremental false -p apps/web/tsconfig.json`, exit0; rerun after adding reviewer probes. Separate from Next build, includes unresolved identifiers/imports. |
| Whole source/E2E/scripts/config ESLint | exit0 using the C2 command below |
| Freshly compiled unit/helper fixtures | **32/32 pass**: 28 current feature tests plus four unchanged original reviewer assertions |
| Developer intercepted-browser suite | **26/26 pass**, 37.0s, reviewer-started lane-local Next16 at `127.0.0.1:3146` |
| Unchanged original reviewer browser suite | **3/3 pass**, 3.7s |
| Unchanged original R5 reviewer probes | **2/2 pass**, 2.5s; both failed on C2 |
| Additional C3 reviewer probes | **2/2 pass**, 2.8s: terminal410 stale refresh/filter; suppressed reselection fresh CAS11 |
| Production build | **unaccepted**. Read C3 `build.txt`: exit1 fetching existing Geist/Geist Mono Google Fonts during production compilation. No reviewer build pass or replacement typography claimed. Reviewer dev run also reported font-fetch failures. |
| Actual API / visible normal workflow | **not executed by this review; acceptance pending** |

Browser suites use intercepted synthetic responses and the real candidate components. They do not traverse the actual memory BFF/backend on those intercepted requests. The BFF unit suite uses mocked upstream responses. Fixture navigation/mobile checks do not establish real visible usability. The original R5 probes are also included in the developer suite; these reruns are recorded separately for provenance, not counted as independent distinct coverage.

Reviewer scratch evidence, all under `apps/web/.memory-tests/` and excluded from commits:

- `reviewer-c3-unit.txt`, freshly compiled `reviewer-compiled/` including `body-free.test.ts`.
- `reviewer-c3-browser.txt` / `reviewer-c3-browser-results/`.
- `reviewer-c3-original-browser.txt` / `reviewer-c3-original-results/`.
- `reviewer-c3-r5-browser.txt` / `reviewer-c3-r5-results/`.
- `reviewer-c3-extra.spec.ts`, `reviewer-c3-extra.config.ts`, `reviewer-c3-extra-browser.txt` / `reviewer-c3-extra-results/`.

Reproduction follows the C2 commands below, adding `apps/web/src/lib/memory/body-free.test.ts` to compilation, using C3 result paths, and running the additional `--config apps/web/.memory-tests/reviewer-c3-extra.config.ts`. The existing original spec/config/assertions were not edited. Reviewer-started port3146 server was stopped after testing; no unrelated process or generated Next tree was cleaned.

### Integration disposition / original-developer handoff

**R5 rework accepted at this bounded scope; no further C3 code correction requested of `agt_12787a1e`.** Controller can proceed to the planned separately owned API integration/activation candidate. Per controller, API PR50 at `b6192d8` is independently accepted and pushed, with56 PostgreSQL and76 actual-HTTP passes, but unmerged at this review. Those are **controller-reported API results**, not runs performed or cross-tree verification claimed by this reviewer.

Next acceptance requires the actual integrated bytes and real authenticated workspace → Settings → Memory workflow with visible screenshots and matching actual API/network/state evidence. Include owner/member own-record handling and cross-owner denial, create/correct under approved activation, ordinary409 draft recovery, lost-ack original-pair polling/retry, exact-source/history fidelity and permanent delete/tombstone behavior. Do not infer these from fixture passes or the separate API acceptance. Production build remains unresolved. Full #46/#41, later compaction status and continuation/end-to-end paths remain open.

Only this review is a durable reviewer write; scratch is confined to `.memory-tests/`. No product, Git, backend, model, private MEMORY, shared-workbench or old-tree changes. Write-back check: durable review outcomes and limits are recorded here; no duplicate profile-memory write. Controller relay to the original developer remains necessary. Historical C2 changes-requested disposition below is superseded by this C3 section.

---
## C2 — targeted original-reviewer recheck (2026-09-28, 22:01 +08:00)

**CHANGES REQUESTED: M46-R5 below. Original M46-R1–R4 are closed at the stated static/fixture scope. No actual-API, visible-browser usability or full #46 acceptance.**

Frozen candidate manifest `evidence/issue46/c2/candidate-manifest.sha256` independently hashes to `F3097CAE91BCFA8A3B3EAC623AB9E90F6EE52840E0117787CB0ABA717C59EDC2`. All **34 listed file hashes match** current bytes; manifest hash was rechecked after testing. Base remains `9cd93ec1aa70ea803401a88c55834de1593f0aeb`. Inspected C2 lane/evidence, the new provider/state/context files, suppression and response-validator changes, and added tests. No product/Git changes were made by the reviewer.

### M46-R5 — P1: suppression removes permitted management of content-unavailable records

**Files:** `apps/web/src/components/memory/memory-panel.tsx:51–53`; `memory-detail.tsx:36–39,58–62`; `apps/web/src/lib/memory/use-memory-management.ts:26–32` (`invalidate`).

The R1 confidentiality fix clears the old copied body, but it replaces the entire selected detail with a display-only section whenever a valid current DTO has `contentAvailable:false`. An authenticated owner can therefore no longer Delete a nondeleted source-unavailable record. Deactivate/history controls disappear as well, and `invalidate` removes the legitimate body-free row from the current list. Refresh followed by selecting it again repeats the same result.

**Independent reproductions:** for the same signed-in fixture actor who owns the record, return a contract-valid current/list DTO containing `id`, `version:2`, `validity:invalidated`, `contentAvailable:false`, `reason:source_unavailable` and either:

- `intent:active`, `displayStatus:invalidated`; or
- `intent:inactive`, `displayStatus:inactive`.

Enter Settings → Memory, select the matching status, then select its body-free row. Old body text remains suppressed as required. Both tests fail because the Delete button is absent; no mutation is dispatched. Screenshot/DOM inspection shows only status/version/source-unavailable text and an empty list. The owner cannot complete the permanent-erasure workflow through this UI.

**Contract basis:** current unavailable DTOs deliberately retain owned record identity, current version and lifecycle metadata. DELETE consumes `{requestId,expectedVersion}`; it does not require readable content. Existing lane-local core `commands.py:137–173` also checks owner/current version and terminal intent, not readability, before delete. This is static contract/core corroboration, not new API runtime acceptance. Source unavailability does not mean the record was erased or permission was revoked. Historical unavailable DTOs also retain version/intent/validity/display metadata; `read(history)` currently discards that page after finding any unavailable revision and suppresses the whole record.

**Required rework:** keep body/conditions/source/editor suppression, stale-response fencing and explicit erased/not-found handling. Retain an authorized content-free current projection for allowed lifecycle actions (Delete for a nondeleted record, Deactivate where supported) and preserve safe revision metadata/history paging. Obtain fresh authorized current metadata when only a source-read failure is known; do not infer permissions/version from a stale previously readable body. Do not restore private bytes, reactivate deleted records, add unsupported controls or change backend contracts. Cover unavailable active/inactive management and safe unavailable-history projection alongside all original suppression/race tests.

**Evidence:** `apps/web/.memory-tests/reviewer-c2-extra.spec.ts:24–42` has two new fixture checks; both fail at line39 expecting Delete. Log `reviewer-c2-extra-browser.txt`; screenshot/DOM/trace directories under `reviewer-c2-extra-results/` ending `1b863-t-unavailable-active-record` and `2ba41-unavailable-inactive-record`. Full prefix is `apps/web/.memory-tests/`. These tests use actual candidate components with intercepted responses. They prove the frontend regression without claiming an actual backend delete attempt.

### Closure of the original findings

| Finding | Recheck disposition and direct evidence |
|---|---|
| M46-R1 retained private bytes | **closed for original failures.** Both unchanged reviewer adverse browser cases pass: current 200 unavailable removes copied editor; history410 removes old subject. Developer exact-source404/410 and late-list/erasure regressions also pass. The excessive suppression of valid content-free management is separately recorded as R5. |
| M46-R2 lost Home/Back identity | **closed at runtime fixture scope.** Original reviewer Home/Back test passes unchanged. Developer expanded test checks no automatic resend, then exact original method/path/serialized body/Idempotency-Key and UUID on explicit Retry after Home/Back. Original command is retained in the scoped React provider. |
| M46-R3 target/operation correlation | **closed at validator/helper scope.** All three original adverse assertions now pass against freshly compiled current code. BFF supplies targetId, rejects missing targeted IDs and validates record/revision/deactivate/delete, request/operation and correction-predecessor bindings. Additional tests preserve alternate request-ID replay aliases and a distinct correction successor. |
| M46-R4 enum coercion | **closed at validator/helper scope.** Original array-enum assertion passes. New primitive/container cases cover memory and operation enums. `member` requires a string; original coercion is gone. |

### Provider placement, runtime lifecycle and scope fencing

The approved layout delta is exactly one import plus one `MemorySessionProvider` wrapper inside the existing WorkspaceProvider, with I18n → Theme → Auth → Workspace ordering preserved. RootLayout remains a Server Component; the feature provider is a Client Component wrapping children. Relevant installed Next16 guidance was read: `01-app/03-api-reference/04-functions/use-pathname.md` and the Context providers section of `01-app/01-getting-started/05-server-and-client-components.md`. The current config does not enable Cache Components.

The provider's single responsibility is a scoped unresolved-operation runtime lifetime. `session-state.ts` stores actor, workspace, epoch, revoked and the immutable pending operation. It stores no lists, sources or copied editors. `alignSession` retains the same scope on Home, and advances epoch/clears pending on actor/logout/explicit workspace changes during rendering before consumers receive the new scope. `updatePending` and `revokeSession` reject stale epoch callbacks; revoked scope cannot accept new pending state. `MemoryPanel` gates mismatched/revoked scope and keys its local view by actor/workspace/epoch. Detached views abort their requests; `stopped`/abort checks prevent old poll/mutation completions from committing view state.

**pass at inspected/tested scope:** feature-owned runtime composition; no private body in localStorage/sessionStorage, a module-global cache, persisted Workspace/server state or a new durability contract. No shared-chat/backend/auth implementation edit was introduced. The former document-wide tab interception is removed. Beforeunload warning is scoped to a pending operation and does not imply restart durability. `memoryAdmissionEnabled=false` remains unchanged.

**Executed race fixtures:** explicit workspace change with a held mutation and a held committed poll; logout/login as another actor with a held committed poll; revocation followed by Home/Back with a held poll; original delayed source/logout; original ordinary409 preserving typed correction and requiring comparison. All passed independently. The409 fixture still uses a PATCH conflict while a correction draft is open, because create/correct remain gated; it does not establish a live correction/resave through the actual API. Tests establish the sampled interleavings; actual signed-session/member-revocation and real API races remain separate gates.

### C2 independent execution ledger

| Evidence class | Result |
|---|---|
| Manifest | 34/34 bytes matched; exact file SHA256 matches controller handoff |
| Whole-web strict TypeScript | exit0; separate no-emit check, including unresolved identifiers/imports |
| Whole source/E2E/scripts/config ESLint | exit0 |
| Dedicated Node fixtures | **30/30 pass**, including 26 current feature tests and the four original reviewer adverse assertions; current source freshly compiled into `.memory-tests/reviewer-compiled` |
| Developer intercepted-browser suite | **18/18 pass**, exit0, 31.3s on reviewer-started lane-local Next at `127.0.0.1:3146` |
| Original reviewer browser adverse suite | **3/3 pass unchanged**, exit0, 4.4s |
| Adjacent R1 lifecycle probes | **2/2 fail**, missing Delete for valid unavailable active/inactive records; R5 |
| Production build | **blocked/unaccepted**. C2 developer evidence shows ENOTEMPTY removing generated `.next/memory-c2-browser-results` before compilation; earlier Google Fonts constraint remains. Reviewer did not clean generated Next directories or claim a build pass. |
| Authenticated real API / visible normal workflow | **not run; blocked for acceptance**, unchanged |
| Full #46/#41 | **open**, including later compaction/continuation and end-to-end paths |

Commands (root unless noted):

```powershell
node apps/web/node_modules/typescript/bin/tsc --noEmit --incremental false -p apps/web/tsconfig.json
node apps/web/node_modules/typescript/bin/tsc --target es2022 --module commonjs --moduleResolution node --esModuleInterop --skipLibCheck --strict --types node --typeRoots apps/web/node_modules/@types --outDir apps/web/.memory-tests/reviewer-compiled apps/web/src/lib/memory/validation.test.ts apps/web/src/lib/memory/proxy.test.ts apps/web/src/lib/memory/client.test.ts apps/web/src/lib/memory/response.test.ts apps/web/src/lib/memory/session-state.test.ts
node --test apps/web/.memory-tests/reviewer-compiled/*.test.js apps/web/.memory-tests/reviewer-adversarial.test.cjs
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:3146'
node apps/web/node_modules/@playwright/test/cli.js test --config apps/web/playwright.config.ts e2e/memory-management.spec.ts --workers=1 --reporter=list --output=apps/web/.memory-tests/reviewer-c2-browser-results
node apps/web/node_modules/@playwright/test/cli.js test --config apps/web/.memory-tests/reviewer-playwright.config.ts --output=apps/web/.memory-tests/reviewer-c2-original-results
node apps/web/node_modules/@playwright/test/cli.js test --config apps/web/.memory-tests/reviewer-c2-extra.config.ts
```

From `apps/web`, lint command remained `node node_modules/eslint/bin/eslint.js src e2e scripts next.config.ts playwright.config.ts eslint.config.mjs postcss.config.mjs`; reviewer-owned dev server command remained `node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3146`. Scratch final logs: `reviewer-c2-browser.txt`, `reviewer-c2-original-browser.txt`, `reviewer-c2-extra-browser.txt`. Scratch stays excluded from commits. No generated evidence was placed inside `.next` by this review. The reviewer-owned port3146 dev process was stopped after testing; no unrelated process was stopped.

**Original-developer handoff:** return R5 to `agt_12787a1e`, retaining the approved provider scope and accepted R2–R4 fixes. Same reviewer will rerun the original and adjacent lifecycle probes. Controller relay remains necessary because that external agent is not in this session's exposed collaboration tree. Reviewer-only durable update is this artifact; no product/Git/model/private-memory/shared-workbench write. Earlier C1 text below is historical and is superseded by this C2 disposition.

---
## C1 — current candidate disposition (2026-09-28, 21:18 +08:00)

**CHANGES REQUESTED — four concrete current-code findings below. No feature usability, real-API authorization or full #46 acceptance.** The intended result is a member or owner safely managing their own private records through workspace → Settings → Memory, retaining a recoverable original mutation when its outcome is unknown and suppressing erased/unreadable bytes everywhere in that view. Existing happy-path counts do not establish those outcomes; independent adverse-path tests reproduced failures.

Reviewed working-tree candidate: `lanes/issue46-management-ui.md` and `evidence/issue46/`, over fixed HEAD `9cd93ec1aa70ea803401a88c55834de1593f0aeb`. Product/test scope is 29 files: all files in `src/lib/memory/`, `src/components/memory/`, the new memories/sources BFF directories, plus Settings, i18n and the memory E2E file. Sorted workspace-relative path plus SHA256 lines, joined with LF, yield manifest hash `FCCA2F4A56B0755C4359D7E7BFEEC45A6FA7CD6AA175F53FFC7B680C8182856C`. This identifies inspected bytes only.

Controller handoff reports independently accepted core admission `893de95` integrated into API `7d47607`, with API completion/review still underway. This reviewer did not inspect another worktree or infer an accepted API from those hashes. `memoryAdmissionEnabled=false` is still the appropriate current activation boundary. The older blanket admission-pending descriptions in the lane/copy should be reconciled with that handoff when preparing the next candidate; do not enable create/correct ahead of accepted API integration.

### M46-R1 — P1: authoritative unavailability does not clear every retained private projection

**Files:** `apps/web/src/components/memory/memory-detail.tsx:25–40,57–60,78–80`; `apps/web/src/lib/memory/use-memory-management.ts:11,27–30`; `apps/web/src/components/memory/memory-form.tsx:10–13`.

Two independently reproduced cases:

1. Open an available record and Correct, copying its body/conditions into the form without typing any new draft. Refresh after the current GET changes to a valid `contentAvailable:false, reason:source_unavailable` DTO; the active list correctly becomes empty. The detail says the source is unavailable, but the form still contains the old record's subject, applicability and body. The success handler stores the unavailable DTO without clearing `edit`, and the form retains its state. This is previously retrieved private content, not independently typed unsaved wording whose loss might be justified by a conflict decision.
2. Open an available record, then receive owner `410 erased` from its revisions endpoint (for example, deleted in another session). Detail/history is cleared, but the list button still exposes `conditions.subject` from the cached available row. `report` only handles whole-session/workspace revocation or sets an error; it has no record-level invalidation path to clear the parent list.

**Impact:** a recognized erasure/readability decision leaves semantic bytes readable in the current feature. The lane's complete-clear claim does not hold. Ordinary 409 draft preservation must remain intact; content-readability denial needs its own explicit transition across list/detail/history/source/copied editor state.

**Required rework:** propagate authorized target unavailability through feature-owned state; discard retained protected projections and fence late reads that could restore them. Cover both 200 unavailable DTOs and relevant current/history/source 410/404 paths. Preserve the narrower distinction between exact-source unavailability and permanent record erasure; do not invent an erased tombstone for every missing source.

**Evidence:** reviewer intercepted-browser tests at `.memory-tests/reviewer-adversarial.spec.ts:23,38` fail expected removal (received one old-content editor / one old-subject list button). Final run uses an empty active-list response after invalidation, consistent with the API filter. Screenshot and DOM/error context confirm the old form alongside the unavailable current projection. This reproduces frontend state handling, not a backend erasure defect or cross-owner API leak.

### M46-R2 — P1: ordinary Home → Back navigation abandons unresolved request identity

**Files:** `apps/web/src/lib/memory/use-pending-navigation.ts:7–17`; `apps/web/src/lib/memory/use-memory-management.ts:15,44–47,72–97`; existing Home link in `components/workspace-sidebar.tsx` is an integration observation, not an assigned edit.

**Reproduction:** trigger Delete; return `503 outcome_unknown`, with original-request polls returning `404 operation_not_found`. The original UUID and Retry original request are visible. Click the ordinary Home link, wait for the SPA URL `/`, then browser Back → Settings → Memory for the same authenticated user/workspace. The original UUID/retry state is gone; the record is offered as ordinary actionable data again. This path performs neither logout nor an explicit workspace switch nor a forced document unload.

**Cause:** the navigation hook intercepts only clicks on outer `role=tab` controls. Next Link navigation does not fire beforeunload, and unmount destroys the sole runtime request/body/key holder. The operation may still commit after the original response was lost, so starting again can acquire a different identity.

**Required rework:** retain or safely guard the unresolved operation across ordinary same-scope navigation using a cohesive feature-lifetime boundary. Do not persist private bodies in unscoped storage or expand shared-chat ownership. Any necessary ownership expansion returns to the controller. Preserve explicit scope/auth clearing and the original requestId/key/body pair; extend actual navigation tests beyond the AI Chat tab click.

**Evidence:** `.memory-tests/reviewer-adversarial.spec.ts:47` fails after explicitly awaiting Home navigation and returning. DOM snapshot has no pending UUID/retry state. An initial timing probe checked the URL before navigation settled; it was corrected before the final run. Final result is reproducible, not that earlier transient observation.

### M46-R3 — P2: successful responses are not correlated to requested resource/operation identities

**Files:** `apps/web/src/lib/memory/proxy.ts:52–58`; `apps/web/src/lib/memory/response.ts:48–63`; downstream `use-memory-management.ts:50–55,85–86` and `memory-detail.tsx:64,72–73`.

The BFF verifies structural shape and available-body owner/workspace, but receives no expected endpoint ID in `validResponse`. Only source reads compare the exact requested tuple. Adversarial helper tests show HTTP 200 for all three cases:

- current GET for memory A returns an otherwise valid, same-owner/workspace memory B;
- request poll for original request A returns a committed operation whose requestId is B;
- DELETE A returns a valid completed receipt with id B.

**Impact:** the UI can display B while actions still target A, or clear A's pending state based on B's operation. This is a malformed-upstream response-handling failure; no evidence here claims the actual API currently emits these values or leaks another owner's body.

**Required rework:** correlate current/revision/deactivate/delete target IDs, request/operation poll identities and correction predecessor to their endpoint contracts. Keep malformed mutation acknowledgements outcome-unknown and retain the original pending identity. Preserve the API's legitimate alternate requestId/key replay semantics: a mutation receipt may return the originally stored requestId, so do not blindly require every mutation receipt requestId to equal a later replay alias. A correction successor is intentionally a different record ID.

**Evidence:** three isolated proxy tests in `.memory-tests/reviewer-adversarial.test.cjs:9–11` expect safe failure and receive 200. No network or actual API is used for these cases.

### M46-R4 — P2: enum coercion admits non-contract DTO values

**File:** `apps/web/src/lib/memory/response.ts:18–21,33,58`.

`String(value)` converts array-valued enums into accepted strings while forwarding the original array unchanged. The strict DTO validator accepts current-memory payloads with `intent:["active"]`, `validity:["valid"]` and `confirmation:["explicit_remember"]`. Similar coercion exists for unavailable reasons and operation fields. Downstream state checks use strict string equality, so validation and rendering/action predicates no longer operate on the same type.

**Required rework:** require actual string enum members without coercion and retain fail-closed available/unavailable projection checks. Add malformed primitive/container cases to the boundary tests.

**Evidence:** `.memory-tests/reviewer-adversarial.test.cjs:8` reports all three invalid fields accepted; expected accepted-fields list is empty. This is strict contract-validation evidence, not a claim about actual API output.

### Independent execution and evidence classes

| Class | Result and scope |
|---|---|
| TypeScript | **pass**, exit 0: `node apps/web/node_modules/typescript/bin/tsc --noEmit --incremental false -p apps/web/tsconfig.json`. Includes changed TS/TSX and generated route types. Changed imports/identifiers inspected beyond Next build. |
| ESLint | **pass**, exit 0 from `apps/web`: `node node_modules/eslint/bin/eslint.js src e2e scripts next.config.ts playwright.config.ts eslint.config.mjs postcss.config.mjs`. |
| Developer unit fixtures, independently rerun | **18/18 pass** after compiling current source/tests with strict TypeScript to `.memory-tests/reviewer-compiled`; Node test runner exit 0. Doubled session/fetch only. |
| Developer intercepted browser fixtures, independently rerun | **8/8 pass** on reviewer-started lane-local Next16 dev server `127.0.0.1:3146`; headless Chromium, intercepted auth/workspace/memory/source data, exit 0 in 11.9s. Bypasses authenticated BFF/API. |
| Reviewer adverse browser fixtures | **3/3 fail the governing invariants**, final run: retained unreadable copied form; retained erased list subject; lost pending identity after Home/Back. Exit 1. Actual candidate components with intercepted data. |
| Reviewer adverse proxy/DTO fixtures | **4/4 fail the governing assertions**, exit 1: enum-container rejection and three target/request correlations. Synthetic dependencies only. |
| Live unauthenticated Next HTTP | **pass at narrow boundary**: list (including forged actor/internal headers), history and request poll return 401 with fixed `authentication_required`, requestId null, `Cache-Control: private, no-store, max-age=0`, Vary includes Cookie. Malformed create JSON returns 422 fixed `invalid_request`, null requestId, same no-store policy. No signed-in or backend request was exercised. |
| Visual fixture inspection | Developer 390×844 screenshot inspected: existing compact zinc/dark Settings language and no horizontal overflow in the repeated mobile fixture. Reviewer failure screenshot/DOM inspected for R1. These are intercepted-data/dev-font observations only. |
| Production build | **blocked**, developer-recorded Google Geist/Geist Mono fetch failure in unchanged layout. Not independently rerun and not treated as a product typography defect. No font replacement or mocked build success. |
| Full existing web unit suite | **not run by reviewer**; dedicated feature fixtures do not imply whole-repository regression acceptance. |
| Actual authenticated API and private owner/member isolation | **blocked**, actual API completion/integration and signed-session/backend workflow not exercised here. |
| Real visible browser acceptance | **blocked**. No actual-API sign-in/workspace/Memory manual workflow, screenshot/network acceptance is claimed. |
| Full #46/#41 | **open**, including later compaction status and end-to-end continuation/recovery/quality paths. |

Reproducible feature-unit command from root:

```powershell
node apps/web/node_modules/typescript/bin/tsc --target es2022 --module commonjs --moduleResolution node --esModuleInterop --skipLibCheck --strict --types node --typeRoots apps/web/node_modules/@types --outDir apps/web/.memory-tests/reviewer-compiled apps/web/src/lib/memory/validation.test.ts apps/web/src/lib/memory/proxy.test.ts apps/web/src/lib/memory/client.test.ts apps/web/src/lib/memory/response.test.ts
node --test apps/web/.memory-tests/reviewer-compiled/*.test.js
node --test apps/web/.memory-tests/reviewer-adversarial.test.cjs
```

Reviewer-started server, from `apps/web`: `node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3146`. Developer E2E rerun there: set `PLAYWRIGHT_BASE_URL=http://127.0.0.1:3146`, then `node node_modules/@playwright/test/cli.js test e2e/memory-management.spec.ts --workers=1 --reporter=list --output=.memory-tests/reviewer-playwright-results`. Reviewer adverse fixtures from root: `node apps/web/node_modules/@playwright/test/cli.js test --config apps/web/.memory-tests/reviewer-playwright.config.ts`.

Scratch evidence (excluded from commits):

- `apps/web/.memory-tests/reviewer-adversarial.spec.ts`, `reviewer-playwright.config.ts`, `reviewer-adversarial.test.cjs`.
- `reviewer-browser-adversarial.txt`, `reviewer-unit-adversarial.txt` record final failures.
- `reviewer-adversarial-results/reviewer-adversarial-revie-4c55e-clears-copied-private-draft/`, `...-fdba2-removes-cached-list-subject/`, `...-c7034-abandon-unresolved-identity/`: screenshots, error-context DOM and traces. The full parent path is `apps/web/.memory-tests/`.

The durable reproductions and actual results above remain in this reviewer artifact even when scratch is removed. The reviewer-owned dev process was stopped after testing; no unrelated service was stopped. Its output independently showed development fallback-font warnings and empty-avatar fixture warnings, with no production-build pass inferred. No product source, package, activation flag or Git state was changed by the reviewer.

### Bounded judgments and remaining acceptance

- **pass at static/fixture scope:** A1 privacy sentence accurately excludes private records from shared chat/Research; no unsupported active/pin/expiry/search/index/restore control found. New memory dependencies stay within feature/Settings/BFF boundaries, with no private model/provider path or private-body logging/localStorage/sessionStorage added. Body/query/key allowlists, selected server-derived headers, no-store, refusal of redirects, exact-source tuple comparison and fixed upstream error text are present. Both member and owner reach Memory in intercepted fixtures while Evaluation remains owner-only.
- **pass at tested happy-path scope:** runtime account/workspace keyed components, abort checks, list/read generations, whole-workspace denial teardown, same-pair explicit retry/polling and conflict refresh retaining the typed form. The conflict fixture provokes PATCH conflict while an unsent correction form is open; it does not execute create/correct through the disabled gate or prove successor save/resave. Real delayed actor/workspace/mutation/poll races remain required.
- **blocked for current-code approval:** R1–R4. Correct within the original feature ownership, keep responsibilities coherent, then have this same reviewer rerun the original and adverse checks. No reviewer-authored product fix or replacement implementation.
- **blocked for API/visible acceptance:** signed-cookie → BFF → unchanged real backend auth/member/owner guards; source/history availability truth table; real CAS successor flow; dropped committed acknowledgement/poll; deletion all-revision erasure; re-entry/restart/scope changes; production-font and keyboard/mobile walkthrough. Historical validity and the effectiveFrom/validUntil/confirmation/supersession metadata are only sparsely displayed by MemoryRecord and need explicit real-data readability examination; this review does not claim that every historical semantic distinction has been visibly accepted.
- **Architecture:** new feature files are bounded and do not overload shared chat/Workspace models. Target unavailability needs a single feature-level propagation rule; navigation lifetime should be fixed without growing a document-wide collection of special cases or an unscoped persistent cache.

Rework owner: original developer `agt_12787a1e`. Attempted direct relay failed because that ID is not in this session's live collaboration tree (only reviewer `/root` is exposed); controller must deliver R1–R4 and the artifact to the existing developer. No new agent was spawned. Same reviewer will recheck the original developer's next candidate.

Write-back check: durable verified review is here; scratch is explicitly non-product/non-commit evidence. No private memory or shared workbench writes. Earlier preparation follows as historical context and does not override this C1 disposition.

---
## Historical preparation disposition — before candidate handoff

**PENDING CANDIDATE; NO IMPLEMENTATION ACCEPTANCE.** At inspection on 2026-09-28, HEAD is `9cd93ec1aa70ea803401a88c55834de1593f0aeb`, branch `work/issue46-memory-management-ui`. The tracked/untracked worktree was clean before this reviewer file was created. No ready Memory component/hook/BFF candidate was supplied at baseline inspection. No candidate findings are asserted.

This preparation permits the assigned developer's bounded frontend work to continue. Backend implementation and unmerged #47/#48 constrain dependent integration/acceptance, not unrelated frontend authoring. Full #46 remains open for later compaction status, continuation/recovery and end-to-end paths.

## Authority and ownership

- Governing authority: full `specs/v5/memory-management/spec.md` v4, especially §§8, 10, 12–14; final A1 choice2; `design.md` §§3, 7.1, 7.3, 11 and the narrower operative API consumer contract.
- Exact consumer contract: `lanes/issue42-management.md`, SHA-256 `2EBF5D6BD9A9C298D21253C50A9ECAA869AD9AC2A437BFEDF354BF0A961F2802`.
- `reviews/issue42-management.md` grants bounded consumer-contract approval at that hash. Its original admission integration/create-correct activation and actual API/runtime gates remain in force. The contract's earlier PROPOSED heading does not expand or negate the later explicitly bounded review disposition.
- Spec SHA-256: `A15B1B55E2542B01455B47B67508CFFD673DD532DAB2932702AD771B08A1FE85`. Hashes identify inputs; they do not prove behavior.
- Developer `agt_12787a1e` owns new memory feature component/hook/BFF routes, narrow Settings entry/i18n/tests. No backend/shared-chat/shared-model change is assigned here.
- This reviewer owns only `specs/v5/memory-management/reviews/issue46-management-ui.md`. Findings/rework will return to the original developer and be rechecked by this reviewer. No implementation was authored by the reviewer.

## Bootstrap and framework-document gate

Read Windows global alignment/review/writing rules, SOUL/IDENTITY and memory policy. Private MEMORY and dated private memory were not accessed. `prepare_session.py --repo-path D:/Code/citeframe-lanes/issue46-management-ui` succeeded; referenced workbench project/state/task were read. Git remote/identity inspection was read-only; GitHub local/global identity matches. No Git/model/product/global-state writes occurred.

Read `apps/web/AGENTS.md`: it requires relevant installed Next.js guidance before framework judgment. `apps/web/package.json` pins Next `16.2.10`, React `19.2.4`; `tsconfig.json` is strict and includes TS/TSX plus Next-generated types.

**Local-document prerequisite CLOSED at 20:46 +08:00 on 2026-09-28.** The controller reported its frozen pnpm install completed (462 packages, downloaded 0). This reviewer independently verified installed Next `16.2.10`, read the relevant local guidance listed below, and observed an empty `git diff -- pnpm-lock.yaml`. Initial dependency-doc absence and denied network/browser attempts are historical only; no further remote access was attempted. No package install or dependency modification was performed by this reviewer. Documentation readiness grants no candidate or runtime acceptance.

## Actual source baseline inspected

These are source observations, not browser or feature acceptance:

1. `apps/web/src/app/workspaces/[workspaceId]/page.tsx:65–88,160,240–253,280`: workspace/auth context drives the existing workspace screen and Settings tab; Settings renders `SettingsPanel`. Mobile controls use the existing responsive shell. Real entry is sign-in → workspace selection → workspace → Settings → Memory.
2. `apps/web/src/components/settings-panel.tsx:18–25,94,172–205`: existing Settings has workspace/evaluation views. The inner tablist is owner-only, and nonowners are forced to workspace view. The new private Memory entry must be reachable by both members and owners without changing owner-only model settings or moving memory business logic into the shell. Current zinc/light/dark styling, scroll containment and responsive padding establish the source baseline; screenshot comparison is still required.
3. `apps/web/src/lib/auth/server-session.ts:1–18` reads/verifies the session cookie. `auth/server-route.ts:24–32` builds upstream actor/internal-auth headers and then spreads additional headers. This is a relevant call-site constraint: new forwarding must never pass arbitrary incoming headers into that spread. It is not a finding against an absent candidate and does not authorize rewriting the shared helper.
4. Existing `app/api/workspaces/[workspaceId]/model-settings/route.ts` awaits promise params, uses the server session's user ID, fetches with `cache: no-store` and returns `Cache-Control: no-store`. Settings/assets BFF routes and API-base-url selection were also inspected for actual conventions. Memory still requires its own bounded methods/paths/query/body/header forwarding and accurate error handling.
5. `lib/auth/auth-context.tsx`, `lib/workspace-context.tsx` and `lib/model-settings/use-model-settings.ts` were read for auth hydration, user/workspace transitions, fetch cancellation and feature boundaries. Memory state must remain feature-local and independently fenced; this review does not prescribe copying another feature's async behavior.
6. `e2e/authenticated-smoke.spec.ts` and `playwright.config.ts` establish an existing actual sign-in/workspace/Settings path. Credential-gated/skipped tests and route-intercepted scenarios must be reported separately. The existing suite does not prove the new feature.
7. File inventory contains no memory UI/hook/BFF route at this baseline. `git diff --stat` and `git status --porcelain=v1` were empty before this review artifact.

## Semantic oracle for candidate adjudication

| Area | Verifiable requirement and decisive evidence | Current disposition |
|---|---|---|
| Private identity and permissions | Actual browser/BFF/API chain derives actor from verified server session and internal auth from server config. Browser actor/token headers, identity JSON, role/purpose/grants cannot choose authority. Use two members plus workspace owner: each manages only own records; owner cannot inspect another member's current/history/source/request/operation. Missing/bad auth and revoked/archived workspace fail closed without foreign metadata. | blocked: candidate/integration pending |
| Feature boundary | Only allowed new feature/BFF and narrow entry/i18n/tests change. No private content joins Workspace persistence, shared chat/Research, prompts, tools, summaries, checkpoints, plans, logs or derived outputs. No promise of private reuse in shared outputs. No paid model calls are needed for this lane. | blocked: candidate pending |
| Scope/auth fencing | Immediately hide/reset private list, draft, history, source and receipt state when user/workspace/auth validity changes; abort requests and reject late success/error/finally effects. Exercise delayed list/history/source/mutation/poll responses, switch-away/back and logout/login. A returned auth/workspace denial clears protected data. A workspace-only cache key is insufficient across actors. | blocked: candidate pending |
| Cache isolation | Private requests and BFF responses, including errors, are noncacheable; no unscoped module singleton, localStorage, persisted Workspace or shared-query private-body cache. Server request memoization and route fetch/cache behavior must be checked against Next16 documentation and actual headers. | blocked: candidate pending |
| Exact API mapping | Map the declared discriminated DTOs and literal error semantics. Supported writes are create, correction successor, inactive PATCH and DELETE with expectedVersion. No active/reactivate, pin/expiry-only edit, search/index/backfill/restore controls, queued-index status or unsupported scope. Optional feature aspirations in the broader design do not expand this mounted subset. | blocked: candidate pending |
| Lost acknowledgement | Retain original requestId + Idempotency-Key + immutable command/body until resolved. Timeout/outcome_unknown/operation_in_progress uses content-free original request polling. A polling 404 is not proof of rollback and cannot automatically generate a replacement identity. Explicit resend retains the exact pair/body; altered body cannot reuse the pair. Verify dropped response after actual commit, poll/replay and no duplicate operation. | blocked: candidate/integration pending |
| CAS/conflict recovery | A correction carries the displayed expectedVersion, creates/selects its successor and preserves predecessor history. On 409 retain the exact local draft, show fresh authorized current state/version and require explicit resave. Do not silently overwrite, rebase or reinterpret every 409 as version_conflict. New body/version requires a deliberate new mutation identity only after the previous attempt is resolved. | blocked: candidate pending |
| Erasure and terminal states | Successful delete matches synchronous core cleanup completed, clears cached body/conditions/source/history for the erased target and refreshes authorized state. Owner current/history 410 and minimal list/replay tombstones never resurrect text. Foreign IDs remain 404. Poll/replay remain content-free/current-head aware. UI states original conversation/document retention accurately, without claiming backup/provider erasure or restore. | blocked: candidate/integration pending |
| Exact source | Submit the returned sourceId/sourceVersion/contentSha256/span:null unchanged. Render original instruction/provenance/time/role/attribution/branch/exact version. Source 410 clears displayed source and offers no newest-version fallback; other owner/workspace gets 404. No arbitrary path/URL resolver or client attribution. | blocked: candidate pending |
| Readability/history | contentAvailable discriminates accessible body from suppression. Unavailable DTOs have no semantic fields; do not fill fake empty bodies or carry old fields forward. Preserve persisted revision intent/validity and server displayStatus. Stored-valid historical data can be presently unavailable; inactive/superseded display precedence remains. Operation contentAvailable concerns current head, not resultVersion's old bytes. | blocked: candidate pending |
| Live paging | Use exact opaque nextCursor; reset on actor/workspace/filter/target changes. Do not mix revisions or statuses or claim snapshot completeness. Tampered/expired/mismatched cursor recovery refreshes the intended view without private-data carryover. | blocked: candidate pending |
| Visible quality | Both roles reach Memory through actual Settings; empty/loading/save/error/recovery states are legible. Preserve existing light/dark visual language; check long multiline/CJK text, mobile width/scrolling, labels, keyboard focus/tab semantics, destructive confirmation and readable source/history. No redundant decorative instructions/cards/subtitles. | blocked: no browser candidate |
| TS/module safety | Run a standalone no-emit TypeScript check, not only Next build; inspect all changed imports/identifiers for TS2304/TS2552/TS2307-class failures. Lint/test/build results must name candidate and command; differentiate baseline failures from new failures. | blocked: candidate pending; installed dependencies available |
| Tests prove invariants | Tests must exercise delayed/stale actual hook state, forged authority through BFF, immutable replay body/key pairing, 409 draft retention, 410 body clearing, exact source references and DTO projections. Checking strings/shape alone cannot establish these behaviors. | blocked: tests pending |

### Reverse-review probes

Before bounded acceptance, assume each regression occurred and identify the actual evidence that would fail: another account sees the prior account's source; a lost create acknowledgement produces two records; a conflict discards the draft; a late pre-delete response restores erased text; an unavailable historical revision is rendered from a prior object; member cannot reach Memory; browser-supplied actor replaces server identity. Missing detection remains an evidence gap rather than a manufactured code finding.

## Next16 local guidance and frozen BFF test oracle — 20:46 +08:00

**Disposition: pass for local-document reading only.** Developer remains running. No unfinished implementation was audited, executed, interrupted or accepted in this follow-up. Frozen source conventions were read with `git show 9cd93ec:<path>`; the operative API contract hash remains unchanged.

All documentation paths below are relative to `apps/web/node_modules/next/dist/docs/01-app/`:

- `01-getting-started/15-route-handlers.md`: supported methods, noncached default Route Handlers, route resolution, optional Cache Components behavior and generated route-context types.
- `03-api-reference/03-file-conventions/route.md`: HTTP methods, promise `context.params`, cookies/headers, route configuration and version history. Unsupported methods return framework 405; automatically supplied OPTIONS is framework behavior, not an implemented memory operation.
- `03-api-reference/04-functions/cookies.md`: asynchronous cookie reads, request-time behavior, and mutation/deletion restrictions. The existing server-session helper must execute in a valid route request context; a fake-session helper unit test does not exercise signed-cookie verification.
- `03-api-reference/04-functions/fetch.md`: browser HTTP cache versus server persistent cache, explicit `no-store`, conflicting cache/revalidate options, memoization exclusion for Route Handlers and development-only Server Component HMR caveat. HMR guidance is not evidence that a BFF caches private data.
- `02-guides/caching-without-cache-components.md`: relevant default, route-config and render-pass deduplication sections. Frozen `apps/web/next.config.ts` does not enable `cacheComponents`; its output is standalone. No new framework cache configuration is prescribed.
- `02-guides/backend-for-frontend.md`: public endpoints, forwarding/request-body handling, upstream and response header boundaries, validation, credential checks, sensitive-error suppression and runtime limitations.
- `02-guides/authentication.md`: Authorization, DAL, layout partial-render caveat and Route Handlers. Secure authorization belongs close to data access; hiding controls or checking a layout does not establish it. The guide's example admin gate/403 is generic; this feature's member/owner and nonenumerating API contract governs.
- `03-api-reference/04-functions/next-response.md` (`next()`): explicit safe-header subset and avoidance of copying incoming credentials into upstream or outgoing client responses.

Frozen source reinspection covered `apps/web/src/lib/auth/server-route.ts`, `apps/web/src/app/api/workspaces/[workspaceId]/model-settings/route.ts` and `apps/web/next.config.ts`. It confirms the existing session-derived actor convention, promise params, explicit upstream no-store and response cache header. Additional headers are spread after trusted headers in the existing shared helper, so the memory caller's bounded header construction is a concrete upcoming test target. No shared-helper edit or current-candidate defect is implied.

### Prepared BFF assertions, not executed tests

| Probe | Required observation and evidence level |
|---|---|
| Route context and authentication | Exercise actual handler methods with awaited params. Missing/invalid session cannot reach private upstream requests. An injected session double proves only unit wiring; signed-cookie → Next handler → real API requires separate runtime evidence. Every private endpoint including source and operation polling authenticates. |
| Spoofed browser authority | Send mixed-case actor/internal-token headers and unrelated authorization/cookie headers, plus forbidden body identity fields. The upstream actor/internal auth comes solely from server state; caller values never override it or return in response headers. Unsupported JSON fields cannot be silently dropped into an otherwise successful write. Session credentials stay server-side. |
| Bounded forwarding | Only declared paths/methods/query fields and the exact supported body reach the configured API origin. No browser-chosen destination, generalized arbitrary proxy, source-URL resolver or credential-bearing redirect continuation. Static requests/operations paths are exercised separately from record-ID paths. Unknown operations cannot produce fabricated receipts. |
| Mutation and replay fidelity | Capture forwarded method, path, Idempotency-Key and parsed body across initial send/retry. Preserve requestId, expectedVersion, exact content/condition strings and null/default semantics; do not trim, infer or mint retry identity. DELETE includes its JSON body. Original pair/body stability is observed in the client plus BFF chain. |
| Error and uncertain outcome | Distinguish upstream contract errors from local session/validation and network failures. Preserve safe code/status/requestId/currentVersion rules from the actual API; no raw exception, reflected text or credentials. A transport failure after possible dispatch cannot prove rollback or invent completion. Poll 404 remains only a point-in-time observation. API mixed-error precedence is tested at the API boundary; local BFF responses are labeled separately rather than represented as backend responses. |
| Cache boundaries | Assert explicit upstream `cache: no-store` and private response cache policy across success and relevant error paths. Inspect actual HTTP headers and consecutive requests by two actors; a unit fetch-options assertion alone cannot establish browser/proxy isolation. No framework persistent private cache or replay-body singleton is justified by render-pass memoization examples. |
| Serialization | Tombstones, unavailable revision bodies, content-free operation polling, successor receipts and exact source/version/hash remain faithful to the contract. Malformed/non-JSON upstream responses produce safe failure with truthful mutation uncertainty; they cannot become an empty successful list or saved receipt. |

These assertions are preparation for the original developer's candidate tests and independent review. Fixture unit/E2E, real backend API, and visible workspace → Settings → Memory walkthrough remain separate, unexecuted acceptance classes. No install/build/test count changes their disposition.

## In-progress developer observation — 20:34 +08:00

After baseline preparation, new untracked `apps/web/src/lib/memory/` files (`activation.ts`, `client.ts`, `errors.ts`, `proxy.ts`, `server-route.ts`, `types.ts`, `validation.ts`) and memory/source BFF route directories appeared. No Memory component or candidate-ready handoff was present in the inspected paths. These are concurrent developer-owned changes, untouched by this reviewer. Their appearance does not establish a reviewable completed candidate; the baseline statements above refer to the initial clean tree. Installed Next16 docs were still absent at this observation.

## Evidence ledger and integration handoff

| Evidence class | Observed result |
|---|---|
| Static baseline/contract | Inspected source files above; full v4 spec and exact contract/review read; starting SHA and contract hash verified. No candidate judgment. |
| Fixture unit/component tests | Not run; no candidate supplied. Future results remain labeled fixture. |
| Fixture/mocked browser E2E | Not run. Future route interception, fake auth or API stubs remain labeled fixture and cannot satisfy real acceptance. |
| Real API/network/manual workflow | Not run. Backend APIs remain in development. Exact integration SHA/runtime origin and disposable test identities must be supplied through controller handoff. No arbitrary existing service or old tree will be used. |
| Real visible browser | Not run. No screenshot, real Memory interaction or browser network result is claimed. |
| Full #46 | Open. This slice does not cover later compaction status, chat/Research continuation, refresh/recovery or complete end-to-end paths. |

Commands executed for preparation included `python D:/Code/dev-workbench/scripts/prepare_session.py --repo-path D:/Code/citeframe-lanes/issue46-management-ui`, `git rev-parse HEAD`, `git status --short`, `git status --porcelain=v1`, `git diff --stat`, read-only remote/local/global identity checks, `Get-FileHash` on contract/spec, and targeted source/doc inventories. These are baseline evidence only.

The real-path gate requires a running candidate frontend connected to the actual integrated management API with unchanged auth/membership dependencies, authorized synthetic accounts/workspace, and no model use. Walk through visible workspace → Settings → Memory for empty list, exact create and refresh, source, history, correction/successor, stale 409 recovery preserving draft, inactive, deletion/410, lost-ack polling, user/workspace changes and access revocation. Record bounded screenshots plus sanitized method/path/status/request-body or response assertions without cookies/internal tokens. Repeat key reading/actions at mobile width. Preserve a before/after visual baseline where the existing Settings shell changed. Fixture success alone leaves this gate blocked.

The current collaboration inventory exposes only this reviewer root; the external developer ID cannot be messaged from this inventory. Controller must relay candidate-ready status and original-developer rework. No replacement reviewer/developer was spawned.

Write-back check: durable verified preparation is recorded solely here. No private memory or shared workbench writes are appropriate under this lane ownership. The next review updates this same artifact with the candidate identity, severity-ordered concrete findings (if any), commands, evidence scope and bounded disposition.
