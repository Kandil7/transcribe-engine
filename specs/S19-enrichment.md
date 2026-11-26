# S19 — Enrichment: chapters, summaries, entities, analytics

| | |
|---|---|
| Phase | 5 |
| Depends on | S18 |
| Branch | `feat/S19-enrichment` |
| Design sections | نواتج النظام والـ RAG › الإثراء (Enrichment)؛ التخزين والـ API (artifacts) |
| ADRs | — |

## Goal
Asynchronous, versioned artifacts derived from a transcript version, never modifying it, starting with
the ones that improve RAG directly.

## Scope
- In: chapters with titles and times (+ YouTube chapters format), file and chapter summaries,
  entities with times, speaker analytics (talk time, speech rate, silence, interruptions), hypothetical
  questions per RAG chunk.
- Out (→ S19b): speaker-name suggestions, translation with original timings `[D: الإثراء]` — listed in the
  design, scheduled after the first five by the implementation order.

## Interfaces
```python
@dataclass(frozen=True)
class Artifact:
    artifact_id: str; transcript_id: str; transcript_version: int
    kind: Literal["chapters", "summary", "entities", "analytics", "questions"]
    model: str; version: str; payload: Mapping[str, object]
class Enricher(Protocol):   # LLM-backed
    async def chapters(self, t: CanonicalTranscript) -> Sequence[Chapter]: ...
    async def summary(self, text: str, max_words: int) -> str: ...
    async def entities(self, t: CanonicalTranscript) -> Sequence[TimedEntity]: ...
    async def questions(self, chunk: RagChunk, n: int) -> Sequence[str]: ...
def speaker_analytics(t: CanonicalTranscript) -> SpeakerAnalytics   # pure, no LLM
```

## Files
- `src/transcribe_engine/domain/{analytics,chapters}.py`
- `src/transcribe_engine/application/use_cases/enrich_transcript.py`
- `src/transcribe_engine/infrastructure/llm/enricher.py`; migration for `artifacts`
- `src/transcribe_engine/presentation/api/routes_results.py` — `GET /v1/transcriptions/{id}/chapters?format=json|youtube`

## Rules `[D: الإثراء]`
- Runs after `transcript.completed`; each artifact has its own model + version; transcript untouched.
- Chapter times snap to segment boundaries from the transcript, never times invented by the LLM.
- Entities must be substrings of the transcript (verified); otherwise dropped and counted.
- Chapters become RAG parent chunks; questions are indexed with their chunk (S18).
- Event `enrichment.completed` (S20). Failure of one artifact does not block others.

## Acceptance criteria
- **AC-1** — `test_analytics.py::test_talk_time_and_rate` (unit).
- **AC-2** — `test_chapters.py::test_times_snap_to_segments` (unit, fake enricher returns off-grid times).
- **AC-3** — `test_enrich_transcript.py::test_entities_verified_against_text` (unit).
- **AC-4** — `test_enrich_transcript.py::test_transcript_unchanged` (unit): bytes before == after.
- **AC-5** — `test_enrich_transcript.py::test_one_failure_does_not_block_others` (unit).
- **AC-6** — `test_api_results.py::test_youtube_chapters_format` (integration): starts at `00:00`.

## Commit plan
1. `docs(S19): add spec`
2. `test(S19): add enrichment tests (xfail)`
3. `feat(S19): add speaker analytics`
4. `build(S19): add artifacts table`
5. `feat(S19): add enricher port, fake and LLM adapter`
6. `feat(S19): add chapters with snapping and summaries`
7. `feat(S19): add verified entities and chunk questions`
8. `feat(S19): add chapters endpoint`

## Open questions
- [x] Q1 — (resolved by: autopilot, 2026-11-27, D-058; R-010) Which LLM, hosted where (privacy: transcripts leave the cluster?). No LLM is wired: a hosted model would send transcripts out, which needs the owner's decision. The Enricher port is built with a fake; a local model waits for R-010.
