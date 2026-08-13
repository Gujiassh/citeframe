# F-ASR capability contract

Status: `approved` for capability/profile/error-code freeze only.
Does **not** approve Audio/Video catalog enablement (OD-B6 remainder / F-AUDIO).

## Profile identity

Server-selected, one profile:

| Field | Contract |
| --- | --- |
| capability | `asr` |
| provider | `openai` (closed list; no selector) |
| model | `whisper-1` default (`AI_PDF_ASR_MODEL`) |
| adapterVersion | `asr-openai-transcriptions-v1` |
| modelVersion | `asr-v1` (`AI_PDF_ASR_VERSION`) |
| secret | OpenAI key (`AI_PDF_OPENAI_API_KEY` / `OPENAI_API_KEY`); blank/whitespace = missing |
| timeoutSeconds | `AI_PDF_ASR_TIMEOUT_SECONDS` (default 120) |
| maxDurationSeconds | `AI_PDF_ASR_MAX_DURATION_SECONDS` (default 600) |
| maxFileBytes | `AI_PDF_ASR_MAX_FILE_BYTES` (default 25 MiB) |
| fingerprint | capability-profile-v1 SHA-256; secret is one-way marker only |

Public metadata never includes endpoint identifier, secret, or fingerprint preimage.

## Fail-closed

| Condition | Code |
| --- | --- |
| Registry missing | `capability_unavailable` |
| Missing/blank secret or `configured=false` | `asr_not_configured` |
| Provider timeout (future adapter) | `asr_timeout` |
| Provider/protocol failure (future adapter) | `asr_provider_error` |
| Segment schema violation (future ingest) | `asr_segment_contract_invalid` |

`require_asr_capability()` / `require_configured_asr_profile()` must run before any audio representation or content-unit persist. They never fall back to vision or generation. They never invent transcripts.

## Configured path

When the secret is present, `capability_status()["asr"]` is `ok` and the registry returns a typed profile + snapshot fields. This is configuration readiness only. This slice does **not** ship a transcription adapter.

## Reserved segment schema (for F-AUDIO)

- `start_ms` / `end_ms` with `end_ms > start_ms`
- optional speaker; no silent speaker invention
- `text_sha256` of normalized transcript text
- no empty transcript rows as a success path

## Explicitly out of scope

- enabling `audio` / `video` asset kinds
- fake or stub transcripts
- user/workspace provider selector
- changing generation/embedding fingerprints or Research agent I/O
