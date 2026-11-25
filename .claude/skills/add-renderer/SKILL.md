---
name: add-renderer
description: Add an output format renderer (SRT, VTT, ASS, TTML, SBV, TXT, Markdown, CSV, chapters) from the canonical transcript.
---
1. Renderers are pure functions in `src/transcribe_engine/domain/render/<format>.py`:
   `def render_<format>(t: CanonicalTranscript, opts: <Format>Options) -> str | bytes`.
   No I/O, no clock, no randomness. Same input → byte-identical output.
2. Build from words and segments of the canonical transcript, never from another format.
3. Subtitle formats take a `SubtitleProfile` (docs/design.md, "الترجمات المرئية"):
   cue segmentation is shared in `domain/render/cues.py`; the renderer only serializes cues.
4. Arabic rules: RLM (U+200F) at line start and after trailing punctuation; numerals per
   `opts.numerals`; UTF-8 (SRT with BOM when `opts.bom=True`).
5. Tests: golden files in `tests/unit/render/golden/<format>/`. One small canonical fixture
   (Arabic + English code-switch + numbers + two speakers + a music event), one golden output per profile.
   Update goldens only with `--update-goldens` and review the diff by eye.
6. Register the format in the renderer registry used by the API (`format=` query param).
