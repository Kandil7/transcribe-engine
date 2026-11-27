# Build progress

Kept in sync with `.autopilot/state.json` by the autopilot. Status: `todo` · `in_progress` · `partial` · `blocked` · `done`.

**Autopilot status:** blocked on owner decisions (see docs/REVIEW_QUEUE.md)   **Last update:** 2026-11-27

| Order | Slice | Title | Status | Branch | Merged (main) | Tag | Notes |
|---|---|---|---|---|---|---|---|
| 1 | S01 | Repo foundation and CI | done | — | 2985206 | v0.1.0 | PR #1 merged (rebase) |
| 2 | S00 | Model selection spike | partial | spike/S00-model-selection | 6a2aae9 (PR #19) | — | guidelines + validator + ADR-0007 (provisional); R-001 open |
| 3 | S02 | Job state machine | done | — | 714136b | — | PR #5 merged (rebase) |
| 4 | S03 | Pipeline config, keys, time units | done | — | eb5dd15 | — | PR #7 merged (rebase) |
| 5 | S04 | Arabic text normalization | done | — | c909f6c | — | PR #9 merged (rebase) |
| 6 | S07 | Object storage and presigned uploads | done | — | a29dd33 | — | PR #11 merged (rebase) |
| 7 | S05 | Schema, repositories, unit of work | done | — | 2af874b | — | PR #13 merged (rebase) |
| 8 | S06 | Postgres job queue, lease, fencing, reconciler | done | — | f216ccd | — | PR #15 merged (rebase) |
| 9 | S08 | API, auth, job endpoints | done | — | f9eeca3 | — | PR #17 merged (rebase) |
| 10 | S09 | Ingest: probe, hash, dedupe, normalize | done | feat/S09-ingest-validation | 8e24311 (PRs #21, #23) | — | D-030, D-031: fenced ref increment and worker wiring deferred to S10 |
| 11 | S10 | Chunk plan, fan-out, merge | done | feat/S10-result-refs | pending | v0.2.0 | make dev and make demo on this machine; plumbing ASR/VAD (D-035) |
| 12 | S11 | VAD with cut and merge | done | fix/S11-mypy-numpy (PR #29) | | | |
| 13 | S12 | ASR adapters (local Whisper turbo) | partial | feat/R003-local-asr | 80e0ef3 (PR #53) | — | local demo verified; CUDA and vLLM model open (R-003 b) |
| 14 | S15 | Canonical transcript and renderers | todo | | | v0.3.0-local | **local demo** |
| 15 | S13 | Audio profiling and routing | todo | | | | |
| 16 | S14 | Forced alignment | todo | | | | |
| 17 | S16 | Evaluation harness | partial | — | 09d77ce (PR #39) | v0.4.0 pending | metrics, SNR mix, gate; accuracy unmeasured (R-001) |
| 18 | S17 | Speaker diarization | partial | — | PR #41 | — | assignment, port, wiring; AC-4/AC-5 deferred (R-008) |
| - | S18 | RAG chunks, embeddings, hybrid search | partial | — | PR #43 | — | chunks, boundaries, RRF (AC-1 to AC-4); index, pgvector, API deferred (R-009) |
| 20 | S20 | Outbox, webhooks, observability | partial | — | 7b8c5dc (PR #35) | — | delivery, logs, metrics, alerts; spans and metric values not wired (follow-up) |
| - | S19 | Enrichment | partial | — | PR #45 | — | analytics, snapping, verified entities; API and LLM deferred (R-010) |
| 22 | S21 | Privacy, retention, deletion | todo | | | | |
| - | S22 | Corrections and training export | partial | — | PR #48, #50 | — | save, diff, consented manifest, SQL versions, endpoint; aligner (R-005), re-index, DB-backed export deferred |
| — | Final acceptance | | todo | | | v1.0.0-local | `docs/FINAL_REPORT.md` |
