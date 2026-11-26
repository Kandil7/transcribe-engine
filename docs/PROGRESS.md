# Build progress

Kept in sync with `.autopilot/state.json` by the autopilot. Status: `todo` · `in_progress` · `partial` · `blocked` · `done`.

**Autopilot status:** running   **Current slice:** —   **Last update:** 2026-11-26

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
| 10 | S09 | Ingest: probe, hash, dedupe, normalize | partial | feat/S09-ingest-validation | a5d306a (PR #21) | — | reviewers pending; dref confinement open (D-030) |
| 11 | S10 | Chunk plan, fan-out, merge | todo | | | v0.2.0 | adds `make dev`, `make demo` |
| 12 | S11 | VAD with cut and merge | todo | | | | |
| 13 | S12 | ASR adapters (local profile first) | todo | | | | |
| 14 | S15 | Canonical transcript and renderers | todo | | | v0.3.0-local | **local demo** |
| 15 | S13 | Audio profiling and routing | todo | | | | |
| 16 | S14 | Forced alignment | todo | | | | |
| 17 | S16 | Evaluation harness | todo | | | v0.4.0 | |
| 18 | S17 | Speaker diarization | todo | | | | |
| 19 | S18 | RAG indexing and search | todo | | | | |
| 20 | S20 | Outbox, webhooks, observability | todo | | | | |
| 21 | S19 | Enrichment | todo | | | | |
| 22 | S21 | Privacy, retention, deletion | todo | | | | |
| 23 | S22 | Corrections and training export | todo | | | v0.5.0 | |
| — | Final acceptance | | todo | | | v1.0.0-local | `docs/FINAL_REPORT.md` |
