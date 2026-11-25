# Transcribe Engine

Arabic batch ASR platform (Egyptian dialect first). Design: `docs/design.md` (Arabic).
Read only the sections a task needs; specs in `specs/` name them. Decisions: `docs/adr/`.

## Commands
- `make check`  — format check, lint, types, import contracts, unit tests. Must pass before you finish.
- `make itest`  — integration + contract tests (Testcontainers: Postgres, MinIO). Needs Docker.
- `make up` / `make down` — local Postgres (pgvector) + MinIO.
- `uv run alembic revision --autogenerate -m "<msg>"` — new migration. Never edit an applied migration.
- `uv run pytest tests/unit/path::test_name -q` — run one test; prefer this while iterating.

## Architecture rules
- Layers: `domain` ← `application` ← `infrastructure` / `presentation`. Enforced by import-linter.
- `domain` imports only the standard library. `main.py` is the only composition root.
- Every external dependency (ASR, VAD, aligner, diarizer, storage, queue, clock, media probe)
  is a Port (`typing.Protocol`) in `application/ports/`, with a Fake in `tests/fakes/`
  and a contract test in `tests/contracts/` run against both the Fake and the real Adapter.
- Adapters translate library errors into `domain.errors.TransientError` / `PermanentError`.
- Job state changes only through `domain.jobs.JobState.transition()`. Never UPDATE state directly.
- No new abstraction (base class, factory, registry) without a second real implementation.

## Conventions that differ from defaults
- Time is integer samples inside the pipeline, integer milliseconds at boundaries. Never float seconds.
- Arabic text normalization only via `domain.text.normalize()`. No ad-hoc regex on Arabic text.
- IDs and cache keys are deterministic hashes defined in `domain.keys`. Never random IDs for chunks/results.
- Never log transcript text, file names or audio content. Log ids, durations, counts.
- Add a dependency only when a spec needs it; record it in `docs/DECISIONS.md` with its license.
  Never commit `.env` or secrets.

## Workflow
- Autonomous build: follow `prompts/AUTOPILOT.md`. State: `.autopilot/state.json`. Logs: `docs/BUILD_LOG.md`,
  `docs/DECISIONS.md`, `docs/REVIEW_QUEUE.md`. Never stop to ask; decide, record, continue.
- Work one slice at a time from `specs/SXX-*.md` on branch `feat/SXX-<slug>`. See `CONTRIBUTING.md`.
- Commit after every step in the spec's commit plan. Every commit must pass `make check`.
- New acceptance tests start as `@pytest.mark.xfail(strict=True, reason="SXX")`; remove the marker
  in the commit that makes them pass.
- IMPORTANT: never edit or delete an existing test to make it pass. If a test is truly wrong, fix it
  in its own `fix(SXX): correct <AC> test` commit with the reason and a decision entry.
- A decision not covered by the spec or design doc → write an ADR (`/write-adr`) in the same branch.
- When compacting, keep: current slice ID, spec path, files changed, failing tests, next commit step.
