# Controller management API acceptance

Independent implementation review closed M42-I1 with exact router/service/test hashes in reviews/issue42-management.md. This controller inspected the new router/service, the two-line main registration and scoped CI changes, then ran an independent disposable PostgreSQL17.11 cluster at loopback56742 in `.local-runtime/controller-management/data`.

Actual controller evidence: all56 dedicated management tests passed in19.04s; complete Alembic upgrade through t4b5c6d7e8f9 passed; real socket HTTP to full ai_pdf_api.main on56743 passed76 lifecycle/security/replay checks. The submitted live_http.py assertions were unchanged; only output/log destinations were redirected in memory to controller-owned scratch. Sanitized method/path/status results are controller-live-http.json. No paid model, fixture HTTP interception, auth/member override or production database was used for socket checks. TestClient/realPG tests remain distinct from liveHTTP evidence. Own API stopped; exact own PostgreSQL cleanly stopped and pg_isready returned no response.

The earlier broad Windows API result1011passed29failed9skipped remains non-green. Independent evidence identifies checkout-byte/provenance and environment problems; no historical hash, test or production artifact was weakened. Hosted Linux CI is a required independent gate.

This is bounded API acceptance only. The branch contains exact unmerged PR47 permission prerequisite and PR48 core/admission dependency. Draft delivery may proceed; merge requires both prerequisites, updated hosted gates and controller integration checks. The management UI, actual visible-page walkthrough, shared source/search, Chat/Research automatic compaction and full#41 remain unaccepted.

The raw pytest-full-api.txt artifact retains original runner whitespace and its manifested hash. Staged whitespace verification excludes only that raw transcript; product/tests/docs pass the check.
