# 0010. Search ranking: a lexical gate, dense vectors reorder, RRF fuses, no reranker
Status: Accepted (S18, D-080, D-086)
Date: 2026-11-28   Slice: S18

## Context
The design describes hybrid search with a reranker. A first build ranked by vector alone, so every query returned its nearest
chunks, even a word that was never said (the negative control failed).

## Decision
The candidate set is the chunks that contain every query word after normalisation (`domain.text.normalize`, D-057). Vectors
only order those candidates. The two orders are fused with reciprocal rank fusion (`domain.rag.rrf`). No reranker in v1 (D-080).

## Alternatives considered
- Vector-only ranking: returns hits for any query. Rejected by the negative control.
- Vector-only with a similarity threshold: needs a threshold measured on real Arabic data (R-009). Not available yet.

## Consequences
- Precision first: a synonym that shares no word with the query is not found until a measured vector candidate source exists.
- Candidates are at most 50 per ranking, so a very common word can crowd out rarer matches. Acceptable for v1.
- The design's dense recall is deferred, and this is recorded as a deviation (D-086).
