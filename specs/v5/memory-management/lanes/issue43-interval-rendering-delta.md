# Issue43 interval rendering and dispatch profile amendment

Status: revised exact internal-persistence contract, pending original-reviewer/controller approval. This revision addresses P43-I1/P43-I2; it grants no implementation approval. No table, column, migration, shared provider ABI, native source kind, native writer, adapter or router change. Selected Option A and the separately approved native-lifecycle amendment remain unchanged. The single product owner remains the bounded core implementation lane.

## 1. Existing mismatch and interim boundary

The planner selects intervals after protected current-request units. Existing cumulative prefix coverage alone cannot reconstruct raw units before those intervals. The current nonzero-start refusal `checkpoint_interval_metadata_required` stays in force until this exact contract is approved and implemented; that refusal cannot be final delivery of P43-A1. Existing reservation/send profile checks also need durable equality on recovered unadopted results and their adoption.

## 2. Exact immutable JSON meanings

Only existing `memory_calls.input_manifest` and `result_manifest` JSON meanings change. Canonical SHA-256 uses the existing canonical JSON encoding/digest; hashes below are lowercase-or-uppercase normalized hexadecimal SHA-256 values compared by value, with no inference or default fields.

### Provider dispatch input

`input_manifest.schemaVersion = compaction-input-v2` retains exact `capture` and `policy` and requires `dispatchProfile`:

- `schemaVersion = compaction-dispatch-profile-v1`;
- `provider`, `protocol`, `model`, `configFingerprint`;
- `contextWindowTokens` (physical model context), `maxOutputTokens` (physical connection output ceiling), `inputCeiling` (configured input cap), `safetyMargin` (explicit nonnegative reserve);
- `counter = {counter_id,counter_version,mode,config_fingerprint}`;
- `watermarks` = the complete exact existing CompactionPolicy object.

Identity comes from the actual frozen connection/counter/policy. Provider must equal the native reservation provider; counter metadata must match actual counting. Strict types, complete fields and exact versions are required; missing/malformed/version-mismatched data rejects. No endpoint, credentials or provider secrets are stored. Exact request output reserve stays bound by immutable GenerationRequest hash and reserved-output count. Current hard capacity is recomputed from physical context, configured cap, request output and safety; physical output ceiling is separately enforced.

Summary calls additionally require these two distinct code-owned objects:

1. `compactionPlan = {schemaVersion: compaction-plan-v1, intervalStart, intervalEnd, protectedUnitKeys}`. This is the episode aggregate replacement plan. Indices are strict integers, `0 <= intervalStart < intervalEnd <= len(capture.units)`. Protected keys are unique known original-unit keys in original order, preserve prior protected keys, and cannot occur inside the selected interval. The aggregate interval must extend the previous cumulative dependency frontier at adoption. That frontier-extension condition does not apply to each chunk subset.
2. `summaryInput` has exactly one of the following shapes:
   - Chunk: `{schemaVersion: compaction-summary-input-v1, kind: original_units, originalUnitKeys: [...]}`. Keys are a nonempty, ordered, contiguous complete-unit slice of the aggregate interval, without duplicates. They resolve only against that immutable capture's original units and exact source versions/tool-group identities. The physical chunk request contains exactly that slice's attributed original payloads, with no other source bodies. System summary instructions grant no support authority.
   - Merge: `{schemaVersion: compaction-summary-input-v1, kind: child_results, children: [{callId,resultSha256,inputManifestSha256}, ...]}`. Entries are a nonempty ordered list of distinct succeeded, valid `compact_chunk` results from this same episode/capture/profile/plan. `resultSha256` equals both the child's existing stored result hash and the canonical hash of its task-memory-v2 summary; `inputManifestSha256` binds the child's entire immutable input manifest, including its exact descriptor. Child order is original-unit order. Missing, changed, foreign, invalidated or mismatched children reject. No merge-of-merge recursion is permitted. The merge request contains exactly those authenticated child summaries in that order; original-unit mapping remains in their descriptors.

Descriptor lengths, serialized bytes, chunk count and merge fan-in obey the existing capture/manifest/summary policy caps before dispatch or loading; no truncation is allowed. Immutable request archive/hash remains exact physical-payload evidence. Request construction must derive payloads from the descriptor and verify their ordered identity; descriptor metadata alone does not establish which bodies were sent.

### Summary result

`result_manifest = {schemaVersion: compaction-result-v2, summary, compactionPlan, summaryInput, finalEligible}`. `summary` retains task-memory-v2. Plan and descriptor are exact copies of validated immutable input metadata. `finalEligible` is a strict boolean computed by code using section 3, never accepted from model output. Existing `result_sha256` remains canonical hash of `summary`; it is not repurposed. Consumers also compare full input/result plan and descriptor equality and recompute eligibility, so that summary hash alone cannot authenticate changed metadata.

Metadata-only accounting/tool archive records keep existing non-dispatch manifests; absence of required dispatch metadata never grants provider-send or summary-adoption authority. GenerationRequest, native callback parameters and neutral provider ports remain unchanged.

## 3. Input, support, dependency and final eligibility rules

These four sets have separate meanings:

- Aggregate replacement originals: `capture.units[intervalStart:intervalEnd]`.
- Actual chunk input: only the ordered original keys in that chunk descriptor. Every atom/conflict-side sourceRef or tool-group ref must resolve inside this actual input. A reference to a cumulative dependency or another chunk is insufficient.
- Actual merge input/support: the authenticated child summaries named in its descriptor. Each merge reference must be present in the support references of those supplied child summaries and resolve to an original within the aggregate interval. Complete input provenance is computed from child descriptors, independently of whether their prose mentions every original. Input completeness does not prove semantic fidelity or absence of omission.
- Cumulative adoption dependencies: the complete original prefix `[0,intervalEnd)`, including raw-before and protected units. These establish authorized dependency retention/readback and coverage; they do not add permissible support to a chunk or merge.

Compute `finalEligible` as follows, in addition to all normal schema/source/state/owner checks:

- Chunk: true exactly when its authenticated `originalUnitKeys` equals the entire ordered aggregate interval. A proper subset is an intermediate result and cannot be adopted, even with the same aggregate plan.
- Merge: true exactly when concatenating the authenticated ordered child original-key lists yields the entire ordered aggregate interval, with no gaps, duplicates, repeated tool groups or out-of-interval keys, and every merged support reference satisfies the child-support rule. An incomplete otherwise valid intermediate merge is not adoptable. Children must be chunk results; no recursive merge hierarchy.
- At adoption, the aggregate end must additionally extend the prior cumulative frontier and the candidate must satisfy exact current rendered count, lower-target/no-progress and all native/source guards. A persisted true flag cannot override any recomputed predicate.

Run identical descriptor, support, hash, plan and eligibility validation when saving a result, recovering it, adopting it, and reloading its committed checkpoint. An intermediate result may be saved/recovered for its exact bounded episode role; it cannot become a snapshot's `generation_call_id` unless final eligibility recomputes true. These checks do not replace the independent numbers/negations/conditions/conflict omission oracle.

## 4. Atomic adoption and original-preserving rendering

`generation_call_id` identifies the final eligible immutable result. One existing transaction validates it and inserts snapshot, exact cumulative coverage, direct/raw dependency uses and real native pointer/context CAS. `covered_count = intervalEnd` is the dependency frontier, not the hidden-unit count. Existing strict parent-prefix extension, coverage hashes and all-old/all-new failure behavior remain mandatory.

Reload walks the bounded parent snapshot chain and authenticated generation metadata in version order. Retain disjoint earlier intervals; replace an earlier interval only when fully contained by the later interval; reject partial overlap or containment of protected anchors. Each replacement occupies its original interval position, with all raw units outside effective intervals retaining original chronology. Protected keys carry forward. Missing/invalidated/corrupt metadata, inconsistent parent captures, cycles or bound overflow fail closed. Existing snapshots lacking explicit metadata fail `checkpoint_rendering_metadata_required`; no inference from prose, sourceRefs or ordinal counts.

Retained earlier summaries keep their own call/input/result provenance and remain rendering artifacts. They never become registered original sources. For a containing replacement interval, rebuild chunk inputs from its authorized original units and their exact source readback, including originals represented by earlier intervals. Do not summarize prior prose as an original or manufacture a new source kind. Bounded original rebuild/chunk/merge refusal remains available when caps cannot be met. Planner, candidate gain and final count use the same effective rendered request, including disjoint retained summaries, raw-before/current/interior anchors and new interval replacement. There is no independent summary head or process-local authority.

## 5. Profile binding at every result boundary

Reservation, idempotent reservation, request archive adoption and mark-sent compare the whole immutable dispatch profile and exact capture/policy/request identity. Summary calls additionally compare the whole aggregate plan and per-call descriptor. Validate/recount current physical/configured bounds before new object/provider effects.

Recovered **unadopted** succeeded summary results must compare those same exact stored input-manifest fields with the current expected profile, capture, policy, plan, descriptor and request hash before returning reusable content. Validate result hashes/support/eligibility and child provenance as above. Final adoption repeats the exact expected profile+plan+descriptor/capture/request binding even if no new reservation/send occurs. An unchanged request hash, config fingerprint or recovery key cannot bypass this equality. Mismatch rejects before returning reusable content or producing new archive/provider effects; no relabeling, silent compatibility path or resend of a known result. Unknown/sent results remain non-replayable; authoritative accounting is unchanged.

Previously **committed** checkpoint rendering is a separate path: retain and authenticate its recorded generation profile/plan/descriptor, revalidate current source/native authority and reconstruct exact historical intervals. Do not require its old generation profile to equal the current connection merely to render lawful historical content. Count the newly rendered main request under the actual current profile, enforce current capacity, and reserve/send that main request with its own exact current profile. This path cannot adopt an old uncommitted result or rewrite historical provenance.

## 6. Exclusive future implementation scope and acceptance

Upon approval only: owned `compaction/gate.py`, `packing.py`, `journal.py`, `repository.py`, `requests.py`, `summary.py`, optional cohesive new `rendering.py`; dedicated compaction tests and lane evidence. `summary.py` is explicitly listed for exact per-call support validation. No schema/model/migration, shared contracts memory.py, ports/adapters, native sources/writers or other product paths are added to scope.

Required independent deterministic oracles after implementation:

1. Same native execution/current question across two growth episodes, earlier conversation and an interior protected constraint: containing/disjoint intervals, complete tool groups, fresh-process reload, exact GenerationRequest bytes/hash and exact original chronology. Assert effective intervals and cumulative dependencies separately.
2. For `[protected_question,g1,g2]` and plan `[1,3)`, reject protected-question-only summary support. A chunk physically containing only g1 must reject a g2 reference, even if g2 belongs to the aggregate interval. Reject intermediate partial chunk as final, missing/duplicate/reordered/foreign children, child-hash or descriptor substitution, out-of-child merge support, metadata corruption and protected-key removal. No pointer/coverage changes or replay.
3. With prior frontier 6 and aggregate interval `[1,9)`, accept legitimate intermediate chunk `[1,4)` as non-final input, then require the complete authenticated interval before adoption. Rebuild containing intervals from originals; retained summary prose never becomes original source authority.
4. Change every profile/counter/capacity field while keeping request bytes/config fingerprint fixed where possible. Test reserve, archive adoption, send, succeeded unadopted recovery and final adoption. Reject with zero new object/provider effects and unchanged accounting. Separately render committed history with original provenance and recount the new main request under current profile.
5. Save actual counts for original/current-rendered/candidate/chunk/merge requests with all three native serializers. Preserve independent chunk/merge caps, complete tool batches, source readback, semantic omission fixtures, no-progress/hard overflow, same execution/budget/cancel, unknown/crash recovery and atomic all-old/all-new evidence. No paid/live model calls.

The nullable native-lifecycle amendment remains approved under its separately recorded hash. This document does not grant whole-core, dependent #44/#45/#46 integration, semantic model-quality or UI acceptance.
