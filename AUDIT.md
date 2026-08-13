# AUDIT — F-AUDIO (W2)

Branch: `work/v5f-audio-20260813`  
Lane: F-AUDIO  
Status: **pending auditor** (implementer must not self-ACCEPT merge)

## Scope claimed

- Closed audio MIME freeze + inspect
- Types: audio_source, audio_normalized, audio_transcript_segment, audio_range
- Additive Alembic `k5e6f7a8b9c0` after HTML head
- Worker AudioIngestionAdapter with ASR gate before persist
- Real Whisper path when configured; fail-closed otherwise
- AudioLocatorCodec in PRODUCTION_LOCATOR_CODECS
- Web player + range highlight; uploadAccept empty
- S0_HANDOFF audio appendix; production registry not enabled

## Auditor checklist

- [ ] Production registry still excludes audio
- [ ] No fake/stub successful transcripts without provider
- [ ] require_configured_asr_profile before any audio persist
- [ ] MIME freeze matches tests
- [ ] Alembic single head k5e6f7a8b9c0
- [ ] Focused tests green
- [ ] No video work; no reverts of ASR/office/html/pdf-visual
