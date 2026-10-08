# Critical review: #42 manual credential admission

**Current status: APPROVED — exact finite policy; original developer may implement. R001 closed. Implementation/runtime/activation acceptance remains pending.**
**Reviewer:** original replacement #42 Critical reviewer.
**Date:** 2026-09-28.
**Reviewed HEAD:** 492624c1f36e17f94f7e5010bf9e374edc40ec2c.
**Contract:** specs/v5/memory-management/lanes/issue42-admission.md.
**Contract SHA-256:** 9a8d943a39ade6b224e9a21a6b9ff0485e9f3b7963094e21868441ad64dc2693.

The initial review below is retained as history; its R001 blocker and pending-policy verdict are superseded by the exact-policy recheck at the end of this file.

## 1. Verdict and scope

The neutral deterministic approach is feasible. Its five named category families, stable payload-free error, exact-source preservation and explicit detection limits are appropriate for this pre-activation correction. **Exact matching-policy approval is withheld until R001 is resolved.** The current contract names categories but does not yet define the promised finite rule inventory. This finding concerns the new admission contract only; accepted P1a, IR1–IR6 and existing runtime evidence remain intact.

Reviewed actual MemoryCommands._mutate, MemoryConditions/MemoryStatement/MemoryError, WorkspaceAccess and design sections 3.2, 5.1–5.2 and 7.1. No architecture repeat, product implementation, migration, database execution, model call or Git write occurred. The requested lane contract and review paths are the bounded artifacts for this review; no wider spec/task regeneration is needed.

## 2. R001 — exact finite matching inventory required before implementation

**Priority: blocking exact-policy approval.**
**Target:** lanes/issue42-admission.md, paragraph beginning “Supported positive rejection categories”.

“Credential-bearing”, “clearly labeled”, “password-bearing” and “recognized provider-token/key shapes” leave materially different matchers possible. Chinese labels, provider formats, token lengths, boundaries and assignment grammar are not enumerated. A reviewer cannot yet identify precisely which synthetic inputs must reject or remain accepted.

**Required correction:** the original developer should append an auditable rule table to this contract before affected product edits. Each enabled rule needs a stable rule ID, exact regex or equivalent deterministic parsing grammar, matching flags/boundaries, a synthetic positive fixture and a nearest negative fixture. One small inventory is sufficient:

| Already-authorized family | Definition needed |
|---|---|
| Private-key PEM | Exact supported BEGIN/END labels; whether a header alone, truncated block or complete paired block triggers; public-key/certificate controls. |
| Authorization/cookie headers | Exact header names and supported schemes/value grammar; line/embedded-header anchoring, casing, whitespace and empty-value treatment. Define Cookie/Set-Cookie coverage explicitly rather than infer all session-token forms. |
| Labeled assignments | Exhaustive English and Chinese label aliases; delimiters, quoting, value boundaries and minimum/nonempty value rule; casing/Unicode matching policy. Ordinary token counts must not enter a generic “token” secret rule. |
| Password-bearing connection/URI text | Exact supported URI/connection-string forms and schemes, user-info/password boundaries, escaping/percent-encoding behavior. Explicitly list any unsupported connection-string forms. |
| Recognized provider shapes | Exact enabled formats: provider/format identity, prefixes, alphabet, length bounds and surrounding boundaries. No open-ended “looks like a key” entropy/length heuristic. If none are defined, explicitly mark this family unsupported for this revision. |

Also define scanning over the three existing text fields independently: content, conditions.subject and conditions.applicability. State whether case folding, Unicode normalization or decoding occurs for detection; source bytes/text must remain unchanged. Do not add normalization or recursive decoding implicitly.

**Important negative-control boundary:** credential discussion without a supported credential value should remain accepted. A phrase such as “do not use” must not suppress a supported embedded credential match. Quoted examples/code containing a matching synthetic value are still matches under a lexical policy unless a narrowly defined exception is explicitly approved. Public certificates or ordinary preferences elsewhere in the same input must not override a private-key match. This avoids introducing a semantic classifier through a prose exemption.

**Closure evidence:** refined contract at a pinned hash with the complete inventory and boundary fixtures. The reviewer can then approve that exact finite policy before implementation. No universal secret/PII-detection claim is required or permitted.

## 3. Integration constraints validated against current code

These make the existing “preserve ordering” requirement executable; they do not authorize new request/schema behavior.

1. Retain current request-ID/key/version structural validation and authorization precedence. Invalid membership, archived workspace, shared purpose/audience and another owner's target must retain existing denial behavior before admission reveals anything about a proposed statement.
2. Preserve the current authorized idempotency lookup: mismatched request digest remains idempotency_conflict; a matching committed request retains its existing receipt path. Do not retroactively turn committed replay into a new admission failure. Reconcile remains unchanged. Existing persisted-data remediation is outside this new-submission correction.
3. On the fresh-operation branch, resolve/lock the target, check expected version and terminal state as today, then run admission for remember/correct **before constructing/adding/flushing MemoryInstruction**. In correct, it must also precede predecessor supersession or successor creation. Validating in _create is too late because _mutate already flushes the instruction first.
4. A rejected fresh submission raises MemoryError with exactly sensitive_content_unsupported. No matching text, field value, span, digest or raw body enters exception arguments/messages, diagnostic events or receipt. No rejected operation/candidate/source/revision is persisted. The existing transient in-memory request digest need not be removed; it must not become rejection output or stored failed-operation metadata.
5. Deactivate/delete remain usable and do not re-scan historical text. Clean authorized commands retain exact stored content/conditions, source attribution, CAS, lost-ack recovery and commit-before-receipt semantics.
6. Keep one stdlib-only deterministic admission module and one shared command integration. No model/classifier/network/third-party scanner, API-side clone, new DTO/DB field, provider change or shared-private reuse.

## 4. Required implementation evidence after exact-policy approval

- Table-driven positives and nearest negatives for every approved rule; each positive placed separately in content, subject and applicability, with the other fields clean. Cover boundary lengths, casing/newlines, quotes and only the explicitly supported encoding behavior. Use synthetic values.
- Assert exact exception type/code and payload-free args/string/repr/captured logs; no returned receipt. No debug printing or exception chaining containing the match.
- Real disposable PostgreSQL: compare all six memory tables before/after rejected remember and rejected correct, including existing predecessor head/revision/support state. Observe executed DML so rollback-only “no rows remain” cannot substitute for validation-before-write evidence. Reconcile rejected request remains absent; corrected clean draft can reuse the unconsumed request identity.
- Parity matrix: clean remember/correct and exact source fidelity; unauthorized/non-owner/shared contexts; stale CAS and terminal target combined with matched text; committed exact replay/lost acknowledgement; changed-body same-key conflict; concurrency/successor invariant where touched. Preserve error precedence.
- Neutral imports with API/Worker unavailable; bounded matcher work under the existing 4000/256/2000 text limits and adversarial near-matches, with no pathological regex backtracking.
- API 422 mapping and body-safe HTTP/log behavior remain separate future integration evidence. No mounted API or UI acceptance is claimed here.

## 5. Gate summary and handoff

| Review area | Status |
|---|---|
| Five bounded category families and deterministic approach | Feasible / approved in principle only |
| Exact supported matching policy | **Blocked by R001** |
| Stable code, source fidelity, privacy and honest limitations | Design pass; implementation evidence pending |
| Auth/CAS/idempotency integration | Feasible at the explicit pre-write point above; implementation evidence pending |
| Schema/request-shape changes | Not applicable; none authorized |
| Universal sensitive-data/semantic-confirmation guarantee | Explicitly excluded |
| Existing P1a acceptance | Retained; no re-review |
| Runtime/PG/API/UI acceptance for this correction | Not run / not granted |

Next handoff is the original developer's finite rule inventory in the existing lane contract, followed by exact-policy re-review. Original developer remains the implementation owner; Management API consumes the integrated neutral error and does not clone validation.

Durable write-back is this new review only. No private/global memory, original implementation review, canonical #40 workbench, product, test or Git state was changed.


## 6. Exact-policy recheck — APPROVED, 2026-09-28

**R001 CLOSED. No new boundary finding. Explicit implementation go-ahead to the original #42 developer for this exact finite predicate and insertion point.** This approval covers the admission module, smallest shared remember/correct integration and dedicated tests/evidence already authorized by the lane contract. Create/correct API activation remains gated on actual implementation acceptance and exact integration; separately progressing read/query surfaces are outside this review.

### Approved identities

| Artifact | SHA-256 |
|---|---|
| lanes/issue42-admission.md | 6fd16d80c32e7c4205d1d97c408347232070c2ccb218a3a91ab044400597f60c |
| evidence/issue42-admission-rules.md, incorporated by the contract | 35b19edf1889cb4ce37cad912154e50085f860e3141e87c348676cb1e2abf8fc |

HEAD at review remains 492624c1f36e17f94f7e5010bf9e374edc40ec2c. The policy artifacts are working-tree documents; HEAD alone does not identify this approval. Both file hashes were rechecked immediately before this review update. The incorporated proposal's actual hash matches the contract pin. Inventory and boundary-fixture sections duplicated in the two documents are text-identical.

### Exact matching disposition

- **R1 pass:** six explicitly enumerated, case-exact, same-type complete PEM pairs with non-whitespace body. Empty/truncated/lowercase/mismatched blocks are expressly outside this predicate. Public material cannot exempt a separate supported match.
- **R2 pass:** exact two authorization headers/two schemes, ASCII boundaries, eight-character minimum, padding and terminal delimiters are defined. Cookie/Set-Cookie grammar intentionally examines the initial nonempty pair, includes ordinary cookies and does not claim to detect a later pair after an empty first value.
- **R3 pass:** finite English/Chinese labels, all three assignment separators, matched quotes, bare-value terminators and ASCII identifier boundaries are defined. Multiword unquoted discussion is outside the bare-value grammar. Synthetic/example/negated assignments that match are still rejected; no semantic or placeholder allowlist.
- **R4 pass:** fifteen schemes with explicit user/password/host character exclusions and a scheme boundary. Percent escapes remain literal; empty-password/username-only, other schemes, encoded whole URIs, query-only credentials and nonmatching DSNs are not claimed by this rule.
- **R5 pass:** four bounded lexical shape expressions and full-token boundaries are explicit. The optional OpenAI-style prefix overlap is deliberately documented: sk-proj- or sk-svcacct- followed by 31 body characters still matches the plain sk- alternative. Each documented 257-character optional-prefix body is overlong and does not match. No authenticity/vendor-completeness inference follows.

All rules search each field independently; content, subject and applicability are not concatenated. ASCII-only insensitive labels/schemes/headers, exact token bodies, whitespace classes and literal backslash handling are specified. No normalization, decoding or rewriting of submitted/stored text is authorized. Any supported match rejects; surrounding discussion, negation, quotes, examples or public-key material do not cancel it.

**Independent policy check:** compiled the four R5 expressions directly from the contract in memory with their stated full-token boundaries; 57 assertions verified lower/exact/upper lengths, prefix-case and identifier boundaries, negated/quoted matches and the documented optional-prefix overlap. All passed. These are contract-regex checks, not production implementation tests. R1–R4 received grammar/fixture consistency review; no production matcher exists in this evidence.

### Auth/CAS/idempotency placement — approved

The incorporated proposal explicitly preserves current structural validation, workspace/member/private-owner authorization, operation replay/conflict lookup, target ownership, expected-version CAS and terminal checks. Admission runs only for a fresh remember/correct, immediately before the first MemoryInstruction is constructed, before any add/flush, predecessor supersession or successor creation. Both commands use the same predicate.

Committed exact replay retains receipt reconstruction under current authorization; changed-body keys retain idempotency_conflict; stale/terminal corrections retain their existing errors before admission. Rejected new submissions persist no operation or request digest and leave their request/key reusable with edited safe text. Reconcile, deactivate/delete and historical data are not retroactively scanned.

Only MemoryError("sensitive_content_unsupported") is emitted on a match. No matched value, rule result, source text, span, digest, failed-operation payload or diagnostic body is authorized. Existing transient request hashing stays unchanged.

### Implementation and activation gates retained

The original developer may now implement against the two approved hashes above. Subsequent review must verify the actual predicate matches this inventory; unchanged source storage; exact stable error and payload-free logs; real PostgreSQL six-table before/after equality plus no attempted DML on rejection; preserved authorization/CAS/replay/lost-ack and successor behavior; neutral imports; and bounded matcher behavior. The pending unit fixture expansions and PG tests are not claimed as executed here.

API must consume the integrated neutral validator/error without cloning the predicate. No schema/DTO/request-shape/provider/compaction change, model classifier or shared-private reuse is approved. Any matcher expansion or exception outside this inventory needs an explicit matching-policy delta.

Prior P1a acceptance remains intact. No broader core audit, product/test edit, PostgreSQL start, Git write or provider/model call occurred. Only this admission review was updated; durable write-back remains here.
