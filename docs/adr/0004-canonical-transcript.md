# 0004. One canonical transcript; every format is derived
Status: Accepted
Date: 2026-11-24   Slice: S15

## Context
Outputs include JSON, TXT, Markdown, CSV, SRT, VTT, later ASS/TTML/SBV, RAG chunks and enrichment.
Formats generated from each other lose information (speakers, word times, confidence, language spans).

## Decision
A versioned, immutable JSON transcript (schema 1.0, see docs/design.md "التمثيل المرجعي") is the only
stored representation. Renderers are pure functions from it. `raw_text`, `search_text` and the offset
map are derived from words. Corrections create a new version.

## Consequences
- Adding a format never touches the pipeline.
- Re-rendering is cheap, so formats are rendered on request with a cache.
- Schema changes need a version bump and a migration path for stored transcripts.
