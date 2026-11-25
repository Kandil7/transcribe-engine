# 0008. Arabic normalizer is a domain character table, not a CAMeL adapter
Status: Accepted (S04, D-008)
Date: 2026-11-26   Slice: S04

## Context
The design says normalization runs through CAMeL Tools instead of a hand-written regex. The search,
RAG and evaluation layers need one normalizer that maps every search character back to its source
character (an exact offset map). CLAUDE.md keeps `domain` on the standard library and forbids an
abstraction without a second implementation.

## Decision
Implement the normalization rules in `domain/text.py` as a fixed character table with single-pass code.
Each rule is one-to-one or a deletion, so the offset map is exact. CAMeL Tools is reserved for
morphology (lemmas, roots), which is outside this rule set, and would enter later behind a Port.

## Alternatives considered
- A `TextNormalizer` Port with a CAMeL adapter: a dependency for rules that are a fixed table; no
  exact offset guarantee; a second implementation does not exist yet.

## Consequences
- The rules are testable without a model or a network call; the case table pins their behaviour.
- A future morphology feature does not change these rules; it adds a separate Port.
- Whitespace collapse and lowercasing are defined per D-010 so the offset map stays exact.
