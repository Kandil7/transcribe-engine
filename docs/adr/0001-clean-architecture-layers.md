# 0001. Clean Architecture with four enforced layers
Status: Accepted
Date: 2026-11-24   Slice: S01

## Context
The product mixes deterministic logic (validation, hashing, state, permissions, retries) with
probabilistic components (VAD, ASR, alignment, diarization) whose engines will change.

## Decision
Four layers under `src/transcribe_engine/`: domain ← application ← infrastructure / presentation, with
`main.py` as the only composition root. Every external dependency is a Port in `application/ports`.
Rules are enforced by import-linter contracts in `pyproject.toml`, run in `make check`.

## Alternatives considered
- Convention only: erodes under agent-written code; violations found late.
- Microservices per stage: operational cost before the batch engine is proven (design: out of scope).

## Consequences
- Domain and application are testable with Fakes, no GPU, no Docker.
- Every new engine is an Adapter + contract test, not a refactor.
- No DTO per layer: domain dataclasses cross into application; Pydantic stays in presentation.
