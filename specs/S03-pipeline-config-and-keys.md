# S03 — Pipeline config, deterministic keys, time units

| | |
|---|---|
| Phase | 2 |
| Depends on | S01 |
| Branch | `feat/S03-pipeline-config-and-keys` |
| Design sections | تدفق البيانات › مفتاح الـ Idempotency؛ خط الأنابيب › التقسيم والمعالجة المتوازية والتجميع (قواعد التقسيم)؛ نواتج النظام › الـ RAG (الفهرسة) |
| ADRs | 0003 (integer time) |

## Goal
One place that defines the processing configuration, its canonical serialization, every
deterministic id/hash in the system, and conversions between samples and milliseconds.

## Interfaces
```python
@dataclass(frozen=True)
class PipelineConfig:
    engine: str
    model_revision: str
    language: str                      # "ar", explicit, never auto
    decoding_params: Mapping[str, str | int | float | bool]
    vad_params: Mapping[str, str | int | float | bool]
    diarization_enabled: bool
    pipeline_version: str
    def canonical_json(self) -> str: ...
    def config_hash(self) -> str: ...  # sha256 hex of canonical_json

def result_key(file_sha256: str, config: PipelineConfig, isolation_scope: str | None = None) -> str
def chunk_id(media_sha256: str, config_hash: str, idx: int, start_sample: int, end_sample: int) -> str
def rag_chunk_id(transcript_id: str, version: int, start_ms: int, end_ms: int) -> str
def embedding_id(text_with_header: str, embedding_model: str) -> str

SAMPLE_RATE = 16_000
def samples_to_ms(samples: int, sample_rate: int = SAMPLE_RATE) -> int   # floor
def ms_to_samples(ms: int, sample_rate: int = SAMPLE_RATE) -> int
```

## Files
- `src/transcribe_engine/domain/config.py`, `src/transcribe_engine/domain/keys.py`,
  `src/transcribe_engine/domain/time.py`
- `tests/unit/domain/test_config.py`, `test_keys.py`, `test_time.py`

## Rules
- Key = sha256(file_sha256 ‖ canonical_json(config)) over engine, model_revision, language,
  decoding_params, vad_params, diarization_enabled, pipeline_version `[D: مفتاح الـ Idempotency]`.
- `isolation_scope=tenant_id` only for tenants that require full isolation `[D: مفتاح الـ Idempotency]`.
- Canonical JSON: sorted keys at every level, `separators=(",", ":")`, `ensure_ascii=False`, UTF-8,
  NaN/Infinity rejected. Field order in the dataclass never changes the key.
- chunk_id formula `[D: التقسيم والمعالجة المتوازية]`; rag_chunk_id and embedding_id formulas `[D: الـ RAG]`.
- All keys are lowercase hex sha256 with a type prefix: `res_`, `chk_`, `rag_`, `emb_`.
- Time is integer samples inside the pipeline, integer ms at boundaries; no floats `[ADR-0003]`.

## Edge cases
- `decoding_params` with nested values → rejected (flat mapping only) with `ValueError`.
- Float `0.0` vs int `0` in params produce different keys (documented, tested), so adapters must emit
  stable types.
- ms↔samples round trip at 16 kHz is exact for multiples of 1 ms (16 samples).

## Acceptance criteria
- **AC-1** `[D: مفتاح الـ Idempotency]` — `test_keys.py::test_each_config_field_changes_key` (unit):
  changing any single field changes `result_key`.
- **AC-2** — `test_config.py::test_canonical_json_is_order_independent` (Hypothesis): permuted mappings →
  identical JSON.
- **AC-3** `[D: مفتاح الـ Idempotency]` — `test_keys.py::test_isolation_scope_changes_key` (unit).
- **AC-4** `[D: التقسيم]` — `test_keys.py::test_chunk_id_stable_across_runs` (unit, golden values).
- **AC-5** `[ADR-0003]` — `test_time.py::test_round_trip_ms_samples` (Hypothesis).
- **AC-6** — `test_config.py::test_rejects_nan_and_nested` (unit).

## Commit plan
1. `docs(S03): add spec`
2. `test(S03): add acceptance tests (xfail)`
3. `feat(S03): add time units`
4. `feat(S03): add PipelineConfig with canonical JSON`
5. `feat(S03): add deterministic keys`

## Open questions
- [x] Q1 — Should the profiling/routing policy version (section 1.5) be part of the key? Proposed: yes,
  through `pipeline_version` (bumped when routing thresholds change), no extra field.
  **Resolved (autopilot, 2026-11-25, D-007):** accepted as proposed.
