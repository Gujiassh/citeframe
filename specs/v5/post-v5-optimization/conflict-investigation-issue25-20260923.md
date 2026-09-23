# Issue #25 conflict investigation

## Implementation checkpoint

Worktree: `D:/Code/citeframe-conflict-investigation`. Branch: `work/issue25-conflict-investigation`.
Base: stacked #29, initially `de66244a50a046897f688c2e490e634638237c35`; updating normally to `5bfee6a0f9a7d8466d72b11a961cc5446fa7bca1`. No canonical or architecture checkout writes. The repair1 frozen 1,989-file overlay was verified against embedded input pins and the remote base (only line endings differed) before implementation; overlay content is not a #25 commit.

The candidate adds frozen workflow v4/Agent IO v3 and an explicit investigator role. Gate operations persist input/result hashes, original sources, inspection conditions, revisions and separate verifier/critic outputs. Each external operation is reserved before dispatch, bounded to three inspections/two supplemental searches; retries replay completed records. Ambiguous external outcomes stop unresolved without redispatch. Gate completion requires a persisted outcome. Historical claims remain original; verified corrections have separate IDs and original/evidence relationships in the investigation journal and report. Unresolved outputs include checked sources, queries, stop reason and gaps.

The API exposes typed investigation state and Web displays sources, known/unknown conditions, original and corrected conclusions, queries and gaps. Original/user-edited report semantics remain unchanged.

Migration `r2f3a4b5c6d7` follows #23 `q1e2f3a4b5c6`. The p0 installer uses frozen `alembic/release_data/research_v3.json` instead of importing current release defaults; r2 also freezes its v4 seed. Old v2/v3 manifests/readers are retained.

## Evidence and remaining gates

This is an implementation checkpoint, not acceptance. Initial deterministic Worker investigation tests: 11 passed. Initial persistence tests: 8 passed, one cancel fixture setup failure being corrected. Broader API/Worker tests exposed version-default fixture assumptions and Worker prompt projection updates; fixes and reruns are in progress. TypeScript check passed once. Logs, input pins and pre-change manifest are in worktree-local `.local-issue25/` and excluded from commits.

No paid provider or credential files used. No service listeners found on 3000/8000/5432/9000 and no docker/psql/pg_ctl command available on PATH. Real PostgreSQL, process restart, migrated API/Worker/object-store and visible service-backed UI acceptance remain blocked. Deterministic fixtures do not establish real retrieval quality. CI, independent Critical review and exact-head runtime evidence remain required; PR must stay draft and no merge is authorized.

Next: incorporate upstream #29 normally, finish persistence/migration/runtime/DTO/UI regression coverage, verify delta scope, publish stacked draft closes #25 and hand to Hubble. Subsequent prerequisite updates must be merged normally and relevant regressions repeated.
