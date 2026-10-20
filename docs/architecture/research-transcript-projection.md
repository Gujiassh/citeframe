# Research transcript projection

`ai_pdf_worker.research.memory_context.project_context` copies supplied Research input and native journal rows into local transcript data. The function is currently unregistered and has test-only callers.

## Input and authority

Callers supply a Step lease, consuming step kind and model role, current goal, constraints, resolved system prompt, the complete role-input variables mapping and an explicitly ordered journal sequence. Supported consuming roles are planner, researcher, verifier, critic, investigator and synthesizer.

Before projection, callers must establish lawful shared-task access, committed producer provenance and current lease authority. Every private instruction body, condition and reference must be excluded from shared input, including content belonging to the requester or owner. Fully loaded ORM state and matching body hashes do not establish those permissions or commitment. Output source descriptors confer no read or evidence rights.

## Protected input and ordered history

The protected section preserves the complete current goal, constraints, system prompt and role-input variables. Mutable mappings and journal bodies are deep-copied. Evidence associations, result schemas, quantities, negation and uncertainty remain supplied data.

History preserves caller order across Steps and journal kinds. Adaptive locators use kind, Step ID and turn number; conflict locators use kind, Step ID and operation number. Duplicate locators are rejected. There is no inferred cross-Step chronology, sorting, deduplication or summary.

Each entry separates the consuming lease identity from the original producer Step, Attempt and role, and carries its execution snapshot ID. Adaptive producers are researchers. Conflict inspect, verify and critic phases identify investigator, verifier and critic producers; search and finish have no model role. Conflict requests preserve native operation arguments, which may differ from final model-input variables.

## Availability and validation

Adaptive journals retain a request hash and query without the original request body. Projection reports request availability as `not_stored`; it does not reconstruct a request from current input or query. A validated adaptive result is represented as succeeded native-journal data.

Conflict entries preserve the native `started` or `succeeded` status. A started operation must have no result body or result hash and reports result availability as `not_recorded`. Successful results require a dictionary body matching its canonical hash. Native request bodies are checked in the same way. No success, retry or cancellation is inferred from incomplete journal data.

Unsupported roles, invalid phase/status/ordinal, duplicate locators, body/hash mismatch and unloaded ORM attributes raise local errors. Unloaded attributes are rejected before an implicit database read. Ordinals require exact integers within native per-Step bounds. The input boundary expects native journal row objects and supplied lawful mappings.

## Composition limits

The projection performs no database query, provider serialization or send, source registration or authorization, tool execution, checkpoint adoption or compaction. Per-Step ordinal limits do not bound aggregate input bytes, depth or number of Steps. A future composition must enforce a finite aggregate loading/copy/provider envelope without trimming protected semantics, preserve native dispatch and recovery authority, and register authorized sources through the appropriate native boundary. Full Research memory integration remains incomplete.
