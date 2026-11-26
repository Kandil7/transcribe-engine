# Architecture decisions

| # | Title | Status |
|---|---|---|
| [0001](0001-clean-architecture-layers.md) | Clean Architecture with four enforced layers | Accepted |
| [0002](0002-postgres-as-queue.md) | Postgres is both source of truth and job queue | Accepted |
| [0003](0003-integer-time.md) | Integer samples inside, integer ms at boundaries | Accepted |
| [0004](0004-canonical-transcript.md) | One canonical transcript; every format derived | Accepted |
| [0005](0005-vllm-separate-service.md) | ASR model in a separate vLLM service | Accepted |
| [0006](0006-stage-handoff-between-queues.md) | One job row moves between cpu and gpu queues | Proposed |
| [0007](0007-default-asr-engine.md) | Default ASR engine | Provisional (S00 partial) |

New ADRs: `/write-adr <title>` in Claude Code.
