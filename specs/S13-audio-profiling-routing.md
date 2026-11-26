# S13 — Audio profiling and routing

| | |
|---|---|
| Phase | 3 |
| Depends on | S11 |
| Branch | `feat/S13-audio-profiling-routing` |
| Design sections | خط الأنابيب › 1.5 تحليل الصوت والتوجيه؛ اختيار النماذج › مصفوفة المتانة |
| ADRs | — |

## Goal
Each chunk gets an `AudioProfile`; a pure routing policy decides enhancement, separation, VAD
strictness and flags, so clean audio pays only the profiling cost.

## Interfaces
```python
@dataclass(frozen=True)
class AudioProfile:
    snr_db: float; c50_db: float; music_ratio: float; speech_ratio: float; overlap_ratio: float
    clipping_ratio: float; loudness_lufs: float; source_sample_rate: int; channels: int; quality_mos: float
@dataclass(frozen=True)
class ProcessingPlan:
    steps: tuple[Step, ...]            # Loudnorm | Denoise | SeparateVocals | SplitChannels
    feed_asr: Literal["original", "enhanced"]; vad_threshold: float; flags: frozenset[str]
    skip_asr: bool
def plan_processing(p: AudioProfile, policy: RoutingPolicy) -> ProcessingPlan   # pure
class AudioProfiler(Protocol):
    async def profile(self, audio: AudioRef, span: SampleSpan) -> AudioProfile: ...
class Enhancer(Protocol):
    async def apply(self, audio: AudioRef, step: Step) -> AudioRef: ...
```

## Files
- `src/transcribe_engine/domain/routing.py` (+ `RoutingPolicy` with thresholds)
- `src/transcribe_engine/infrastructure/audio/{brouhaha,music_detector,dnsmos,loudness,deepfilternet,demucs}.py`
- `tests/unit/domain/test_routing.py`, `tests/contracts/test_profiler_contract.py`

## Rules (table from `[D: 1.5 تحليل الصوت والتوجيه]`, thresholds are *initial* config)
| Condition | Detection | Plan |
|---|---|---|
| clean | SNR > 15 dB | nothing |
| medium noise | 5–15 dB | DeepFilterNet for VAD/diarization only; original to ASR |
| heavy noise | < 5 dB | denoise for ASR only if S16 shows a gain; strict VAD; `low_snr` |
| music under speech | music_ratio > 30% | Demucs `htdemucs` (GPU) on those chunks only |
| music, no speech | speech ≈ 0 | `skip_asr`, `music` event |
| singing | AudioSet class | tenant setting, default `[غناء]` without transcription |
| reverb | low C50 | flag only |
| telephony | source 8 kHz | `telephony` flag + eval bucket |
| stereo, speaker per channel | 2 distinct channels | `SplitChannels`: process each channel separately |
| overlap | high overlap_ratio | `overlap=true` |
| quiet | < −35 LUFS | loudnorm to −23 LUFS |
| clipping | > 1% samples | flag only |
| no speech | speech_ratio < 2% | job COMPLETED, empty result, `no_speech`, no GPU |

- Profile stored per chunk and feeds segment confidence `[D: 1.5]`.
- Thresholds change only through `RoutingPolicy` version → bumps `pipeline_version` (S03 Q1).

## Acceptance criteria
- **AC-1** `[D: 1.5]` — `test_routing.py::test_policy_table` (unit): one parametrized case per table row.
- **AC-2** `[D: 1.5]` — `::test_clean_audio_has_no_steps` (unit).
- **AC-3** `[D: 1.5]` — `test_prepare_chunks.py::test_no_speech_completes_without_gpu` (unit, fakes).
- **AC-4** — `test_profiler_contract.py::test_snr_ordering` (contract, ml): mixes at 20/10/0 dB give
  decreasing SNR estimates.
- **AC-5** `[D: 1.5]` — `test_process_job.py::test_feed_asr_original_for_medium_noise` (unit).
- **AC-6** `[D: 1.5]` — `test_prepare_chunks.py::test_split_channels_keeps_two_tracks` (unit).

## Commit plan
1. `docs(S13): add spec`
2. `test(S13): add routing and profiler tests (xfail)`
3. `feat(S13): add AudioProfile and routing policy`
4. `feat(S13): add profiler adapters (Brouhaha, music detection, loudness, DNSMOS)`
5. `feat(S13): add enhancer adapters (DeepFilterNet, Demucs)`
6. `feat(S13): wire profiling and routing into PrepareChunks and ProcessJob`

## Open questions
- [x] Q1 — Add `PROFILING` stage (S02 Q3). Must be resolved first. (resolved by: autopilot, 2026-11-26, D-044): the stage already exists in `JobStage` (D-005).
- [ ] Q2 — Licenses of Brouhaha, DNSMOS, DeepFilterNet, Demucs for commercial use: check before merge.
