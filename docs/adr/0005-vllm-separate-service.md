# 0005. The ASR model runs in a separate vLLM service
Status: Accepted
Date: 2026-11-24   Slice: S12

## Context
Loading the model inside the worker process ties one job to one GPU, conflicts with forking after CUDA
initialization, and leaves the GPU idle between a file's chunks.

## Decision
The model is served by vLLM (BF16, no GGUF in production) as its own service. The GPU worker sends all
chunks of a job concurrently over HTTP (bounded semaphore), and vLLM's continuous batching packs them,
including across jobs. Alignment and diarization stay in a worker subprocess restarted every N jobs.

## Consequences
- `concurrency=1` applies to the worker, not the GPU.
- Engine swap = different vLLM launch args + Adapter; the worker image stays small.
- Audar (Qwen3-ASR format) support on vLLM must be verified in S00; fallback runtime recorded in ADR-0007.
