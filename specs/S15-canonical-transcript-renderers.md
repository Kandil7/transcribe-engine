# S15 — Canonical transcript and renderers

| | |
|---|---|
| Phase | 4 |
| Depends on | S04, S10 |
| Branch | `feat/S15-canonical-transcript-renderers` |
| Design sections | نواتج النظام والـ RAG › التمثيل المرجعي، الصيغ المشتقة، الترجمات المرئية، التخزين والـ API |
| ADRs | 0004 (single canonical transcript) |

## Goal
One versioned JSON transcript is the source of every output; JSON, TXT, Markdown, CSV, SRT and
WebVTT render from it deterministically, with correct Arabic direction in players.

## Scope
- In: canonical schema 1.0, serializer + JSON Schema file, derived `raw_text` / `search_text` / offset
  map, `SubtitleProfile` + cue segmentation, renderers JSON, TXT, MD, CSV, SRT, VTT, API `format=` and
  `/subtitles?profile=`.
- Out (→ later, on demand): ASS, TTML, SBV, Parquet `[D: ترتيب التنفيذ: "باقي الصيغ حسب الطلب"]`.
  (→ S19): chapters format.

## Interfaces
```python
@dataclass(frozen=True)
class CanonicalTranscript:
    schema_version: str; transcript_id: str; version: int; source: Literal["asr", "human"]
    media: MediaMeta; provenance: Provenance; speakers: tuple[Speaker, ...]
    segments: tuple[Segment, ...]; events: tuple[Event, ...]; warnings: tuple[str, ...]
    def raw_text(self) -> str: ...
    def search_text(self) -> NormalizedText: ...
def to_json(t: CanonicalTranscript) -> bytes: ...
def from_json(b: bytes) -> CanonicalTranscript: ...
@dataclass(frozen=True)
class SubtitleProfile:
    max_chars_per_line: int = 42; max_lines: int = 2; min_duration_ms: int = 833
    max_duration_ms: int = 7000; max_cps: float = 17.0; min_gap_ms: int = 80
    break_on_speaker_change: bool = True; numerals: Literal["western", "arabic_indic"] = "western"
def build_cues(t: CanonicalTranscript, p: SubtitleProfile) -> tuple[Cue, ...]
def render_srt(cues: Sequence[Cue], *, bom: bool = True) -> bytes: ...
def render_vtt(cues: Sequence[Cue], *, speakers: bool = True) -> str: ...
```

## Files
- `src/transcribe_engine/domain/transcript.py` (extend), `domain/render/{json_,txt,md,csv_,cues,srt,vtt}.py`
- `docs/schemas/transcript-1.0.json`
- `src/transcribe_engine/presentation/api/routes_results.py`
- `tests/unit/render/golden/**`, `tests/unit/render/test_*.py`

## Rules
- Schema fields as in "التمثيل المرجعي"; integer ms; `lang` per word; immutable; corrections create a
  new version `[D: التمثيل المرجعي]`.
- `raw_text`, `search_text` and offsets derived from words, never stored separately `[D]`.
- Cue ≠ segment; profile defaults per table; cut at punctuation, then before conjunctions/prepositions;
  never split a preposition from its word; break on speaker change `[D: الترجمات المرئية]`.
- RLM (U+200F) at line start and after trailing punctuation; SRT UTF-8 with BOM; numerals per profile
  `[D: الترجمات المرئية]`.
- Formats rendered on request with cache; JSON stored once `[D: التخزين والـ API]`.
- Profiles `broadcast`, `youtube`, `social_vertical` `[D: الترجمات المرئية]`.

## Acceptance criteria
- **AC-1** `[D: التمثيل المرجعي]` — `test_json.py::test_round_trip_and_schema_valid` (unit, Hypothesis).
- **AC-2** `[D]` — `test_json.py::test_search_text_derived_from_words` (unit).
- **AC-3** `[D: الترجمات المرئية]` — `test_cues.py::test_profile_limits_hold` (Hypothesis): chars/line,
  lines, duration bounds, cps, gaps.
- **AC-4** `[D]` — `test_cues.py::test_no_preposition_split` (unit, Arabic fixture).
- **AC-5** `[D]` — `test_srt.py::test_golden_broadcast`, `test_vtt.py::test_golden_speakers` (golden).
- **AC-6** `[D]` — `test_srt.py::test_rlm_and_bom` (unit): every line starts with U+200F; file starts with BOM.
- **AC-7** — `test_render_determinism.py::test_byte_identical` (unit).
- **AC-8** `[D: التخزين والـ API]` — `test_api_results.py::test_formats_and_profiles` (integration).

## Commit plan
1. `docs(S15): add spec`
2. `test(S15): add schema, cue and golden tests (xfail)`
3. `feat(S15): add canonical transcript schema and JSON serializer`
4. `feat(S15): derive raw and search text from words`
5. `feat(S15): add subtitle profiles and cue builder`
6. `feat(S15): add SRT and VTT renderers with RTL rules`
7. `feat(S15): add TXT, Markdown and CSV renderers`
8. `feat(S15): add result and subtitle endpoints with cache`

## Open questions
- [ ] Q1 — Reading speed 17 cps and 42 chars/line are initial values; confirm for Arabic with a viewer test.
