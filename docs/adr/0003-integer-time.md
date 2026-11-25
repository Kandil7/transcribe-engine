# 0003. Integer samples inside, integer milliseconds at boundaries
Status: Accepted
Date: 2026-11-24   Slice: S03

## Context
Hundreds of chunks per file are offset, padded and merged. Float seconds accumulate rounding error and
make "is this word inside the chunk core" comparisons unstable.

## Decision
Inside the pipeline, all positions are integer sample indices at 16 kHz. At API, storage and output
boundaries, integer milliseconds. Conversions only through `domain.time`. Floats for time are a review
finding.

## Consequences
- Merge and dedupe are exact; property tests use zero tolerance.
- Formats needing seconds (`?t=` deep links, SRT `HH:MM:SS,mmm`) format from integer ms.
