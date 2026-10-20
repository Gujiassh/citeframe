# History foundation

`citeframe_contracts.history` and `citeframe_memory.history` provide storage-free source-selection, query-shape, exact-text window, cursor, and page-counting helpers. They are not connected to application history search or source readers. They create no native authorization, source issuance, index, ranking, persistence, or tool dispatch. The isolated `GenerationImage` value is also available; existing generation messages and requests remain text-only.

## Typed sources and queries

`SourceSelection` reuses the canonical compaction `SourceReference` with a canonical lowercase UUID, positive bounded revision, and lowercase SHA-256. A selection can contain a nonempty half-open text span or a canonical locator ID. The text-window helper requires an already resolved text body; it rejects an unresolved locator span.

History policy/query parsers validate exact shapes, supported kinds/scopes, duplicate choices, strict integer bounds, and timezone-aware dates. Source-kind choices are `chat_message`, `note`, `content_unit`, and `research_artifact`. Runtime policy projection checks the parent/member shape; scalar budgets and deadlines remain the compaction policy owner's responsibility. Plain DTO construction is not a validated policy receipt.

Kind projection uses configured corpus kinds. Source-ID projection intersects the caller's corpus, authorized, and scope sets. These helpers do not prove those sets complete or authorized, filter source metadata by time, read bodies, or rank results. A future native issuer must supply lawful current scope and revalidate membership, source state, revision, and permissions before and after use. Private instructions, including the requester's own, remain excluded from all shared Chat/Research model, tool, summary, checkpoint, planning, and derived-output paths. See [private instruction persistence](private-instructions.md).

## Exact text and continuation

Opening a window verifies the SHA-256 of the entire original UTF-8 body. Text offsets are Python Unicode code points, with no normalization of BOM, CRLF, astral characters, or combining sequences. Optional before/after expansion is bounded to 2,000 code points on each side and clipped once to body boundaries. Pages advance within that fixed window. The body hash and length must still match before paging; a completed nonempty window cannot be read again. An empty body can produce a terminal empty page.

Range cursors bind the original source identity/revision/hash, fixed window, next offset, caller-supplied binding digest, and expiry. They use HMAC-SHA256 with an exact bytes key of at least 32 bytes, constant-time signature comparison, and canonical unpadded URL-safe base64. Decoding caps the token at 4,096 characters, validates exact JSON fields/types and canonical encoding, and accepts only a future expiry within 900 seconds. The MAC supplies integrity; the payload remains readable, and possession grants no read permission. The key and binding must come from a trusted native issuer.

A range cursor intentionally excludes the current tool-call and counting-profile identities. A later request can re-budget the same original window using its current framing and profile, after fresh native authorization. The query parser's opaque search cursor is a separate shape-only field; no search-pagination engine is implemented.

## Counted candidate pages

`fit_page` receives an existing complete generation request and one target tool-result slot. It requires that slot's contiguous assistant/tool group to have matching ordered identities and cardinality. It replaces only the target result, retaining siblings, tools, message order, parameters, and output reserve. Unrelated earlier provider history and argument schemas still require send-time validation.

The helper counts the complete rendered candidate and the same-envelope empty-content baseline through the compaction counter identity/capacity checks. Returned data includes the exact candidate request/hash, count and baseline, current tool-call ID, and public counting-profile hash. Profile material includes model/protocol/configuration/counter identities, capacity, reserve, safety margin, and page limit; it excludes the API key. Counter identity does not establish tokenizer accuracy or billing.

Each candidate begins with at most 16,000 code points. It must fit hard input capacity and a nonnegative candidate-minus-baseline content delta of at most the configured 1–2,000 tokens. A rejected size is halved and recounted, giving at most 14 candidate sizes and 28 count calls. The algorithm does not assume monotonic token counts or promise the largest possible page. No-fit errors leave the original window unchanged. Returned candidates are not sent, archived, adopted, or granted dispatch authority. See [compaction foundation](compaction-foundation.md) and [provider adapters](provider-foundation.md).

## Isolated PNG structure value

`GenerationImage` is frozen and hides base64 content from its representation. It accepts only PNG/high detail, strict integer dimensions, canonical base64, at most 4 MiB decoded data and 5,592,408 encoded characters. Primitive type, size, computed decoded length, alphabet, and padding checks precede ASCII conversion/base64 decoding. Dimension values range from 1 to 2,147,483,647; this structural range is not a practical pixel or model limit.

Validation inspects only the 33-byte PNG signature/IHDR structure: dimensions, color/depth pairing, compression/filter/interlace fields, and header CRC. Header-only data and unparsed remainder can pass. This value does not validate a complete pixel stream, decompress images, provide source provenance, or establish safe native image admission. It adds no image field to `GenerationMessage` or `GenerationRequest` and is not integrated with adapters, counters, archives, packing, or native rendering.

Source entry points: [history contracts](../../packages/backend-contracts/src/citeframe_contracts/history.py), [range helpers](../../packages/memory-service/src/citeframe_memory/history/ranges.py), [query helpers](../../packages/memory-service/src/citeframe_memory/history/search.py), and [image value](../../packages/backend-contracts/src/citeframe_contracts/memory.py).
