# S12 — ASR adapters via vLLM + hallucination filter

| | |
|---|---|
| Phase | 3 |
| Depends on | S10, S00 |
| Branch | `feat/S12-asr-adapters` |
| Design sections | الرؤية المعمارية › الـ Ports، Adapters المخططة للـ ASR؛ خط الأنابيب › 3. الـ ASR، 4. فلتر الـ Hallucination؛ البيانات والتشغيل › تشغيل الـ GPU Worker |
| ADRs | 0005 (vLLM as a separate service), 0007 (default engine) |

## Goal
Real transcription through a vLLM service for the engine chosen in S00, behind the full `ASREngine`
Port with capabilities, with suspect segments flagged instead of silently trusted.

## Interfaces
```python
@dataclass(frozen=True)
class ASRCapabilities:
    native_word_timestamps: bool; native_segment_timestamps: bool
    max_chunk_seconds: float; supports_language_hint: bool; supports_batching: bool
class ASREngine(Protocol):
    name: str; revision: str; capabilities: ASRCapabilities
    async def transcribe(self, chunk: AudioChunk, opts: DecodeOptions) -> RawSegment: ...
@dataclass(frozen=True)
class DecodeOptions:
    language: str; temperature: float = 0.0; extra: Mapping[str, str | int | float | bool] = {}
def flag_hallucinations(segs: Sequence[RawSegment], rules: HallucinationRules) -> Sequence[RawSegment]
```

## Files
- `src/transcribe_engine/application/ports/asr.py` (full version)
- `src/transcribe_engine/infrastructure/asr/{vllm_client,cohere_transcribe,audar,faster_whisper}.py`
- `src/transcribe_engine/domain/hallucination.py`, `.../hallucination_phrases.ar.txt`
- `deploy/vllm/` — compose service + launch args for the chosen model
- `tests/contracts/test_asr_contract.py` (fake + `gpu` real), `tests/unit/domain/test_hallucination.py`

## Rules
- The model runs in a separate vLLM service in BF16; the worker calls it over HTTP; no GGUF in
  production `[D: تشغيل الـ GPU Worker؛ ADR-0005]`.
- The worker sends all chunks of a job concurrently (semaphore, initial 32); vLLM batches `[D: تشغيل الـ GPU Worker]`.
- Explicit `language="ar"`, `temperature=0`, all params stored in `decoding_params` `[D: 3. الـ ASR]`.
- Whisper adapter only: `condition_on_previous_text=False`, compression-ratio / no-speech /
  log-prob thresholds `[D: 3. الـ ASR]`. It is a comparison reference, not default `[D: Adapters المخططة]`.
- Hallucination filter: n-gram repetition within and across chunks, known-phrase list, words-per-second
  above a limit → `suspect=true`, never deleted silently `[D: 4. فلتر الـ Hallucination]`.
- Errors: HTTP 5xx/timeouts → `TransientError`; 4xx on input → `PermanentError` `[D: آليات الاعتمادية]`.
- `name`/`revision` recorded in provenance `[D: الـ Ports]`.

## Acceptance criteria
- **AC-1** `[D: الـ Ports]` — `test_asr_contract.py::test_capabilities_declared` (contract).
- **AC-2** `[D: 3. الـ ASR]` — `::test_arabic_sample_transcribed` (gpu): 3 fixed clips, CER below the
  S00 dev value + 2 points.
- **AC-3** `[D: آليات الاعتمادية]` — `test_vllm_client.py::test_error_mapping` (unit, httpx mock at the
  third-party boundary): 503 → Transient, 400 → Permanent, timeout → Transient.
- **AC-4** `[D: تشغيل الـ GPU Worker]` — `test_process_job.py::test_inflight_bounded` (unit, fakes):
  never more than N concurrent calls.
- **AC-5** `[D: 4]` — `test_hallucination.py::test_repetition_flagged`, `::test_known_phrase_flagged`,
  `::test_fast_speech_flagged`, `::test_normal_text_not_flagged` (unit).
- **AC-6** `[D: 3]` — `test_process_job.py::test_decoding_params_persisted` (unit).

## Commit plan
1. `docs(S12): add spec`
2. `test(S12): add ASR contract and hallucination tests (xfail)`
3. `feat(S12): extend ASR port with capabilities`
4. `feat(S12): add vLLM client with error mapping`
5. `feat(S12): add adapter for the S00 default engine`
6. `feat(S12): add hallucination filter`
7. `build(S12): add vLLM deploy config`
8. `feat(S12): add second engine adapter` (only if S00 kept a fallback)

## Open questions
- [ ] Q1 — Words-per-second limit and n-gram length are not in the design. Proposed: 6 words/s, 4-gram
  repeated ≥ 3 times; tuned in S16.
