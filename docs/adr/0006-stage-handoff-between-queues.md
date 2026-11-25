# 0006. One job row moves between the cpu and gpu queues
Status: Accepted (S02, D-005)
Date: 2026-11-24   Slice: S02

## Context
The design runs probing, hashing, normalization, profiling and VAD on CPU workers and ASR, alignment
and diarization on GPU workers, but its state table has a single `PROCESSING` state and no transition
back to `QUEUED`.

## Decision
Keep one job row. Add `queue` (`cpu` | `gpu`) and `stage` columns and one event, `STAGE_HANDOFF`:
`PROCESSING → QUEUED` with the queue switched to `gpu` once the CPU stages are done.
`PENDING_VALIDATION` jobs are claimable on the `cpu` queue without changing state.
Per-chunk work inside a job runs concurrently in the GPU worker; chunk-level task rows across
workers are deferred until a single file exceeds one worker's timeout budget.

## Alternatives considered
- Separate task rows per stage under each job: more general, more code and states now.
- Everything on the GPU worker: wastes GPU time on FFmpeg and VAD.

## Consequences
- Update the design doc's state table and diagram when accepted.
- `attempt_count` counts claims across both queues; the attempt limit applies per job.
