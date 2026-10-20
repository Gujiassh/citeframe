# Provider foundation

`packages/memory-service` contains neutral adapters for OpenAI Responses, OpenAI Chat Completions, and Anthropic Messages. They consume the shared `GenerationRequest` and immutable `ModelConnectionSnapshot` types and emit typed text, tool-call, usage, and terminal events through an injected HTTP transport. The adapters and turn helpers have no API or Worker imports.

These modules are available as library components. They are not connected to application Chat or Research execution. They add no native tool dispatch, source registration, checkpoint, budget reservation, persistence, or publication behavior. Protocol tests use injected transports; live provider compatibility, token accuracy, and model quality require separate validation.

## Requests and tools

Each adapter checks the connection protocol, adapter version, declared capabilities, model capacity, output reserve, and request purpose before sending. Tool use requires both tool and streaming-tool capability; a cancellation callback requires cancellation capability. Tools are accepted only for the `main` purpose. Messages use system/user/assistant/tool roles; assistant calls require unique declared identities and matching tool results before another conversation message or send. A supplied transport owns connection lifetime and decoded SSE lines; redirects are disabled on the request. Endpoint authorization, credential storage, and application access controls belong to the calling integration.

Tool definitions use an explicit JSON Schema subset: typed objects, arrays, strings, integers, numbers, booleans, and null; enum, descriptions, required properties, boolean additional-properties rules, and applicable size/numeric bounds. Unsupported keywords, duplicate definitions or JSON keys, non-finite values, invalid argument types, and unknown completed tool names fail. Schema and validated-value nesting are limited to depth 16. The entire completed-call batch must pass schema checks and canonical JSON UTF-8 byte limits before any completed-call event is emitted. Original call identities and order are retained.

Default `WireLimits` allow 10,000 SSE events, 262,144 bytes per line/event, 1,048,576 bytes for the accumulated SSE turn, 16 calls, 16,384 bytes per argument string, and 255 bytes per call ID/name. Message content and the complete serialized request must also fit the text limit. These byte bounds do not establish a model token budget or a cumulative execution budget. Limits must be positive integers; explicit overrides remain subject to the same validation rules.

## Completion, cleanup, and errors

Completed-call and usage events follow successful transport exit. A successful `TurnComplete` follows cancellation checks and the completed observer notification. Invalid streams, failed cleanup, or cancellation cannot produce a successful terminal. Cancellation is cooperative before send, between decoded events, and around completed output; it does not actively interrupt a blocked transport read. Transport timeouts remain necessary.

Malformed protocol data and ordinary transport failures produce stable error codes without displaying the raw underlying exception. Ordinary `started` or `completed` observer failures become `generation_observer_error`; ordinary failed-notification errors are best effort and preserve the active error or generator close. Control-flow exceptions such as `KeyboardInterrupt`, `SystemExit`, and asynchronous cancellation propagate. Injected transport/callback implementations must preserve the trusted protocol-error contract and avoid secrets in their own diagnostics. Closing after the successful terminal does not report a late failure.

`collect_turn` accepts a result only after valid terminal semantics and clean iterator exhaustion, and closes the iterator. It rejects events after terminal, mismatched call identities, undeclared calls, invalid usage, incomplete calls, and an empty answer. It does not dispatch a tool or revalidate provider argument schemas. Its default limits are 10,000 typed events, 1,048,576 accounted bytes, 16 calls, 16,384 argument bytes, and 255 identity bytes.

`continuation_decision` matches tool outcomes by call ID and preserves call order. Missing or pending outcomes stop with `pending_results`; unknown outcomes stop with `unknown_result`; cancellation stops without another request. Complete outcomes can produce a request with `gate_required`. The caller must obtain fresh authorization and budget admission before sending it. The helper grants no source, execution, or retry authority.

## Counting and private data

`PayloadTokenCounter` serializes the full protocol payload and invokes a supplied counter. Its profile must match the connection protocol, model, configuration fingerprint, and context capacity, and identify the counter and version. Results retain `exact` or `estimated` provenance. `CharacterEstimateCounter` computes an explicitly configured character estimate plus protocol overhead; neither adapter usage nor an estimate proves remote billing or tokenizer accuracy.

Private instructions, including the requester's own, remain excluded from all shared Chat/Research prompts, tools, summaries, checkpoints, planning, and derived outputs. These neutral components do not load private instruction storage or enforce audience policy; callers must supply only lawful shared input. See [private instruction persistence](private-instructions.md) and [application model configuration](../guides/model-configuration.md).

Source entry points: [adapters](../../packages/memory-service/src/citeframe_memory/adapters/__init__.py), [counting](../../packages/memory-service/src/citeframe_memory/adapters/counting.py), and [turn helpers](../../packages/memory-service/src/citeframe_memory/chat_loop/turns.py).
