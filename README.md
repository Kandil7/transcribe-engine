# Transcribe Engine

An Arabic batch speech-to-text platform, built Egyptian-dialect first. You submit an audio or video file,
and it returns a word-level transcript as JSON, with subtitles in SRT and VTT, plain text, Markdown and CSV.
Jobs run asynchronously on a Postgres-backed queue, with workers for ingest, speech recognition and webhook
delivery. Everything runs locally on one machine; no cloud account is needed.

- **Status:** the local pipeline runs end to end on a real Arabic clip (upload, ASR, subtitles). Several
  slices are partial and some decisions are open. See [Status](#status).
- **Design:** [`docs/design.md`](docs/design.md) (Arabic) is the source of truth. Decisions are in
  [`docs/DECISIONS.md`](docs/DECISIONS.md) (D-001 onward) and architecture records in [`docs/adr/`](docs/adr/).

## Contents

- [Features](#features)
- [Status](#status)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Quick start (local)](#quick-start-local)
- [Using the API](#using-the-api)
- [Output formats and subtitle profiles](#output-formats-and-subtitle-profiles)
- [Configuration](#configuration)
- [ASR engines and models](#asr-engines-and-models)
- [Make targets](#make-targets)
- [Testing and quality gates](#testing-and-quality-gates)
- [Repository layout](#repository-layout)
- [Models, licences and access](#models-licences-and-access)
- [Data handling and privacy](#data-handling-and-privacy)
- [Known limitations](#known-limitations)
- [Contributing and workflow](#contributing-and-workflow)

## Features

- **Async jobs:** submit a file, poll the job, fetch the result. Idempotency keys on submission, and cancel
  and delete on jobs.
- **Word-level transcripts:** every word has integer millisecond times and, when diarization is on, a speaker.
- **Subtitles:** SRT and VTT with right-to-left marks and a byte-order mark, in broadcast, YouTube and
  social-vertical profiles, with Arabic or Western numerals.
- **Other outputs:** canonical JSON, plain text, Markdown and CSV. Chapters and entity checks exist as domain
  logic; they have no API route yet.
- **Versioned transcripts:** human corrections are saved as new versions with optimistic concurrency
  (a stale edit gets `409`). Versions can be deleted.
- **Webhooks:** outbox-based delivery, HMAC-SHA256 signed, to HTTPS destinations only, with an SSRF guard,
  pinned-address delivery, retries over 24 hours and two active secrets for rotation.
- **Deletion and retention:** deleting a job removes its audio, rows and unshared results, and writes a
  content-free audit record. A retention sweep removes expired audio per tenant.
- **Observability:** JSON logs, Prometheus metrics (queue depth, queue wait, job outcomes), per-stage spans
  linked by job id, and alert rules with `promtool` tests in CI.
- **Pluggable ASR:** every engine sits behind one port. Local Whisper, a vLLM service, or a plumbing
  engine for tests.

## Status

Each slice (S00–S22) is in [`specs/`](specs/). The tracked state is in
[`.autopilot/state.json`](.autopilot/state.json) and [`docs/PROGRESS.md`](docs/PROGRESS.md).

| Area | State |
|---|---|
| Foundation, upload, ingest, queue, leases, reconciler (S01–S09) | Done |
| Chunking, merge and fan-out (S10, S11) | Done |
| Local ASR (Whisper large-v3-turbo) and the local demo (S12) | Working locally; verified on a real clip |
| Production ASR on vLLM (Cohere Transcribe Arabic) | Built and tested with mocks; not run on a GPU yet |
| Forced alignment (Arabic wav2vec2 ONNX aligner) | Adapter and placement tested; word-error accuracy not measured |
| Subtitles, formats, profiles (S15) | Done except the render cache and a viewer test of reading speed |
| Accuracy evaluation (S16) | Harness built; **no human reference transcripts yet**, so accuracy is unmeasured |
| Diarization (S17) | Port, assignment and Sortformer adapter built; NeMo not installed; accuracy unmeasured |
| RAG (S18), analytics and chapters (S19) | Pure domain and use cases; no embedder or LLM wired |
| Outbox, webhooks, observability (S20) | Done, with stage spans for the main stages |
| Deletion and retention (S21) | Built and tested; legal review and region pinning open |
| Corrections and versions (S22) | API built; training export waits for a privacy decision |

Open decisions are in [`docs/REVIEW_QUEUE.md`](docs/REVIEW_QUEUE.md). The most important ones: a human reference
hour to measure accuracy (R-001), the Egyptian data protection review (R-011), the privacy rules for the
training export (R-013), and the NeMo dependency for Sortformer (R-008).

## Architecture

Layers follow a strict dependency direction, enforced by import-linter:

```
presentation (FastAPI)  ─┐
infrastructure (DB, S3, ASR, ML, HTTP) ─┼─▶ application (use cases, ports) ─▶ domain (pure logic)
main.py: the only composition root ─────┘
```

- **`domain/`** imports only the standard library. It holds the job state machine (`JobState.transition()`
  is the only way to change state), time handling (integer samples inside the pipeline, integer milliseconds
  at boundaries), text normalization, merge, CTC alignment, subtitle cues and the canonical transcript.
- **`application/`** holds use cases (ingest, prepare chunks, process job, publish outbox, delete job data,
  save correction and others) and the **ports**: `typing.Protocol` interfaces for ASR, VAD, aligner,
  diarizer, storage, queue, clock and media probe. Every port has a fake in `tests/fakes/` and a contract
  test run against both the fake and the real adapter.
- **`infrastructure/`** holds the adapters: SQLAlchemy and Postgres (with row-level security), S3 (MinIO
  locally), Whisper through transformers, vLLM over HTTP, ONNX aligner, Sortformer, the webhook sender,
  Silero VAD and FFmpeg. Adapters translate library errors into `TransientError` (retry) or
  `PermanentError` (fail).
- **Pipeline:** `IngestJob` (validate, normalize to 16 kHz mono WAV, hand off) → `PrepareChunks` (VAD, then a
  chunk plan) → `ProcessJob` on the GPU queue (ASR per chunk, saved as it completes, then merge) →
  `save_transcript`. Workers claim jobs with `SELECT … FOR UPDATE SKIP LOCKED` under a lease; a reconciler
  reclaims expired leases.
- **Worker roles:** `cpu` (ingest and chunk planning), `gpu` (ASR; the only role that loads models), `publisher`
  (webhook delivery) and `sweeper` (deletions and retention).

## Requirements

- Windows 10/11, macOS or Linux.
- **Python 3.12** and **[uv](https://docs.astral.sh/uv/)**.
- **Docker** (Docker Desktop on Windows or macOS) for Postgres and MinIO, and for the integration tests
  (Testcontainers).
- **FFmpeg** and `ffprobe` on the path, for media probing and normalization.
- **Optional, for GPU:** an NVIDIA GPU with a recent driver. The local ASR works on CPU, slowly.

## Quick start (local)

```bash
make setup        # uv sync and git hooks
make setup-ml     # the ML extra (torch and friends): needed by the gpu worker in make dev
make up           # Postgres (pgvector) and MinIO in Docker
make check        # the gate: lint, types, import rules, unit tests
make migrate      # apply database migrations
make seed         # create a local tenant and API key (printed once, saved to .env.local)
make dev          # run the API and the cpu and gpu workers (Ctrl-C stops)
```

In a second terminal, with the key from `make seed` in `TE_API_KEY`:

```bash
make demo FILE=path/to/arabic-audio.mp3
```

This uploads the file, waits for the job, and writes `out/<job id>.json`. Use the API directly for
subtitles (see [Using the API](#using-the-api)).

**Windows notes.** Use Git Bash or PowerShell with `make` available. `make seed` keeps the key in
`.env.local`, which is git-ignored and never read back by the tools. Do not commit it.

### Running the GPU stack on Windows: use WSL2 (D-078)
On native Windows, the GPU worker crashed when the CPU worker ran alongside it. The stack runs reliably under WSL2 with the
same GPU. Run the GPU worker in WSL2 (Ubuntu 24.04):

1. Clone the repo inside WSL, then `uv sync --all-groups`.
2. Install torch from the CUDA index: `uv pip install --index-url https://download.pytorch.org/whl/cu126 "torch==2.14.1"`.
3. Install FFmpeg without `sudo`: `conda install -c conda-forge ffmpeg` into a conda environment on the PATH.
4. Postgres and MinIO keep running on Windows (`make up`); WSL reaches them through localhost.
5. Point `HF_HOME` at the Windows model cache, for example `/mnt/d/AI/Models/HuggingFace`.

### Optional: CUDA torch on this machine

The default `uv sync` installs the CPU build of torch, so the local ASR runs on CPU. For an NVIDIA GPU on
Windows, a CUDA build can be installed into the local environment only (not the shared lock file):

```bash
make gpu-torch    # CUDA 12.6 build of torch 2.14.1 (see D-073)
make gpu-check    # prints the GPU name and runs a small half-precision product on it
```

Run `make gpu-torch` again after any `uv sync`, because sync restores the lock file's CPU build. The
Whisper adapter uses CUDA automatically when torch sees a GPU (`TE_ASR_DEVICE` overrides this).

## Using the API

All routes need an API key in the `Authorization` header: `Authorization: Bearer <key>`. Keys are created by
`make seed`. Errors are JSON.

| Method and path | What it does |
|---|---|
| `POST /v1/uploads` | Create an upload ticket: a presigned `url`, form `fields`, `upload_id` and `max_bytes` (`201`). |
| `POST /v1/transcriptions` | Create a job from `upload_id` and `language`; optional `engine`, `diarization` and HTTPS `webhook_url` (`202`). Accepts `Idempotency-Key`. |
| `GET /v1/transcriptions/{job_id}` | Job state, stage, progress, warnings and error code. |
| `GET /v1/transcriptions/{job_id}/result` | The transcript. `format`: `json` (default), `canonical`, `txt`, `md`, `csv`, `srt`, `vtt`. |
| `GET /v1/transcriptions/{job_id}/subtitles` | Subtitles. `format`: `srt` (default) or `vtt`. `profile`, `numerals`. |
| `POST /v1/transcriptions/{job_id}:cancel` | Cancel a queued or running job (`202`). |
| `POST /v1/transcriptions/{job_id}/versions` | Save a corrected version. Send the base version; stale bases get `409` (`201` on success). |
| `DELETE /v1/transcriptions/{job_id}` | Request deletion of the job's data (`202`). |

Example, with the key in `$TE_API_KEY`:

```bash
# 1. Upload ticket: note upload_id, url and fields
curl -s -X POST http://localhost:8000/v1/uploads -H "Authorization: Bearer $TE_API_KEY"
# 2. Send the file to the ticket URL as a form: every key of "fields" first, then the file
curl -s -X POST "<url from the ticket>" -F "<key>=<value>" ... -F "file=@audio.mp3"
# 3. Create the job from the upload_id in the ticket
curl -s -X POST http://localhost:8000/v1/transcriptions  \
  -H "Authorization: Bearer $TE_API_KEY" -H "Content-Type: application/json"  \
  -H "Idempotency-Key: my-file-001" -d '{"upload_id": "<upload_id>", "language": "ar"}'
# 4. Poll until the state is COMPLETED
curl -s http://localhost:8000/v1/transcriptions/<job_id> -H "Authorization: Bearer $TE_API_KEY"
# 5. Subtitles
curl -s "http://localhost:8000/v1/transcriptions/<job_id>/subtitles?format=srt&profile=broadcast" -H "Authorization: Bearer $TE_API_KEY" -o out/<job_id>.srt
```

The OpenAPI schema is in [`docs/openapi.json`](docs/openapi.json); regenerate it with `make openapi`.

## Output formats and subtitle profiles

- **JSON (`format=json`):** the word-level body the pipeline produces, as stored for the job.
- **Canonical (`format=canonical`):** the versioned transcript that corrections build on. Its fields are
  `schema_version`, `transcript_id`, `version`, `source` (`asr` or `human`), `media`, `provenance` (engine,
  revision, pipeline version, configuration hash), `speakers`, `segments` (each with `start_ms`, `end_ms`,
  `speaker` and `words`, where a word has `text`, `start_ms`, `end_ms`, `lang` and `conf`), `events`
  and `warnings`. All times are integer milliseconds.
- **Subtitles:** cues are split without breaking Arabic prepositions and carry the right-to-left mark.
  Profiles set the limits:

| Profile | Characters per line | Maximum cue duration |
|---|---|---|
| `broadcast` (default) | 42 | 7 s |
| `youtube` | 42 | 6 s |
| `social_vertical` | 24 | 4 s |

Reading speed (17 characters per second) is an initial value, pending a viewer test (R-005 part b).

## Configuration

Settings are read from environment variables with the `TE_` prefix (see
[`src/transcribe_engine/infrastructure/settings.py`](src/transcribe_engine/infrastructure/settings.py)).
Defaults suit local development.

| Variable | Default | Purpose |
|---|---|---|
| `TE_DATABASE_URL` | local Postgres | Owner connection (migrations and workers). |
| `TE_S3_ENDPOINT_URL`, `TE_S3_ACCESS_KEY`, `TE_S3_SECRET_KEY`, `TE_S3_BUCKET` | local MinIO | Object storage. Local values are throwaway. |
| `TE_SCRATCH_DIR` | `.scratch` | Ingest and FFmpeg work files (git-ignored). |
| `TE_ASR_ENGINE` | `whisper_local` | `whisper_local`, `cohere_local`, `vllm` or `plumbing` (tests only). |
| `TE_ASR_MODEL_ID` | `openai/whisper-large-v3-turbo` | Local Whisper model (repository id, never a path). |
| `TE_ASR_DEVICE` | unset | `cuda` or `cpu`. Unset: CUDA when torch sees a GPU. |
| `TE_VLLM_URL` | `http://vllm:8000` | The vLLM service (compose profile `asr-gpu`). |
| `TE_VLLM_MODEL` | `CohereLabs/cohere-transcribe-arabic-07-2026` | Production model served by vLLM (D-067). |
| `TE_ALIGNER_MODEL_ID` | `parseh/aligner-ar` | Arabic forced aligner (D-070). |
| `TE_ALIGNER_REVISION` | pinned 40-character commit | Aligner revision; never a branch name. |
| `TE_CHUNK_MAX_MS` | `30000` | Longest chunk (ms). |
| `TE_CHUNK_PAD_MS` | `500` | Padding either side of a chunk. |
| `TE_CHUNK_OVERLAP_MS` | `1500` | Context shared by fixed windows. |
| `TE_ASR_CONCURRENCY` | `32` | Chunks in flight per job. |
| `TE_LEASE_SECONDS` | `120` | Job lease length. |
| `TE_POLL_SECONDS` | `1.0` | Idle wait between claim attempts. |

Never commit `.env`, `.env.local` or any key. The model access token for gated repositories is read from
`HF_TOKEN` in the environment.

## ASR engines and models

Every engine implements the same port. Choosing one is configuration, never a code branch in the pipeline.

| Engine | Where it runs | Word times | Status |
|---|---|---|---|
| `whisper_local`: `openai/whisper-large-v3-turbo` via transformers | This machine (CPU, or CUDA when available) | Native | Default locally. Verified on a real clip. About 14 s per 2 s clip on CPU, so use the GPU for real volumes. |
| `cohere_local`: `CohereLabs/cohere-transcribe-arabic-07-2026` via transformers, pinned to `c3e911b…` | This machine (CUDA float16 when available) | None; placed by the aligner | Verified to load offline and transcribe on the GPU (D-076). Accuracy unmeasured (D-075). |
| `vllm`: `CohereLabs/cohere-transcribe-arabic-07-2026` | vLLM service, compose profile `asr-gpu`, BF16 on Ampere or newer | None; placed by the aligner | Production default (D-067). Needs an accepted model licence and a token. Not run here yet. |
| `plumbing` | Nowhere | None | Tests of the pipeline only. Produces no words. |

Forced alignment uses `parseh/aligner-ar` (ONNX, Apache-2.0) with our own CTC Viterbi (D-070). Diarization
uses NVIDIA Sortformer v2 (CC-BY-4.0) behind the diarizer port (D-072); its runtime, NeMo, is not installed.

To run the production engine:

```bash
docker compose --profile asr-gpu up vllm     # first run downloads the model; needs HF_TOKEN
TE_ASR_ENGINE=vllm make dev
```

The vLLM service is pinned to a reviewed commit and runs with `--trust-remote-code` (approved in R-014,
D-069). It is not verified on a GPU yet.

## Make targets

| Target | What it does |
|---|---|
| `make setup` | `uv sync --all-groups` and install git hooks. |
| `make fmt` | Format and auto-fix. |
| `make lint`, `make typecheck`, `make imports` | Ruff, mypy (strict on `src/`), import-linter. |
| `make test` | Unit tests (no Docker). |
| `make check` | The fast gate: lint, types, imports and unit tests. Must pass on every commit. |
| `make itest` | Integration and contract tests with Testcontainers (needs Docker). |
| `make cov` | Unit and integration tests with the coverage gate. |
| `make ci` | What CI runs on every pull request. |
| `make up` / `make down` | Start or stop Postgres and MinIO. |
| `make migrate` | Apply Alembic migrations. |
| `make seed` | Create the local tenant and API key. |
| `make dev` | The API and the cpu and gpu workers, with logs. Start the `publisher` and `sweeper` roles separately: `python -m transcribe_engine.worker publisher`. |
| `make demo FILE=…` | Upload a file and save the JSON result to `out/`. |
| `make openapi` | Regenerate `docs/openapi.json`. |
| `make gpu-torch` / `make gpu-check` | CUDA torch for this machine, and a GPU check (see above). |
| `make eval` | Evaluation harness on the dev set (needs a reference set and a GPU; see R-001). |

## Testing and quality gates

- **Unit tests** run on fakes. Each acceptance criterion has a test that fails if the feature breaks.
- **Contract tests** run the same expectations against a fake and against each real adapter.
- **Integration tests** use real Postgres and MinIO through Testcontainers.
- **Strict xfail:** new acceptance tests start as `xfail(strict=True)` and the marker is removed in the
  commit that makes them pass. Tests are never edited to pass.
- **Architecture:** import-linter enforces the layer rules; `domain/` may not import third-party packages.
- **Alerts:** `promtool` rule tests run in the `alerts` CI job.
- **Commits:** conventional commits with the slice id as scope (for example `feat(S14): …`), checked by a
  hook. Every commit passes `make check`.

## Repository layout

```
src/transcribe_engine/
  domain/           pure logic (jobs, chunks, merge, CTC, subtitles, transcript, webhooks, …)
  application/     use cases and ports (Protocols)
  infrastructure/  adapters: db, storage, asr, alignment, diarization, http, observability, ml
  presentation/    FastAPI routes and schemas
  main.py          composition root (wiring)
  worker.py        worker roles: cpu, gpu, publisher, sweeper
tests/              unit, integration, contracts, fakes
migrations/         Alembic revisions (never edit an applied one)
specs/              one specification per slice, S00–S22
docs/               design, decisions, ADRs, build log, review queue, progress
evaluation/         metrics, gates and augmentation for the accuracy harness
deploy/observability/  alert rules and their tests
scripts/            dev, demo, seed, OpenAPI export, autopilot
```

## Models, licences and access

Check each licence before commercial use. Facts below are from the decision records; the model cards are
the authority.

| Component | Model or package | Licence (as recorded) | Access |
|---|---|---|---|
| Local ASR | `openai/whisper-large-v3-turbo` | Whisper card says Apache-2.0 for large-v3; turbo card not yet checked (D-068) | Public, cached locally |
| Production ASR | `CohereLabs/cohere-transcribe-arabic-07-2026` | Apache-2.0 | **Gated:** accept the terms on Hugging Face; set `HF_TOKEN` (D-069) |
| Aligner | `parseh/aligner-ar` | Apache-2.0 | Public, pinned commit (D-070) |
| Diarizer (planned) | `nvidia/diar_streaming_sortformer_4spk-v2` | CC-BY-4.0 | Public. NeMo not installed (D-072) |
| Runtime | `onnxruntime` | MIT | — (D-071) |
| Runtime | `protobuf` | BSD-3-Clause | — (transitive, D-071) |
| Runtime | `torch` | BSD-3-Clause | — |

Excluded on purpose: torchaudio MMS_FA (CC-BY-NC, non-commercial, D-070) and Sortformer v1 (CC-BY-NC, D-072).

## Data handling and privacy

- Audio and transcripts are stored per tenant, with row-level security in Postgres and tenant-scoped keys in S3.
- Logs carry identifiers and counts only: never transcript text, file names or audio.
- Deletion removes the job's audio, rows and unshared result, and writes a content-free audit record.
- Retention is per tenant. Webhook secrets are not stored yet; encryption at rest is a precondition of
  that writer (D-066).
- Production use under Egyptian data protection law, and where GPUs and data may run, is **not** decided
  (R-011). The training export is not built (R-013).

## Known limitations

- **Accuracy is unmeasured.** There are no human reference transcripts yet (R-001). Outputs are plausible,
  and the aligner and diarizer are placed correctly on a sample, but no word error rate or diarization error
  rate has been measured.
- **No production GPU run yet.** The vLLM path and the CUDA local path are built, but not verified on
  production hardware.
- **Word times for the production model depend on the aligner,** and the aligner is not yet tested on a
  reference set. Until it runs, the vLLM engine refuses text without word times rather than returning silence.
- **Diarization** has a port, assignment and an adapter, but no NeMo loader, no speaker-count input and no
  accuracy check.
- **Local speed:** about 14 seconds per two-second clip on CPU.
- **RAG and analytics** (S18, S19): pure logic only. No embedder, reranker or LLM is wired.
- **Render cache** for subtitles is not built; renders are computed on request.

## Contributing and workflow

- Read [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`CLAUDE.md`](CLAUDE.md) before changing code. Each slice is
  built from its spec on a `feat/SXX-<slug>` branch, one commit per plan step, through a pull request.
- Decisions that the spec does not cover are recorded in `docs/DECISIONS.md`, with an ADR when they are
  architectural.
- The build history is in [`docs/BUILD_LOG.md`](docs/BUILD_LOG.md). The autopilot workflow is described in
  [`docs/WORKFLOW.ar.md`](docs/WORKFLOW.ar.md) (Arabic).
