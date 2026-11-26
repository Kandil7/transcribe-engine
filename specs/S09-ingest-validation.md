# S09 — Ingest: probe, hash, dedupe, normalize

| | |
|---|---|
| Phase | 2 |
| Depends on | S06, S07 |
| Branch | `feat/S09-ingest-validation` |
| Design sections | تدفق البيانات › دورة الطلب (6–7)؛ الأمان › فحص الملفات وعزل FFmpeg؛ خط الأنابيب › 1. تطبيع الصوت؛ حدود التشغيل المبدئية |
| ADRs | 0006 |

## Goal
The CPU worker turns an uploaded file into either a cache hit, a clear permanent failure, or a
normalized 16 kHz mono PCM WAV in storage with the job handed to the GPU queue.

## Interfaces
```python
@dataclass(frozen=True)
class MediaInfo:
    format_name: str; duration_ms: int; sample_rate: int; channels: int; size_bytes: int
class MediaProbe(Protocol):
    async def probe(self, path: Path) -> MediaInfo: ...          # PermanentError on bad media
class AudioNormalizer(Protocol):
    async def to_pcm16_mono_16k(self, src: Path, dst: Path) -> NormalizedAudio: ...
class IngestJob:   # use case, handler for queue "cpu"
    async def __call__(self, job: Job, lease: Lease) -> None: ...
```

## Files
- `src/transcribe_engine/application/use_cases/ingest_job.py`, `normalize_audio.py`
- `src/transcribe_engine/application/ports/media.py`
- `src/transcribe_engine/infrastructure/media/{ffprobe,ffmpeg,sandbox}.py`
- `tests/fakes/media.py`, `tests/contracts/test_media_contract.py`
- `tests/integration/fixtures/media/` — tiny generated files (sine, silence, corrupt, playlist, too long)

## Rules
- SHA-256 computed while streaming from storage, never loading the whole file `[D: دورة الطلب 6]`.
- ffprobe decides the format; allow-list: mp3, m4a, aac, wav, flac, ogg/opus, mp4, mkv, webm `[D: فحص الملفات]`.
- Rejected: HLS (`m3u8`), `concat`, any protocol other than `file` (`-protocol_whitelist file`) `[D: فحص الملفات]`.
- Sandbox: subprocess with list argv, no shell, no network, non-root, cgroup memory/CPU limits,
  read-only FS except work dir; ffprobe timeout 30 s; conversion timeout proportional to duration `[D: فحص الملفات]`.
- Limits: duration ≤ 3 h, size ≤ 4 GB (config) `[D: حدود التشغيل المبدئية]`; `head()` size checked too.
- Then `result_key` (S03): COMPLETED result exists → `CACHE_HIT`, `ref_count + 1`; running job with
  same key → wait (Q1); else `VALIDATED` `[D: دورة الطلب 7]`.
- Normalization to `16 kHz mono PCM s16le WAV` stored at `work/{tenant}/{job}/audio.wav`, then
  `STAGE_HANDOFF` to queue `gpu` `[D: 1. تطبيع الصوت؛ ADR-0006]`.
- Error mapping: corrupt → `INVALID_MEDIA`, format → `UNSUPPORTED_FORMAT`, too long → `TOO_LONG`,
  too big → `TOO_LARGE`: all permanent, no retry `[D: آليات الاعتمادية]`.

## Acceptance criteria
- **AC-1** `[D: فحص الملفات]` — `test_media_contract.py::test_playlist_rejected` (integration): an `.mp3`
  that is really an m3u8 pointing at `file:///etc/passwd` → `UNSUPPORTED_FORMAT`, no file read outside work dir.
- **AC-2** `[D: فحص الملفات]` — `::test_extension_ignored_format_from_probe` (integration).
- **AC-3** `[D: حدود التشغيل]` — `test_ingest_job.py::test_too_long_fails_permanently` (unit, fakes).
- **AC-4** `[D: دورة الطلب 7]` — `test_ingest_job.py::test_cache_hit_completes_without_gpu` (unit).
- **AC-5** `[D: دورة الطلب 6]` — `test_ingest_job.py::test_hash_streamed` (unit): fake storage asserts
  no single read larger than the stream chunk.
- **AC-6** `[D: 1. تطبيع الصوت]` — `test_media_contract.py::test_output_is_pcm16_mono_16k` (integration).
- **AC-7** `[ADR-0006]` — `test_ingest_job.py::test_handoff_to_gpu_queue` (unit).
- **AC-8** — `test_media_contract.py::test_probe_timeout_is_transient` (integration with a stalled fake binary).

## Commit plan
1. `docs(S09): add spec`
2. `test(S09): add ingest and media tests (xfail)`
3. `feat(S09): add media ports and fakes`
4. `feat(S09): add sandboxed ffprobe adapter with format allow-list`
5. `feat(S09): add streaming hash and limits`
6. `feat(S09): add cache-hit and dedupe via result_key`
7. `feat(S09): add ffmpeg normalization and hand-off`

## Open questions
- [x] Q1 — "لو وُجدت مهمة جارية، تنتظرها": how does a duplicate wait? Proposed: the job records
  `awaits_result_key`; when the leader completes, the same transaction moves followers to COMPLETED
  (ref_count += n). If the leader fails, followers re-enter VALIDATED (one becomes the new leader).
  **Resolved (deferred to S10; resolved by: autopilot, 2026-11-26, D-029):** S09 does not make a duplicate
  wait. It completes from a stored result when one exists (CACHE_HIT) and otherwise runs its own GPU stage.
  An in-flight marker needs a schema change, and S10 owns result persistence and the claim at write time.
- [x] Q2 — Mono downmix loses "stereo with one speaker per channel" (S13). Proposed: store
  `channels` in `media`; S13 may request per-channel normalization before hand-off.
  **Resolved (resolved by: autopilot, 2026-11-26, D-029):** `channels` comes from the probe and is logged
  as a count. It is not persisted in S09. S13 adds the column with its own migration.
