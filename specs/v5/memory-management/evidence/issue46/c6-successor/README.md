# C6 successor recovery — static implementation candidate

Base: `6ccd8d8a1de7afeb2c8edb0f3f07d0b9cf0a38e8`.
Branch: `work/issue46-memory-management-ui`.
Approved contract: `../../../lanes/issue46-successor-recovery.md`, SHA256 `7B3E17EBB977CEFF298EAD762C8BCF49111E989075D404CE47603F81D55E8BFA` (original contract bytes unchanged).

## Candidate identity

- `candidate-manifest.sha256`: **60E1DFC70C24E47538C59424E2210F80B7E3B7A156C8957CDF06ED28839D06AC**; all41 product/test paths, including4 new files. Sorted POSIX path + space + uppercase file hash, UTF-8 LF joined without trailing LF.
- `tests.sha256`: **F0E353842678423A342D84EFFDE802CB9575889737B897BC017F70914CCC7367**; all9 unit/E2E source files. These hashes identify definitions, not executed browser evidence.
- Eleven paths differ from C5:9 product/pure-test files plus2 E2E definitions. Existing layout, session provider/state, Workspace/auth, settings entry, BFF/client/DTO/API/backend remain unchanged against C5 manifest where represented. No ownership expansion.
- C4 and C5 historical manifests remain unchanged. Original reviewer artifact is read-only to this lane.

## Implemented behavior and boundaries

The feature owns one complete controlled Statement draft above keyed record detail. Original predecessor, target and last attempted target are distinct; definitive correction events are correlated by scope epoch, draft generation, POST/path/requestId. Generic PATCH409 cannot retarget the draft. Successful lifecycle completion clears any retained correction draft; ordinary failure preserves it.

Explicit paged-list selection proves a backward supersedesId chain to the original predecessor, at most8 edges/9 distinct records/9 actual current GETs. Explicit adoption repeats that bounded proof plus one final fresh candidate GET, at most10 actual GETs. Checked projections supply detail views without hidden duplicate current reads. No automatic discovery, pagination, mutation or identity creation occurs during selection/comparison/adoption. A separate Save allocates the next pair and submits the exact retained Statement at the adopted ID/fresh CAS.

Comparison includes all optional fields and exact source tuples. Authorized comparison changes require another explicit adoption. A changed final supersedesId invalidates the proof; the user must explicitly select again, with no follow-link beyond the request budget and no unproven relationship presented as accepted.

List ingestion, current/history/source invalidation and definitive target denial clear participant recovery data. Once a candidate has been chosen, privacy clearing also clears selected comparison and aborts its work, preventing an extra automatic current GET after the bounded action. Body-free list rows remain; explicit reselection can retrieve safe current lifecycle/history metadata. Ordinary pre-conflict source suppression retains the existing body-free lifecycle path. True erased410 is not restored. Unknown pending commands retain their immutable original protocol internally until resolved; source-read failure does not prove mutation failure. Existing actor/workspace/logout/revocation provider fencing remains unchanged.

## Executed evidence

Developer-lane root verification: the following commands were executed by this development lane's `/root`, separately from its implementation workers. These logs provide developer verification only; they do not record external-controller execution or the designated independent reviewer `agt_248928e8`'s verification.

1. Whole-web strict `tsc --noEmit --incremental false`: exit0, `typecheck.txt`.
2. ESLint for all memory components/lib, i18n and both memory E2Es: exit0, `lint.txt`.
3. Strict compilation of all7 memory unit source files into isolated ignored `apps/web/test-results/memory-successor-main-unit`: exit0, `unit-compile.txt`.
4. Node pure tests from that output: **40 passed, 0 failed/skipped**, `units.txt`. Includes29 retained tests and11 new recovery rules/budget/correlation/adversarial tests. Readers/fetches are in-process synthetic doubles, not real API evidence.

An initial `tsx` CLI test startup exited1 before running tests: `SystemError [ERR_SYSTEM_ERROR]: ... uv_os_get_passwd returned ENOMEM (not enough memory)`. Exact output is retained in `units-tsx-startup-error.txt`. The successful run uses the existing standalone TypeScript compile + Node test method. This startup failure was not a browser/network/runtime permission test; no denied operation was retried.

## Authored, unexecuted browser assertions

- Real API correctionPOST409, complete retained draft, explicit distinct-successor comparison/adoption, no intervening writes, separately explicit resave with new identity/fresh successor CAS and another new successor ID.
- Exact predecessor history/source and current/history/source refusal after deletion.
- Existing Home/Back unknown original-triple and real-upstream held-poll revocation definitions.
- Realistic intercepted successor fixtures for optional fields, repeated conflict, unrelated/foreign/cyclic/terminal candidates, participant list/current/history/source loss, source/scope races, selection9/adoption10 network counts and original-predecessor history/source reads without target changes.

Neither E2E suite was executed. Pure tests do not execute the React hook/navigation lifecycle; hook race and visible-control evidence remains authored/static only. No actual API/BFF lifecycle, visible screenshot or usable UI acceptance is claimed.

## Remaining gate / handoff

Return this exact candidate to the original independent reviewer for implementation review. Design approval and C3/C4 bounded passes do not approve the new implementation. Original reviewer is outside the exposed collaboration inventory; controller relay is required. No substitute reviewer was started.

Browser/network/service/stop restrictions remain. No runtime launch/shutdown, fonts change, build rerun, Git/model call, commit or push. Last production build limitation remains Geist/Geist Mono fetch failure; no new build pass. Actual visible Next BFF + accepted API/PG recovery walkthrough remains blocked pending restored authorization. #46/#41 and later compaction/continuation status UI remain open. This is a static candidate for review, with no publishing conclusion.