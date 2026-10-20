# Private instruction management in Settings

The web feature adds Memory under workspace Settings for members and owners. Evaluation remains owner-only. Memory uses the owner-private API described in [Private instruction management API](private-instruction-api.md).

## Records and corrections

The panel provides status-filtered lists, pagination, refresh, creation, current records, revisions, and exact instruction-source reads. It supports correction, deactivation, and deletion. Correction drafts preserve the full statement, including kind, conditions, pin state, and expiry. There are no separate pin-only, expiry-only, reactivation, extraction, or search controls.

A version conflict retains the correction draft. The user explicitly selects a possible successor and compares it with the original record. The comparison checks the exact backward `supersedesId` chain within eight edges and nine reads. Adopting a target repeats that proof and performs a final target read within ten reads. Adoption changes the correction target. A separate Save submits the retained draft against the target's current version. A changed proof requires another comparison.

## Request identity and uncertain results

Each mutation retains one method, path, body, request ID, and idempotency key. An uncertain response keeps that immutable command pending. Content-free request or operation polling observes its state. A missing request lookup does not establish rollback or release the pending command. Retry explicitly sends the original command. There is no automatic resend with a new identity.

Receipts distinguish the original mutation's result version from the currently authorized resource version. Pending-command state can survive Home and Back within the active session provider. The provider keys state by actor and workspace. Epochs and request generations guard asynchronous completions. Logout and observed revocation trigger protected-state cleanup.

## Private data and unavailable content

Available responses must match the current actor, workspace, and private scope. Unavailable responses carry lifecycle metadata without semantic fields. Unavailable-state filters suppress affected protected views after observed erasure, source loss, or revocation. Local drafts and unresolved command bodies remain component or provider state. The feature adds no private-body URL, localStorage, or sessionStorage persistence.

Private instructions from every owner, including the requester, remain excluded from shared Chat and Research prompts, tools, summaries, checkpoints, planning, and derived outputs. Settings management grants no shared-source or evidence authority.

## Browser-to-API proxy

Fixed Next route handlers use the existing signed server session and server-owned API headers. Browser actor and credential headers are not forwarded as authority. The proxy validates methods, identifiers, query parameters, bodies, idempotency keys, and returned DTOs. It refuses upstream redirects and applies private `no-store` responses with `Vary: Cookie`.

After session lookup, non-GET requests compare a supplied `Origin` with the validated incoming `Host` authority and the scheme from the framework request URL. `Forwarded`, `X-Forwarded-Host`, and `X-Forwarded-Proto` do not select the expected origin. Default HTTP and HTTPS ports canonicalize through `URL.origin`. A single terminal DNS root dot is retained, so dotted and undotted DNS origins remain distinct. A supplied Origin requires a valid Host. A malformed present Host or `Sec-Fetch-Site: cross-site` rejects the request. Requests without Origin retain the existing compatibility behavior. The ingress must preserve the intended Host and framework URL scheme. Signed-session and upstream ownership checks retain API authority.

Non-GET bodies are limited to 65,536 raw bytes. The reader rejects the first overflowing chunk before decoding it, cancels incomplete reads, and releases its reader. It does not wait for an unresolved producer cleanup promise. A single delivered chunk or producer queue can already consume memory outside this bound. The reader adds no deadline for a stream that remains below the cap without ending.

JSON syntax is checked before session lookup. Structural validation follows session lookup. Admitted input retains the existing JSON parse and serialization behavior. The upstream request has a 20-second timeout. Fixed error codes replace upstream diagnostic text. Failed mutations with uncertain outcomes remain pending recovery cases.

The feature manages explicit owner-private instructions. Native model dispatch, compaction, generic history search, index activation, image activation, and complete private-memory integration remain separate components.

This reference describes the implementation. Signed-session browser behavior against the API and PostgreSQL, including late-response and unknown-outcome races, requires integrated visible-browser verification. Full issue46 and issue42 completion remain separate acceptance.
