# Issue44 R5 — bounded native image preparation contract

Status: revised implementation-before-review candidate, 2026-09-29, responding to original review `A25EEFC8A4EDFBDD6DCBF0014821A66D7FCAB8B5C4BD13ADD1F7C1E6D0CE0E5F`. NI1–NI5 closure remains with that reviewer. Controller grants only the two geometry files in §12, with coding conditional on its precise small-contract approval. Supervisor/source/activation leases remain ungranted. Controller reports PR52 head `7d6be8a236d48135460b0a5677b6ea01edd31b4f` accepted and pushed, six core/neutral/pure/builder hosted checks successful, three external-service checks failed. Those results cover the prior text builder; they provide no image-resource evidence. No Git calls were made for this design.

## 1. Decision and supported boundary

Implement a **single-purpose native image preparation child per source object**, including bounded storage read, PNG decode/crop or PDF parse/render, and bounded result transfer. Parent retains native authorization and ordered result assembly. Use existing MinIO client construction semantics and existing Python process supervision precedent; add Linux OS resource limits in this specific child. Do not create a general sandbox/job service, persistent worker pool, new database/schema, provider factory or shared image type.

Initial supported runtime: the repository's Linux Python3.12 API image, with working `resource.RLIMIT_AS`, `RLIMIT_CPU`, default-action SIGALRM/ITIMER_REAL, and parent process kill/reap. Windows/macOS and a runtime where any limit cannot be installed/verified reject **before source GET**, with `evidence_image_runtime_unavailable`. No in-process fallback. Existing Windows development can test arithmetic/selection; Linux process tests are mandatory for implementation acceptance.

Compatibility baseline remains **64 explicit regions (8 targets×8), then at most4 optional retrieval images**, retaining order/detail and actual old crop/PNG/PDF rendering semantics. No permanent8-image cap or exclusion of ordinary A4/Letter/downscaled PDFs is authorized. Actual byte/pixel/CPU/retained-memory exhaustion may reject an input; a low output count is not a substitute for those budgets. Canonical RGB/RGBA PNG is the initial fixture family, not a newly approved product format restriction. Unproved complex input behavior stays an activation gate, not a silent change to final supported inputs.

The immediate approved-work candidate is only pure PNG crop arithmetic and PDF **old final-transform** calculation (§12). Original reviewer independently demonstrated48 byte-parity cases, including8 downscales, and64 tiny PNGs totaling5120 bytes. These are reviewer evidence, not a fresh execution here. Linux/complex-input gates below extend that matrix. Ordinary downscale is a required algorithm path before activation.

Full native activation remains a separate reviewed step. The first implementation can execute approved-source synthetic/local fixtures without touching routers or current default native callbacks. #43 core/lifecycle delivery does not block this resource implementation.

## 2. Actual code evidence and gaps

Paths are repository-relative; line ranges were read in the current tree.

| Actual path / symbol | Current behavior | Required boundary |
|---|---|---|
| `services/storage.py:324–332 download_bytes` | `response.read()` with no byte bound; finally close/release | New bounded image-specific read. Do not silently change ingestion/export/research download semantics. |
| `services/storage.py:335… stream_bytes` | 1MiB chunking, default SDK client; no total cap or killable wall deadline | Cannot claim hard bound from this iterator alone. |
| `modalities/image_evidence_targets.py:262…` and `_crop_canonical_image:307–339` | canonical sha verified after full download; `image.load()` precedes PNG/geometry check; Decimal floor/ceil crops, PNG save to BytesIO | Header checks before decode, limited child before Pillow import/open, capped output sink. Keep crop arithmetic/encoder options. |
| `modalities/pdf_evidence_targets.py:131…`, `_page_geometry:233–261`, `crop_pdf_regions_png:366–415` | full PDF fetched; source hash check conditional; PDF opened twice; first150dpi get_pixmap allocated before longest-edge1280 check and possible second render | Require immutable content hash; parse/geometry inside child; one bounded supported raster; no first oversized allocation. |
| `pdf_evidence_targets.py:273–363` | retrieval cache keyed only by object key, region cap4/hit and image cap4; errors soft-skipped | Cache identity must include owner-approved version/hash. Bound source bytes and parse work even if output cap is reached. |
| `modalities/visual_enrichment.py:63–99` | max4 optional images, catches all enrichment errors and continues | Does not bound explicit targets or allocation; strict resource failures must propagate in future approved bounded path. |
| `services/chat.py:120…/152…/450–471` | explicit targets before retrieval images; final text followed by all explicit image payloads then extras, detail=high | Preserve ordering; no mode1/provisional mode2 SSE change. One admission budget across both phases. |
| `schemas/chat.py:367/378/392` | at most8 regions per target and8 targets | Up to64 explicit crops before optional4; existing schema limits are not a safe allocation budget. |

**Existing runtime mechanisms:** storage.py already uses spawn, monotonic deadline/poll, terminate→join→kill→join and a watchdog for publication storage. Constants: network15s, child20s, two teardown graces2s each, publication payload16MiB. `_run_publication_storage_process` is publication-specific, uses pickle recv and has no memory limit; do not call it unchanged as an image sandbox or modify its approved publication semantics. Reuse its stop/reap ordering and safe error treatment in a narrow image runner, with bounded binary framing described below. A watchdog Python thread alone cannot preempt every native call holding the GIL.

`infra/docker/Dockerfile.python` pins Python3.12-slim, runs nonroot uid10001 and one uvicorn process by default. `compose.m403a.yml` specifies API1CPU/2GiB; this is an optional overlay, not proof every deployment has those limits. No existing per-image memory cap was found. Linux `setrlimit` and kernel signal timers are available stdlib/OS mechanisms to integrate, **not already installed image guards**. Installation/probe failure disables this path. No extra package is proposed.

## 3. Concrete v1 engineering envelope (proposal, not provider capacity)

Code-owned immutable `native-image-bounds-v1`; not request-controlled, not inferred from a model name and not a production registry entry. Values below are conservative implementation/test limits for resource experiments preserving the stated compatibility baseline. They become deployable only after reviewer approval and the Linux resource tests; they are not claimed measurements of this workload. Existing8-target/8-region/four-retrieval limits and1280/150 constants above are the only inherited product values.

| Limit | Proposed value / application |
|---|---|
| Source bytes / object | 8MiB; unknown Content-Length still bounded by actual reads |
| Aggregate source bytes / admission | 24MiB; each actual object/page child read charged; incomplete receipt charges the full reservation (see §4) |
| Source read chunk | 64KiB, at most remaining+1 detection byte; no unbounded read call |
| Selected output images | 64 explicit + at most4 optional retrieval; existing schema/order preserved; byte/work limits enforced independently |
| Source operations / admission | ≤68 source/page child operations, serial, bounded by the same30s deadline and24MiB source budget; one child per API process, no wait queue |
| PNG width/height / decode pixels | edge≤4096; width×height≤4,194,304; decoded charge=4×pixels, max16MiB/object |
| Aggregate decoded/raster charge | 64MiB cumulative admission; independent of peak-memory limit |
| PDF pre-render raster | reserve actual computed final bbox/stride before rendering; allow rounding edge up to1282 and≤1282² pixels (3×pixels RGB charge), preserving old1280 scale formula; no first-pass pixmap allocation |
| Aggregate render charge | 32MiB cumulative admission, included in64MiB decoded/raster charge |
| Encoded PNG output | 4MiB/image,16MiB/admission; reserve before encode/receive |
| Child address-space hard+soft limit | 512MiB RLIMIT_AS installed by the proposed trusted launcher before Python exec; launcher pre-entry protection remains a separate deployment gate (§5) |
| Child CPU | soft=hard=8 CPU seconds RLIMIT_CPU; kernel kill, no Python handler dependency |
| Child wall | ≤15s, default SIGALRM timer; includes source read and codec/encoding |
| Whole preparation | 30s monotonic deadline including slot wait, all children and transfer; each child gets min(15s, remaining−1s teardown reserve); ≤0 rejects |
| Teardown | terminate+join0.25s; kill+join0.75s; no result adoption until child reaped; cleanup failure disables further image children for that API process |
| Parent result channel | metadata≤16KiB; each PNG length≤4MiB and aggregate≤16MiB, validate lengths before reading/allocating |

**NI1 — two different lifetimes.** The child slot ends only after process exit/reap. A separate API-process retained-output quota is acquired by trusted native composition **before preparation** and remains owned by the final consumer scope after prepare returns. `prepare` borrows it; successful return does not release it. No hidden transfer to an unspecified later budget.

Proposed experiment: process retained quota256MiB, at most2 live output leases, no waiting queue. Reserve `R = 4*B + 5*(4*ceil(B/3)) + 2MiB` bytes, where B is this admission's PNG output allowance (≤16MiB). R accounts for at most four simultaneously live binary copies (receive/staging/frozen/result-or-archive) plus five base64-sized copies (encoded bytes, ASCII string, data URL, JSON/archive, transport buffer) and bounded metadata. For B=16MiB reserve~172.7MiB, so a second full-size preparation rejects while the first consumer retains output; smaller measured envelopes may coexist under256MiB. This is an explicit maximum-copy contract to verify, not a claim Python/HTTP libraries automatically comply. Any extra serialization/retry/archive copy must reserve its incremental worst-case bytes before allocation or fail. No shrink of R while uncontrolled copies remain; source buffers stay child-only. Whole-API RSS also includes non-image work and the child512MiB; deploy owner must budget worker_count×(retained quota + child allowance + measured API baseline/headroom), not equate2GiB with a per-image guarantee.

One small API-local lease, held by `with` in composition, covers child receive, preparation result, base64/request/archive and last send/iterator cleanup. Ownership state OPEN→CONSUMING→RELEASED: a single explicit move to the caller is allowed; the previous owner cannot release after moving; idempotent close cannot credit twice. On errors/cancel/revocation, first close iterator/client and clear all controlled raw/base64/archive references, then release. Persistent bytes must transfer to a separately approved bounded owner before release; until that interface exists, retaining or detaching image buffers past this scope is forbidden. Escaped raw bytes cannot be garbage-collected by a lease magically: consumer wiring and no-escape tests are required for any lifecycle safety claim. Queued/repeated calls while the first result is still held must reject before new allocation when quota is exhausted. Failed reaping keeps the child slot unavailable; it never releases output reservations still referenced. Neither this quota nor the supervisor is currently authorized for implementation.

Sizing gate before changing constants: in the locked Linux image record empty-child VM baseline, supported corpus success, parent/child peak RSS and wall/CPU, plus enforced failure at each limit. If imports alone do not fit512MiB, fail the feature and bring a measured revision to review; do not raise limits automatically. Hash the versioned envelope in native preparation evidence; this is not a new memory-service policy ABI.

## 4. Proposed local call surface and admission ownership

Names below are **new API-local implementation proposals**, not shared contracts:

```python
prepare_native_images(
    *, sources: tuple[NativeImageSourceRequest, ...],
    budget: NativeImageBudget, output_lease: NativeImageOutputLease,
    cancelled: Callable[[], bool],
) -> NativeImagePreparationResult
```

These are **proposed API-local records**, no shared ABI/export/source authority. Parent-only request fields: unique contiguous source_ordinal; original source owner identity/ref (never granted by child); kind canonical_png|pdf; object_key/hash/generation/representation identity; operation=`geometry_only|crops`; ordered region rows `(output_ordinal,x,y,width,height)`. PNG requires positive strict-int expected_width/expected_height; PDF requires positive strict-int page_number. Geometry-only requires zero region/output rows; crops requires1..8 rows per source record. Output ordinals are unique and contiguous globally across explicit then selected retrieval images (0..N−1, N≤68). Sources with repeated pages/objects remain separate request records unless the exact batching rule below applies. All coordinates finite, bool excluded, existing normalized region constraints retained.

Result is frozen `NativeImagePreparationResult(sources: tuple[NativeImageSourceResult,...], images: tuple[NativePreparedPng,...])`; it borrows the caller-owned output lease, cannot release or transfer it. `NativeImageSourceResult` carries source_ordinal, echoed parent-assigned opaque source_identity digest, operation, mandatory geometry, and `NativeImageCharge`. PNG geometry is width/height/orientation_applied=True; PDF geometry contains all current `_page_geometry` fields: crop_x0/y0/x1/y1, rotation, display_width/height. `NativePreparedPng` carries source_ordinal, output_ordinal, bytes, actual width/height, SHA-256 and PNG media type only. `NativeImageCharge` has source_bytes, decode_bytes, render_bytes, output_bytes, operation_count and receipt_complete; no authority token. Geometry-only produces one source result with no image ordinals; missing crop is an error, successful geometry-only is not. Parent validates source/result bijection and original owner eligibility; it never reopens PDF or decodes PNG to fill missing geometry. Results are all-or-error, no partially successful source list.

`NativeImageBudget` fixes policy version, limits and absolute monotonic deadline; parent owns mutable counters for this call. Source refs stay original-owner records outside the child; echoing a digest proves pairing only. Missing/unknown fields, conflicting operation fields, duplicate ordinals or nonfinite geometry reject before adoption. No new #42 GenerationImage type is declared here.

Caller's native authorization precedes source read and covers **every output reader**. All private sources, even actor-owned, are excluded by A1 choice2. #43/#42 remain source/version/permission authorities. This resource helper never authorizes by possession of an object_key. Parent rechecks exact source eligibility before result adoption/next dispatch via original owner; cancellation/revocation discards child output. Missing canonical/PDF content hash rejects `evidence_target_source_unverifiable` before GET; the current PDF conditional hash behavior does not establish immutable provenance.

Parent reserves upper bounds before each child: source allowance=min(8MiB,remaining source), remaining decode/render/encoded allowances, one source-op, fixed region ordinals. The initial implementation has **no cross-child cache**. One child batches regions only for the same exact `(object_key, hash, processing_generation, representation_identity, kind, page_number)` key, at most8 regions; a different PDF page starts a new read and consumes a new source-op and source bytes even if key/hash repeat. Geometry-only can share that same page child only when explicitly represented in its expected result manifest. No claim that immutable source is always read once.

Counters distinguish cumulative work from releasable live memory. A complete validated terminal receipt followed by exit0 may replace a work reservation with actual charged usage; it never refunds already consumed work. Kill/cancel/EOF/partial/invalid receipt charges **all reserved source/decode/render/output work and operation count**; lack of a receipt never implies zero read/decode. Output live-memory lease remains separate and releases only after controlled buffers are discarded. This conservative failure charging cannot roll back the absolute deadline or refill a retry budget.

Explicit regions are admitted in request/region order. Retrieval candidates retain existing dedup/order and existing optional4 cap, but must fit remaining aggregate slots/resources before selection. Selected explicit failures always fail the preparation. Existing optional-retrieval soft-skip remains the compatibility baseline: a future native-owner decision must distinguish optional per-hit failure (preserve safe skip and charges), whole-admission cancellation/revocation/cleanup failure (abort), and resource exhaustion (no further optional work). Do not activate a blanket soft-skip→whole-chat-error change without that owner approval. Missing optional retrieval metadata may keep its existing pre-selection skip. Explicit overflow is a visible resource error; schema maxima stay unchanged. No SSE envelope change: future integration maps safe error through existing ChatError/error path; transaction effects remain under existing native rollback/start owner.

## 5. Source-read and process protocol

One child performs source GET and codec, under the installed limits. Parent sends a bounded native request plus a storage-owner-supplied frozen MinIO connection snapshot over an anonymous pipe. Credentials never appear in argv, logs, output frames or persisted image metadata. Snapshot creation and SDK client adapter belong to the existing storage owner; no new credential loader. Source object cannot select a bucket/host. The storage owner supplies a NEW lightweight `services/native_image_source.py` using the actual `_publication_client_for_request` MinIO/PoolManager/TLS/retries=False construction semantics, with image-specific timeouts capped by remaining wall time. Its parent-only snapshot factory lazily reads existing settings; its child-side client/read functions import only stdlib, MinIO and urllib3, never settings/metrics/ORM. Do not import the heavy storage.py module into the codec child or change its publication constants/operation enum. This small native storage adapter requires the lease in §9; no new credential service or configurable backend registry is introduced.

### NI2 — startup envelope, secrets and parent death (not authorized to implement)

`-I` alone permits site processing and inherited environment. The required invocation is **fixed owned launcher → absolute Python executable `-I -S -B` → absolute owned child script**, shell=False, cwd=fixed read-only code directory, close_fds=True with only control/result anonymous-pipe FDs plus stdin/stdout as explicitly mapped, stderr=DEVNULL. Construct env from scratch: LANG=C.UTF-8 and TZ=UTC only; any indispensable platform variable needs an explicit fixed deployment value. Do not inherit HOME, PYTHONPATH, LD_*, proxy, DB/model/cloud/storage credentials. No secrets in argv. Parent snapshot credential fields are repr=False and sent only after validated READY.

Selected launch requirement: a tiny **native Linux image-specific launcher** installs RLIMIT_AS512MiB, RLIMIT_CPU8s, RLIMIT_CORE0, parent-death SIGKILL via prctl, verifies getppid against the expected supervisor PID before and after prctl, unblocks SIGALRM/SIGXCPU, sets default dispositions and arms the monotonic wall alarm before exec of Python. Use no Python `preexec_fn` in the multithreaded API. The launcher PID is the child PID; no shell/grandchild chain. Alarm/limits/parent-death behavior must be proved across exec on the pinned image. Launcher startup before its first instruction is covered by the separately verified deployment memory/cgroup and core_dump=0 envelope, **not** by script-entry512MiB. A failed or missing launcher is unavailable, never a fallback to bare Python.

This launcher is a concrete **out-of-scope dependency request** to deployment/controller: proposed `tools/native-image-launcher.c` and image build/copy/check permission. Neither file nor image/dependency change is currently granted. No existing approved launcher or independently verified startup envelope is present, so supervisor production launch remains disabled. Reusing publication's Python watchdog cannot satisfy this missing startup contract. Do not begin supervisor implementation before original review accepts this dependency or an exact equally bounded owner alternative.

After exec, stdlib-only child verifies installed limits, core policy, unblocked alarm and parent PID before READY; recheck parent identity before receiving credentials and before heavy imports. With -S, load only deployment-pinned dependency directories explicitly by absolute paths after limits, without running site.main, .pth or sitecustomize and without user PYTHONPATH. No API-main/ORM import. READY includes protocol version and effective limits, never credentials. Parent checks READY before control transfer. Deadline covers launch and READY; parent death at launcher entry/exec/READY/control/codec must terminate child (launcher parent-check race closure plus inherited PDEATHSIG). Parent/launcher dumpability/core policy must prevent credential-bearing dumps; RLIMIT_CORE0 alone is insufficient evidence on a host piping dumps to a collector: deployment owner must verify dump suppression including PR_SET_DUMPABLE=0 after exec/before credentials. Missing protection rejects before credentials/GET.

### NI3 — exact bounded IPC state machine

Parent sets both pipe descriptors O_NONBLOCK and uses selectors.DefaultSelector with read/write readiness. Never fd.read(n), buffered file writes, pickle recv or unbounded communicate. Each os.read/os.write is≤64KiB; retain offsets across partial operations and handle EAGAIN. Selector wait≤min(50ms, absolute_remaining), then recheck cancel, monotonic time and process exit. One call deadline T covers launch, READY, control write, all frames, EOF and exit; operational cutoff=T−1s permanently reserves teardown once. Child wall alarm is min(15s, cutoff−now). Abort when no operational time remains. Stop state closes channels, terminate+wait0.25s then kill+wait up to T; unreaped child keeps slot/quota unavailable and disables further image work. No reader threads left behind.

Version1 wire: uint32 big-endian body length, one uint8 frame type, then exactly that many body bytes; length excludes type. Known sequence only: child READY(type1 JSON≤1KiB), parent CONTROL(type2 JSON≤16KiB), child SOURCE(type3 JSON≤4KiB), zero or more IMAGE(type4 header JSON≤1KiB, followed by separately uint32-length-prefixed raw PNG≤4MiB), terminal DONE(type5 JSON≤1KiB) **or** ERROR(type6 JSON≤1KiB), then EOF and exit. Each child has exactly one SOURCE for its assigned source/page and≤8 IMAGE frames; total JSON≤16KiB, raw bytes≤its granted budget. Across admission sources≤68/images≤68 and output≤16MiB. Parse JSON with duplicate-key rejection, strict fields/types/finite values; header byte limits checked before allocating; PNG body is read into a single bounded buffer, with final immutable-copy peak reserved by NI1.

SOURCE echoes exact source_ordinal/source_identity, operation and required geometry; IMAGE header echoes assigned source/output ordinal, dimensions, digest and raw length. Require exact expected ordinal set/order, no duplicates, no extras/missing images, and no image on geometry-only. DONE carries complete usage receipt and counts/digests; no adoption until exact EOF+exit0, never on DONE alone. Trailing frames/data, nonzero exit after success, partial header/body, mismatch, stall or cancel discards the whole child's result. Parent validates bounded metadata/hash and PNG signature only, never parses PDF/decodes image. Parent records actual received bytes independently; child-reported work cannot reduce below known consumption. ERROR receipt is not a successful refund receipt; charge full reservation under §4.

The CONTROL contains fixed storage fields (object key≤1024 bytes, endpoint/bucket≤512 each, credential≤4096 each), the one admitted source/page manifest and≤8 finite normalized regions; no child-selected source URL. Partial control writes receive the same cancel/deadline treatment as result reads. EOF/exit waiting never resets the deadline.

Source algorithm:

1. Deadline/limits installed and read reservation granted before get_object. Stat or Content-Length above allowance rejects; missing/false/small length cannot waive actual cap. Storage client has explicit connect/read timeouts≤min(5s, child remaining) and retries=False. Kernel wall timer still bounds a stalled SDK/native call.
2. Read `min(65536, allowance−consumed+1)` bytes per call; detection byte is included in allocation accounting but never adopted. If limit+1 arrives, stop immediately; do not drain the object. Charge actual bytes and reject. Incremental SHA-256 over accepted bytes; verify against owner hash before open/decode. Always close/release response in normal Python exits; killed process closes descriptors at OS teardown.
3. Allocate bounded source storage in child only; account for bytearray→bytes/BytesIO copies within512MiB. No on-disk source/temp files and no cache outside child. If an SDK returns more than the requested length, reject immediately inside the already limited child; do not trust that transport to meet a parent-memory bound.
4. Encode result framing as metadata then PNG lengths/bodies. Parent checks each length and remaining output budget before buffer allocation; reads in64KiB chunks under common deadline. Partial/malformed frame, EOF or unexpected child status discards all output. No pickle recv and no source or raw SDK exception over result channel.
5. On cancel/deadline/error, close channels, terminate, then kill/reap within reserved grace; drain nothing unbounded. Adopt only complete success after exit0 and reauthorization. Launcher-installed alarm/PDEATHSIG and the parent state machine must cover startup through codec; this remains a Linux execution gate, not an implemented guarantee. A child that cannot be reaped is a fatal local resource condition, never a reusable slot.

This is a resource boundary for known codec libraries, not a malicious-code containment sandbox. No subprocess descendants, shell commands, network providers or dynamic code are accepted. Linux process tests must verify actual timer/limit enforcement; no mocking setrlimit/kill into a passing security result.

## 6. PNG decode/crop/encode specifics

Before Image.open, verify signature and first IHDR framing/CRC, width/height, bit-depth8, color type2/6, compression/filter0, interlace0. Reject unsupported/invalid header and expected canonical geometry mismatch before `image.load`. Do not parse the whole PNG in parent. Inside limited child, Image.open must report PNG, RGB/RGBA, single frame, expected dimensions; decompression warnings become errors. Reject animation and unsupported ancillary behavior via existing Pillow validation; all decode allocation remains under RLIMIT_AS regardless of header accuracy.

Charge `4*w*h` before decode (RGB conservatively charged4); crop/encoder transient overhead has the independent512MiB ceiling. Keep original Decimal(str(...)) floor/ceil/clamp semantics and target region order. Do not apply EXIF orientation again, resize, convert color modes, optimize PNG or change save parameters. Save with the same `format="PNG"` to a capped BinaryIO sink: write checks current position+length≤per-image allowance before expanding; seek/truncate cannot exceed the cap. Parent validates returned width/height metadata and byte SHA/length. Do not call uncapped getvalue followed by a size test as the sole memory guard. Budget failure aborts whole selected result, never keeps earlier crops as if complete.

## 7. PDF old final-transform and geometry parity

PDF open, page lookup, display-list construction and all render/encode work must remain within the future hard resource child. Geometry-only also returns the complete original `_page_geometry` values from that child; parent never calls fitz.open to fill them. Display-list construction itself may allocate large native data and is not made safe by pure bbox arithmetic.

Use exactly the old cropbox-relative clip computation/intersection and <0.5pt rejection. In the **installed pinned MuPDF** obtain `fz_bound_display_list` from the same page display list (default annotations included). Intersect with clip, transform by150/72, and use `fz_round_rect` to predict the original first bbox. This is integer sizing without allocating a first pixmap. If longest≤1280, preserve original `get_pixmap(clip=clip,dpi=150,alpha=False)`. Otherwise use `scale=1280/float(longest)` and exactly `fitz.Matrix(150/72,150/72) * fitz.Matrix(scale,scale)`, reserving the resulting final bbox/stride before **one** call `get_pixmap(clip=clip,matrix=matrix,alpha=False)`. Preserve matrix branch default96dpi and non-downscale150dpi metadata. Do not replace MuPDF float32 transform/round behavior with Python ceil or change matrix multiplication order.

Reviewer evidence:48 in-memory cases covering300×400/A4/Letter, rotations0/90/180/270, ordinary/offset cropboxes and full/fractional clips passed byte parity;8 downscales. Reviewer A4 sample first1240×1755→final905×1280 at96dpi, SHA77F9C52A0BDD005C3745B343AFC2CBA838544A1B084B11C29B38D4C903671B88. This sample hash is meaningful only with the exact fixture content; new tests must compare their own identical old/new fixture rather than assert that unrelated PDFs share it.

Required before activation: reproduce on Linux with pinned PyMuPDF1.28.2/Pillow12.3.0; test UserUnit inheritance, nonzero/negative media origins, complex/offset boxes, rotations, annotations, transparency/images, empty and near-rounding clips. Internal MuPDF symbols are version-pinned; unknown version/symbol or nonfinite/out-of-range rectangle rejects before rendering. Failure of a complex case is an explicit parity gate to fix or bring to product review, not permission to exclude all ordinary PDF inputs permanently. Geometry helper §12 computes only numeric clips/bboxes/matrix; it does not construct display lists, open PDF or enforce process budgets.

Charge actual computed final RGB bbox and a separately reserved encoder allowance; validate actual pixmap dimensions against plan as an invariant. `pixmap.tobytes("png")` still allocates internally: use child hard-memory limit plus measured encoding headroom, enforce4MiB PNG transfer cap afterward without describing it as a pre-allocation guarantee. Source/parse/display-list budgets remain independent. Large resource usage can safely reject; image count68 by itself must not force increasing source/memory budgets.
## 8. #42 GenerationImage consumer requirements (no ABI authored)

Provide only successful canonical/crop PNG bytes, exact image order, actual pixel dimensions, media type image/png, stable byte digest and original owner source refs. The shared ABI owner decides actual field names/types and whether bytes/digest are represented there or in existing reference metadata. #44 will not declare/export a competing GenerationImage. OpenAI request rendering must retain detail=high; Anthropic retains its existing image block without an invented detail property. No private image source enters shared tools/history/summary/planning/output.

Provider serialization/base64 limits and image token accounting are later independent admission: enforce archive/request bytes including base64 expansion; require actual approved image capacity/counter policy, never use the text character estimator as exact image count. Successful native crop preparation alone cannot turn on supportsImages or authorize dispatch. Consuming #42's exact approved ABI is a later owned adapter delta.

## 9. Exact proposed leases and first implementation slice

All rows below require controller assignment and original-owner review; **none is a current product write grant**.

| Lease/request | Minimal change / owner boundary |
|---|---|
| NEW `apps/api/src/ai_pdf_api/modalities/native_image_bounds.py` + `native_image_child.py` | Native owner: local budget/framing/supervisor and stdlib-first child with pure codec functions. Two cohesive files, no common sandbox framework. Child must remain runnable without API main/schema/DB imports. |
| NEW `apps/api/src/ai_pdf_api/services/native_image_source.py` | Existing storage owner: parent-only frozen connection snapshot factory and child-side MinIO/PoolManager bounded reader with explicit timeouts. Preserve storage.py/publication operations/constants and unrestricted consumers unchanged. Child imports this sibling by approved absolute file location after OS limits; no API main/settings/ORM import. |
| `modalities/image_evidence_targets.py`, `modalities/pdf_evidence_targets.py` | Native owner: bounded processor injection; move/reuse exact pure crop arithmetic in child without DB import; no duplicate long-lived crop implementation. Keep ORM/evidence handling in original resolvers. Geometry-only paths must use bound too. |
| `modalities/evidence_targets.py`, `services/evidence_targets.py` | Native owner: add explicit optional local processor/budget dependency, preserve existing ImageBytesLoader for old unactivated callers; bounded path cannot accept arbitrary full-read loader as production fallback. Do not change a shared port. |
| `modalities/visual_enrichment.py`, `services/chat.py` | Later native activation lease: one budget across explicit/retrieved sources, resource errors propagated rather than broad soft-skip, unchanged image/SSE ordering. No lease on router/deps or #40 files. |
| NEW `apps/api/tests/test_native_image_bounds.py` and existing image/PDF tests | Native owner: arithmetic/framing and actual Linux child tests plus original pure crop byte/geometry regression. DB fixture tests require disposable configured DB and cannot be reported passing without it. |
| deployment/CI gate | #42/controller only: verify effective runtime limits/worker count and authorize a Linux job. No lock, manifest, shared CI or settings changes in this design. |
| shared image DTO/source authority | #42/#43 respective originals; consume exact accepted signatures later, never copy their declarations or invent authorization. |

**Current immediate slice is only §12 geometry.** The bounds/child/storage leases listed above remain proposed and must not start from this document. After NI1–NI3 and startup dependency approval, controller may separately grant the resource slice. Implement source-read+PNG+old-final-transform PDF child and real Linux limits with synthetic source transport fixtures; no resolver/default composition/router wiring yet. Pure arithmetic can start without #43. This slice must demonstrate real old-function parity by invoking current original crop functions on bounded fixtures, not by copying expected output from the new implementation. Then serialize native resolver extraction/injection under its own lease, remove duplicated legacy pure codec body only when equivalent caller wiring is reviewed. No dead production wrapper or automatic activation is needed for the first testable slice.

## 10. Minimum acceptance suite and blocking evidence

| Required evidence | Exact oracle |
|---|---|
| source boundary | exact8MiB success;8MiB+1 reject; absent/false Content-Length; slow/stuck read; requested read sizes never>64KiB or remaining+1; no more reads after overflow; close/release; digest mismatch rejects before codec |
| aggregate/concurrency | 24MiB total source bound,64 explicit+4 optional output ordinals and≤68 source/page operations; 64 tiny explicit crops are admitted when actual resource budgets fit; only schema/count>64 explicit or>4 optional rejects by count; concurrent admission cannot start second child; same key/different hash never reused; charge failures and no negative/returned speculative allowance |
| PNG preread/decode | IHDR huge dimensions/mismatch/unsupported mode/interlace reject before load; CRC/truncated/animated PNG fail; crafted compressed tiny source/huge pixel input fails before decode; output sink cap failure leaves no partial adopted result |
| actual hard limits | Linux real child allocates past512MiB, native-style uninterruptible-loop fixture hits default SIGALRM, CPU loop hits RLIMIT_CPU, blocked source hits wall timeout; no orphan after cancellation/parent-supervised failure; parent memory stays bounded on oversize output framing. Unsupported platform/failed setrlimit rejects before GET, no skip masquerading as pass |
| PDF prerender | supported page/clip boundary succeeds; large first-pass/downscaled ordinary crops predict final transform and render once; nonfinite/unsafe arithmetic or genuinely over-budget final raster rejects before get_pixmap; rotation/offset/UserUnit covered by parity matrix; huge internal embedded image still cannot escape child limit; encrypted/malformed parse bounded; actual render dimensions≤pre-reserved conservative rectangle |
| exact parity | existing `_crop_canonical_image` and `crop_pdf_regions_png` outputs compared byte-for-byte/SHA under identical pinned Pillow/PyMuPDF versions; RGB/RGBA edge/fractional Decimal regions, multiple regions/targets, PDF300×400 fixture, fractional clip edges near pixel rounding; dimensions and locator geometry/order equal. No decode-only visual similarity acceptance |
| failure semantics | no partial explicit result, safe error without key/source/SDK details; missing hash/version rejected; cancellation after read/during decode/before adoption discards; owner source revocation integration remains separate and unclaimed |
| lifecycle/compatibility | response/channel/document/image cleanup and child reaping on success/error/timeout/cancel; existing image/PDF tests and actual native transaction tests after wiring; mode1/mode2 envelopes unchanged; optional retrieval behavior change explicitly reviewed |

Proposed errors use existing EvidenceTargetError at native boundary: `evidence_image_resource_limit` (422), `evidence_image_runtime_unavailable` (503), `evidence_image_busy` (503), `evidence_image_timeout` (504), `evidence_image_unsupported` (422), `evidence_target_source_unverifiable` (409); retain existing hash/geometry/page errors when applicable. Exact safe messages and mapping through current ChatError are reviewed with activation; no new event envelope or public schema is added here.

Actual blockers: native/storage leases not yet granted; Linux limit installation/enforcement and pinned-library parity not yet measured; optional retrieval resource-error mapping and full old-format/geometry parity require original native review; deployment aggregate memory/worker envelope must be verified. These do not depend on #43 core completion. Full production dispatch separately requires owner source authorization and #42 GenerationImage/counter contracts. No implementation or resource tests were executed in this design turn; evidence here is actual source inspection and hashes only.

## 11. Source snapshot hashes and write-back

| Read-only file | SHA-256 |
|---|---|
| `apps/api/src/ai_pdf_api/services/storage.py` | `6fcbb3f57d7e6198e420886ea3b74858e07a5e0652cf04674596a8fba15efd95` |
| `apps/api/src/ai_pdf_api/modalities/image_evidence_targets.py` | `80a1915ce56ea42cdfb1963724bd5918017274686e8942ac55ccfae127a26ef7` |
| `apps/api/src/ai_pdf_api/modalities/pdf_evidence_targets.py` | `9ec66a868d963fad94ecd594f07d418c5a501b785cefe7e63db35351453d3229` |
| `apps/api/src/ai_pdf_api/modalities/evidence_targets.py` | `008f5ffd4b85fc30b1e8b2e601e0e2f0b65087749cc0c1a20cb22d06a1b59faf` |
| `apps/api/src/ai_pdf_api/modalities/visual_enrichment.py` | `4e37b0140eca9764857c932e65a46dfadf52f23fc727965b23f9eb7c403fa1bd` |
| `apps/api/src/ai_pdf_api/services/evidence_targets.py` | `6bfaa0703536a850859756f4eafd69c893e9c35916f7390885b0e3e499d0d26f` |
| `apps/api/src/ai_pdf_api/services/chat.py` | `dd6d28f8629c1655aca238b817ace9be81c4dfb33c4198027b8fe9f966973c91` |
| `apps/api/src/ai_pdf_api/schemas/chat.py` | `71857732ff3245af5e0cef4180a64cf3e6a968cbd6b174b60222699acdbfeb67` |
| `infra/docker/Dockerfile.python` | `52fbd1c93d960fceaf230fe935ca51d3988e98aef91d3ec75524b8dd0f5ca113` |
| `infra/docker/compose.m403a.yml` | `ca54c999f7400d2cce52f8d0a4a593cc49159fec6d86def4654adcaa11e56adf` |
| `apps/api/tests/test_pdf_evidence_targets.py` | `2f57e5aac760ad86b5ddb895fc67a206fa7352a4956b4f9be44d03863f7969e9` |
| `apps/api/tests/test_image_evidence_lifecycle.py` | `8a7bdf6bca12c9d5567868a1a3959f86c9e35b2a953b4304c3b5f785cc67a6a8` |

Write-back is this new owned contract and a link from loop §21 only. Original owner/reviewer artifacts and parallel #42 image ABI contract are untouched. No product/dependency/schema/router/CI edit, Git/branch change, model/network call or UI46 operation. No private memory read/write. External workbench is read-only under current workspace scope.


## 12. Immediate geometry-only slice — exact small contract awaiting original review

Only proposed product writes after targeted approval: NEW `apps/api/src/ai_pdf_api/modalities/native_image_geometry.py` and NEW `apps/api/tests/test_native_image_geometry.py`. No supervisor, source reader, budgets, lease manager, frame parser, tokenizer, source authority, shared DTO, existing crop edit or production caller. No CI/dependency/lock edits. The original developer resumes only after reviewer accepts these signatures/numeric semantics; this revision writes documentation only.

### 12.1 Pure signatures and closed values

```python
def png_crop_bounds(
    *, width_pixels: int, height_pixels: int,
    region: tuple[float, float, float, float],
) -> tuple[int, int, int, int]: ...

@dataclass(frozen=True)
class PdfRenderPlan:
    clip: tuple[float, float, float, float]
    first_bbox: tuple[int, int, int, int]
    final_bbox: tuple[int, int, int, int]
    matrix: tuple[float, float, float, float, float, float] | None
    dpi: int | None


def pdf_render_plan(
    *, cropbox: tuple[float, float, float, float],
    display_list_bounds: tuple[float, float, float, float],
    region: tuple[float, float, float, float],
) -> PdfRenderPlan: ...
```

Both functions are deterministic numeric operations only: no input bytes, page/document/display-list handle, IO, image decode/encode, renderer or process launch. No import from API schemas/settings/native resolvers or memory contracts. PNG path uses stdlib only. PDF function lazily imports the installed pinned PyMuPDF1.28.2 solely for Rect/Matrix and the same MuPDF intersect/transform/round arithmetic; it must never invoke open/get_displaylist/get_pixmap. This is version-coupled geometry, not an inferred general PDF implementation. `PdfRenderPlan` is an API-local arithmetic return record; no root export or #42 image ABI declaration.

Inputs: dimensions strict Python int (bool rejected),1..2^31−1; tuple arity exactly4; coordinate components strict int/float (bool/subclass/custom coercions rejected), finite; region x/y∈[0,1], width/height∈(0,1], x+width≤1 and y+height≤1 using the existing schema's numeric comparison. Rect components absolute value≤1,000,000 points, x1>x0 and y1>y0; this is a conservative safe arithmetic domain, **not a production source/pixel/capacity budget**. Reject unsafe/nonfinite intermediate values or invalid integer bbox; no clamp of invalid input. Integer region components0/1 may be normalized to float only after strict validation, preserving legacy `str(float)` arithmetic semantics. Tiny valid regions that produce an empty raster return the specified error, not a zero-size plan.

Safe errors are local `ValueError` with exactly `native_image_geometry_invalid`, `native_image_geometry_empty` or `native_image_geometry_engine_unsupported`; no raw values/exceptions/URLs/source identity. Do not import shared ProtocolError or add a new port. Shape/type/range/nonfinite/overflow map invalid; empty PNG bounds/PDF clip<0.5pt/empty transformed bbox map empty; absent/version-mismatched MuPDF primitives map engine_unsupported. Module import itself must work without PyMuPDF loaded; unknown version rejected only on PDF call.

### 12.2 Exact arithmetic, no first render

PNG bounds replicate current `_pixel_floor/_pixel_ceil`: Decimal(str(x))*width floor, Decimal(str(y))*height floor, (Decimal(str(x))+Decimal(str(w)))*width ceiling and analogous height; clamp exactly as original to0 and image dimension. Use the same default Decimal precision28/rounding context in controlled tests; implementation must explicitly preserve that baseline context rather than allow ambient caller context to alter results. Reject empty after clamp. Do not expand regions, resize or change the old floor/ceil rule.

PDF clip replicates current cropbox-relative expressions, constructs `fitz.Rect`, intersects cropbox, checks old0.5pt minimum. `display_list_bounds` is the **actual numeric bound of the original page display list**, not page.cropbox/page.rect substituted by guess. In eventual integration only a resource-limited caller may construct that display list; it must include annotations like old get_pixmap and remain tied to the same page/source. Helper does not validate that provenance.

Mirror inspected `PyMuPDF JM_pixmap_from_display_list` sequence: native FzRect(display bounds) → fz_intersect_rect(clip) → fz_transform_rect at native matrix150/72 → fz_round_rect. Set first_bbox to those four native integer coordinates. If max(width,height)≤1280, return matrix=None,dpi=150,final_bbox=first_bbox. Otherwise form the **same old** `fitz.Matrix(150/72,150/72) * fitz.Matrix(1280/float(longest),1280/float(longest))`, compute final bbox with the same native intersect/transform/round sequence, return six matrix components and dpi=None. Do not use an extra ceil margin to choose the old branch; reservation overhead is a later budget concern. Return actual bbox, including origin; width=x1−x0,height=y1−y0. Preserve native float32 conversion points and current MuPDF rounding epsilon; do not emulate by Python round/ceil. This calculation allocates only constant-sized geometry objects and no pixmap.

Consumers in tests call old `page.get_pixmap(clip=plan.clip,dpi=150,alpha=False)` for non-downscale, or `page.get_pixmap(clip=plan.clip,matrix=fitz.Matrix(*plan.matrix),alpha=False)` for downscale, never both. The resulting PNG must equal the old two-pass oracle, including150-vs96dpi metadata. This test render is fixture-only, not a new production entrypoint.

### 12.3 Exact bounded verification and approval boundary

- Tests AST-extract actual existing `_crop_canonical_image`, `_pixel_floor/_pixel_ceil` and `crop_pdf_regions_png` plus fixed150/1280 constants as the **old oracle**; pin its source hash from §11 and fail visibly on drift. No API/DB/settings import, no copying oracle arithmetic into a fake expected implementation. Synthetic region objects provide only the original four fields.
- PNG fixtures: actual Pillow RGB/RGBA encode/crop;32×32 image, edge/fractional regions and64 tiny outputs in8×8 grouping. Apply returned bounds using the same old crop.save(format=PNG), compare bytes/order/dimensions. Keep full64 capability without increasing source/output caps. Include empty, overflow, bool, nan/inf, malformed tuple and altered Decimal context tests.
- Reproduce reviewer48 matrix using in-memory3 page sizes(300×400,595×842,612×792)×4 rotations×2 ordinary/offset cropbox variants×2 full/fractional regions. The same PDF/page must feed old oracle and new planner+single final render. Record first/final bbox, bytes digest and DPI. Verify test branch coverage includes A4/Letter downscale; do not hardcode an unrelated fixture hash. Instrument planner path to fail on any fitz.open/get_displaylist/get_pixmap call; only fixture setup/render may call them.
- Add bounded complex cases: annotations on/off as supported by the old default, transparency, embedded small image, negative/nonzero media origin, UserUnit inherited/direct, clip edges around native rounding, and nonfinite/out-of-domain rejection. Case generation has explicit small limits (≤12 pages/PDF,≤1024² embedded image,≤2MiB generated fixture, modest physical page bounds); do not use giant hostile PDFs in this arithmetic slice. Old oracle may render twice only on these bounded fixtures.
- Linux with pinned libraries must rerun byte/DPI/geometry matrix before production use; Windows results establish only the observed platform parity. Missing PyMuPDF/Pillow or unknown version causes a required-test failure, never pytest.importorskip or silent deselection. No new Linux CI lease is implied; controller supplies execution separately. Existing builder/profile/core accepted results are untouched and need no re-audit.
- Negative/independent import checks deny API application modules except the new modality package/module and deny Worker/network. No fake source reader/token counter/authority introduced to make geometry tests pass. Explicitly assert no product caller imports this new module in this slice.

This is a real nonpublishing algorithm slice ready for targeted review, not a blocked supervisor implementation. Following signature approval, original developer can write exactly these two files and return code/tests/hash evidence to the same reviewer. NI1–NI3 supervision, startup launcher, result/geometry integration and optional-retrieval mapping remain separate gates. No code is written in this contract revision.

## 13. Revised review oracles and scope ledger

Original NI1–NI5 findings are addressed here as **candidate contract corrections**, not self-closed findings. Added acceptance obligations: hold first output lease through consumer serialization while repeated prepares exhaust process quota; move/close/double-close/cancel with all copied buffers accounted; startup-before/after limit env/site/FD/core/parent-death Linux probes; nonreading child/one-byte body/full pipe/duplicate or missing ordinal/trailing frame/DONE-before-nonzero-exit; incomplete-receipt full charge; geometry-only results with no parent PDF open;64 tiny crops and48old-final-transform byte cases, then Linux/complex gates.

No supervisor, source or geometry product code was created this turn. Only this existing contract is revised; original review SHA A25EEFC8A4EDFBDD6DCBF0014821A66D7FCAB8B5C4BD13ADD1F7C1E6D0CE0E5F stays read-only. The only out-of-scope new dependency proposed is the deployment-owned minimal native launcher/build plus verified startup/core policy; it is a blocker for production supervisor, not for §12 geometry. No alternative shared image type, native/router/schema/CI/dependency write, Git/model/UI46 operation. Write-back is this owned contract; private memory/external workbench untouched.
