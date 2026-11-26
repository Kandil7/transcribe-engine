# Build log — how the system was built

One section per slice, written while the slice is built and committed in its final docs commit.
Template:

```
## SXX — <title>   (<start> → <end>)
Branch: feat/SXX-…   Merged: <main hash>   Tag: <if any>
### What was built
### How it works
### Steps and commits
| # | Commit | What changed | Tests turned green |
### Verification
### Decisions
### Problems and fixes
### Review findings
### Follow-ups
```

---

## Bootstrap — local runtime, MinIO image, CI config   (2026-11-25 → 2026-11-25)
Branch: fix/bootstrap (PR #3)   Merged: ffe877c   Tag: —
### What was built
Machine discovery (`docs/LOCAL_ENV.md`), local runtime profile D-001, MinIO image change D-002,
import-linter config that CI needed. `make setup`, `make up`, `make check` green on this machine.
### How it works
`make up` starts Postgres (pgvector) and MinIO (Chainguard build). MinIO liveness is checked from the
host because the distroless image has no `mc` for a container healthcheck.
### Steps and commits
| # | Commit | What changed | Tests turned green |
|---|---|---|---|
| 1 | fix(repo): use available MinIO image and host-side health check | compose image, Makefile `up` | — |
| 2 | docs(repo): record bootstrap decisions and local environment | D-001, D-002, LOCAL_ENV | — |
| 3 | chore(repo): start autopilot | `.autopilot/state.json` | — |
| 4 | fix(repo): declare external packages for import-linter | pyproject (uncommitted before) | CI `check` job |
### Verification
`make check`: ruff, mypy, lint-imports (4 contracts KEPT), unit tests pass. PR #3: check, commits, integration green.
### Decisions
D-001, D-002
### Problems and fixes
- `minio/minio` and `quay.io/minio/minio` refused on this machine → Chainguard MinIO (D-002).
- `main` CI red on first push: import-linter config lacked `include_external_packages` (the fix was
  uncommitted locally). Fixed in step 4.
- `python3` is a Windows Store stub here; autopilot scripts use `.venv\Scripts\python.exe`.
- Pre-commit's stash/restore left the user's unrelated pending files (prompt move, checkpoint) staged.
  Unstaged with `git restore --staged`; not committed.
### Review findings
Not applicable (configuration only).
### Follow-ups
- Repo has a stray `nul` file (HTML) at root; gitignored, left alone.

## S01 — Repo foundation and CI   (2026-11-25 → in progress)
Branch: feat/S01-foundation   Merged: — (blocked on push, see Problems)   Tag: —
### What was built
Settings (`TE_` prefix, `src/transcribe_engine/infrastructure/settings.py`), Alembic with async
engine (`alembic.ini`, `migrations/env.py`, `script.py.mako`), empty baseline `0001_baseline`, and the
migration round-trip test (AC-4).
### How it works
`env.py` reads `Settings().database_url`, builds an async engine, and runs migrations in one
connection. `alembic upgrade head` on the local Postgres records `0001_baseline` in `alembic_version`.
### Steps and commits
| # | Commit | What changed | Tests turned green |
|---|---|---|---|
| 1 | docs(S01): add spec | Q1 resolved: GitHub Actions | — |
| 2 | build(S01): add settings and alembic baseline | settings, alembic, baseline | — |
| 3 | test(S01): add migration round-trip test | `tests/integration/test_migrations.py` | AC-4 |
| 4 | build(S01): set alembic path separator and asyncio loop scope | alembic.ini, pyproject | silences warnings |
### Verification
- AC-1: `make check` passes (ruff, mypy, lint-imports 4 KEPT, unit tests).
- AC-2: probe `import fastapi` in `domain/errors.py` → `make imports` exit 2, `Domain is pure … BROKEN`;
  probe reverted, nothing committed.
- AC-3: `make up` → Postgres and MinIO healthy; `make migrate` → `Running upgrade -> 0001_baseline`.
- AC-4: `make itest` → `1 passed` (Testcontainers `pgvector/pgvector:pg16`, upgrade/downgrade/upgrade).
- AC-6: `scripts/check_commit_msg.py` on `fixed stuff` → exit 1.
- AC-5: verified after merge. CI run on PR #1 head passed (`check`, `integration`).
### Decisions
D-001 (runtime profile), D-002 (MinIO image)
### Problems and fixes
- The remote `feat/S01-foundation` had been updated by another run (`pull --rebase`) and carried the
  bootstrap and S00 commits again under new hashes. A rebase of that tip conflicted, so the S01 branch
  was rebuilt from `main` with cherry-picks. The old tip is kept locally as `bak/S01-with-stray-prompt`
  and `bak/S01-pre-dedupe`.
- The first test commit captured a staged `prompt/AUTOPILOT.md` change that belonged to the user. It was
  rebuilt without it. The user's file was recovered from the stash blob and verified by hash.
- Force push was denied by the permission classifier (R-002). Approved by the user; pushed with
  `--force-with-lease` to `be18a97`, then PR #1 merged. Merged as `2985206`, tag `v0.1.0`.
- Reviewer subagents (architecture-reviewer, test-reviewer) were not run. The change is small, and the
  review was done inline: reviewed the diff against the spec and the layer contracts.
### Review findings
- None blocking. Inline review: import-linter contracts hold; settings read only in infrastructure;
  `env.py` is the only place that reads `TE_DATABASE_URL`.
### Follow-ups
- Local Postgres password `te` is a throwaway compose default (documented in compose).
- Real CI run for AC-5 pending the push.

## S02 — Job state machine   (2026-11-25 → 2026-11-25)
Branch: feat/S02-job-state-machine   Merged: 714136b (PR #5)   Tag: —
### What was built
- `domain/jobs.py`: `JobState` (with `is_terminal`), `JobStage`, `JobEvent`, `ErrorCode`, `Warning`,
  `Transition`, `transition()`, `backoff()`, `processing_timeout()`, `chunk_failed_warning()`.
- Pure stdlib, no I/O. `InvalidTransitionError` reuses `domain/errors.py`.
- Tests: `tests/unit/domain/test_jobs.py` (table, forbidden pairs, terminal absorb, attempts, timeout,
  backoff, stage order, warnings, happy path) and `test_jobs_properties.py` (Hypothesis: AC-5, AC-7).
### How it works
`transition(state, event, attempt_count, max_attempts, error_code)` first rejects any terminal state,
then handles `CANCEL_REQUESTED` (any non-terminal → `CANCELLED`), then looks up the table. Transient
and lease failures retry while `attempt_count < max_attempts`, otherwise fail with `ATTEMPTS_EXHAUSTED`
or `POISON_JOB`. `backoff` = min(cap, base·2^(n−1)) scaled by a jitter factor in [1−j, 1+j], clamped to
[0, cap]. `processing_timeout` = duration × RTF_p95 × factor + overhead.
### Steps and commits
| # | Commit | What changed | Tests turned green |
|---|---|---|---|
| 1 | cce0e48 docs(S02): resolve open questions | Q1–Q4 answered, D-003..D-006 | — |
| 2 | 2ca7612 test(S02): add acceptance tests (xfail) | 30 strict xfail tests | — |
| 3 | 02892aa feat(S02): add JobState, JobEvent, JobStage, ErrorCode | enums | stage order |
| 4 | e7149e6 feat(S02): implement transition table | `transition()` | AC-1..4, AC-7, edge cases |
| 5 | e89b472 feat(S02): add backoff and processing timeout | `backoff`, `processing_timeout` | AC-5, AC-6 |
| 6 | 0b78a3b docs(adr): accept 0006 stage hand-off between queues | ADR + design.md | — |
| 7 | b264ac1 fix(S02): address review findings | Warning codes, rng injection, stronger AC-4/AC-5/AC-7 | — |
### Verification
- `make check`: 35 passed (ruff, format, mypy, lint-imports 4 KEPT).
- No xfail markers remain: `grep -rn 'reason="S02"' tests` is empty.
- `make itest`: not run; S02 touches no infrastructure.
### Decisions
D-003 (exhaustion at error), D-004 (backoff defaults, jitter RNG), D-005 (PROFILING, ADR-0006 accepted),
D-006 (`error_code` keyword on `transition`)
### Problems and fixes
- Strict xfail on the stage-order test: it passed as soon as the enums existed. Marker removed in the same
  commit, as the protocol says.
- A bulk xfail removal also stripped markers from tests still waiting on step 5. Restored before commit.
- Lint: lazy imports (PLC0415) replaced with `importlib.import_module`; `random` (S311) suppressed with
  D-004 reason on the module-level RNG only.
### Review findings
- architecture-reviewer: 6 findings. Fixed: missing `Warning` codes (in scope); error code assertions;
  AC-7 strengthened; injectable RNG; spec interface updated; stale docstring.
- test-reviewer: 6 findings. Fixed: AC-7 could pass with `transition` always raising; AC-4 branching and
  missing error codes; AC-5 bounds too weak; LEASE_EXPIRED `max_attempts=1` edge; explicit timeout
  parameters; warnings coverage.
- security-reviewer: not run; S02 has no uploads, FFmpeg, auth, SQL, storage or webhook surface.
### Follow-ups
- DB CHECK constraint for states (S05); leases, heartbeats, reconciler (S06).
- Warning codes are not yet persisted; S05/S10 decide the storage.

## S03 — Pipeline config, deterministic keys, time units   (2026-11-25 → 2026-11-25)
Branch: feat/S03-pipeline-config-and-keys   Merged: eb5dd15 (PR #7)   Tag: —
### What was built
- `domain/time.py`: `SAMPLE_RATE`, `samples_to_ms` (floor), `ms_to_samples`; integer only.
- `domain/config.py`: frozen `PipelineConfig` with flat, finite, read-only parameter mappings, an explicit
  language (never auto), `canonical_json()` (sorted keys, compact, UTF-8, NaN/Infinity rejected) and
  `config_hash()`.
- `domain/keys.py`: `result_key`, `chunk_id`, `rag_chunk_id`, `embedding_id` with the `res_`/`chk_`/`rag_`/`emb_`
  prefixes and encodings in D-007.
### How it works
Every key is a type prefix plus SHA-256 of a fixed byte layout. `result_key` hashes file hash, `‖`, canonical
config, and an optional `‖ isolation_scope`. Integer inputs pass through `operator.index`, so floats are rejected
rather than hashed as `16000.0`.
### Steps and commits
| # | Commit | What changed | Tests turned green |
|---|---|---|---|
| 1 | a28150c docs(S03): resolve open question and record key encodings | Q1 answered, D-007 | — |
| 2 | 8d1a672 test(S03): add acceptance tests (xfail) | 25 strict xfail tests with golden values | — |
| 3 | c3b6d5b feat(S03): add time units | `time.py` | AC-5 |
| 4 | 3f39a92 feat(S03): add PipelineConfig with canonical JSON | `config.py` | AC-2, AC-6 |
| 5 | 592d71e feat(S03): add deterministic keys | `keys.py` | AC-1, AC-3, AC-4 |
| 6 | c395a56 fix(S03): address review findings | immutability, integer inputs, key/language checks | — |
### Verification
- `make check`: 71 passed (ruff, format, mypy, lint-imports 4 KEPT).
- No xfail markers remain for S03 (`grep -rn 'reason="S03"' tests` empty).
### Decisions
D-007 (key and ID encodings, Q1 accepted)
### Problems and fixes
- Mypy: `dict` vs `Mapping` return type after making mappings read-only; return type changed to `Mapping`.
- Ruff TRY004 on the key/scalar checks: the spec requires `ValueError`, so the type test is bound to a
  boolean first instead of raising in an `isinstance` branch.
### Review findings
- architecture-reviewer: 6 findings. Fixed: mutable mapping stored in frozen dataclass (result key could change
  after construction); float inputs accepted by time and key functions; case-sensitive `auto` check; non-string
  keys; vad_params NaN coverage; no-op `sort_keys` on a list.
- test-reviewer: 6 findings. Fixed: AC-2 permuted only decoding_params; immutability tested only through the
  proxy and not the caller's dict; 0.0-vs-0 not checked at key level; chained `!=` assertion; allow_nan path.
  Not added: a direct test of `canonical_json` with a non-finite value injected past `__post_init__` (the
  constructor check covers the same invariant).
### Follow-ups
- Adapters must emit stable parameter types (documented edge case).
- S04 provides `domain.text.normalize()`; S03 does not touch text.

## S04 — Arabic text normalization   (2026-11-26 → 2026-11-26)
Branch: feat/S04-arabic-text-normalization   Merged: c909f6c (PR #9)   Tag: —
### What was built
- `domain/text.py`: `fold_char` (one-to-one rules), `normalize` (deletions, whitespace collapse, exact
  offset map), `map_span` (search span to raw span), `NormalizedText`.
- `tests/unit/domain/test_text.py`, `test_text_properties.py`, fixture `normalization_cases.tsv` (50 rows).
- `docs/adr/0008-arabic-normalizer-in-domain.md` (D-008).
### How it works
One pass over the raw text. Tatweel and diacritics are dropped; alef variants, alef maksura, teh marbuta and
Persian yeh fold to one character; Arabic-Indic and Eastern digits become ASCII; Latin letters lowercase
when the result is one character; each whitespace run becomes one space, with leading and trailing space
dropped. The offset of each kept character is stored. `map_span` maps a search span to the raw span and
extends it over deleted marks inside the word (D-012).
### Steps and commits
| # | Commit | What changed | Tests turned green |
|---|---|---|---|
| 1 | 46c54b4 docs(S04): resolve open questions and record decisions | Q1, Q2; D-008..D-010 | — |
| 2 | b6fc0c4 test(S04): add case table and property tests (xfail) | 49-row table, 57 strict xfail | — |
| 3 | 6d7b538 feat(S04): add character folding rules | `fold_char` | — |
| 4 | 8c5d5da fix(S04): correct alef-variant case row | fixture row (D-011) | — |
| 5 | bd99c19 feat(S04): add normalize with exact offset map | `normalize` | AC-1, AC-2, AC-3, AC-5, raw-unmodified |
| 6 | 680b384 feat(S04): add map_span | `map_span` | AC-4, span edge cases |
| 7 | b51c49e docs(adr): 0008 Arabic normalizer as domain character table | ADR-0008, design sentence | — |
| 8 | 646c856 fix(S04): address review findings | D-012, fixture escapes, stronger property tests | — |
### Verification
- `make check`: 138 passed (ruff, format, mypy, lint-imports 4 KEPT).
- No xfail markers remain for S04.
### Decisions
D-008 (domain character table, ADR-0008), D-009 (Persian yeh), D-010 (1:1 definitions), D-011 (fixture row
correction), D-012 (span includes word-boundary marks)
### Problems and fixes
- Fixture row `أإآٱ` expected a lam; corrected in its own commit (D-011).
- Hand-written fixture generation wrote raw tab characters into cells, so the tab-only rows tested the empty
  string. Found by the architecture review; the fixture is regenerated with escapes and explicit LF endings.
- Commit 5 and 6 were split after the fact: `map_span` was written before the normalize commit and was
  moved out so each commit stayed green.
- Hypothesis alphabets: a multi-character string in `sampled_from` is rejected; split into characters.
### Review findings
- architecture-reviewer: 5 findings. Fixed: span dropped word-final diacritics (D-012); tab-only rows checked
  the empty string; no word-final or combining-mark rows; `fold_char` exported only for tests (removed from
  `__all__`). Spec edge case about boundary deletions resolved by D-012.
- test-reviewer: 7 findings. Fixed: AC-3 used the implementation's own `fold_char` (now a literal rule
  table); AC-2 only checked idempotence (now also forbidden output characters); rule characters rarely
  generated (now mixed in); missing boundary and mixed-whitespace cases; duplicate fixture rows; combining
  mark row made explicit.
### Follow-ups
- CAMeL Tools morphology: a later Port (ADR-0008).
- Case table is hand-written; S16 will add a corpus-based check.

## S07 — Object storage and presigned uploads   (2026-11-26 → 2026-11-26)
Branch: feat/S07-object-storage   Merged: a29dd33 (PR #11)   Tag: —
### What was built
- `domain/storage_keys.py`: `incoming_key`, `work_key` (tenant is the second segment, D-014), plus
  `check_incoming_key` and `check_prefix` used by every adapter and the fake.
- `application/ports/storage.py`: `ObjectStorage` Protocol, `UploadTicket`, `ObjectInfo`.
- `infrastructure/storage/s3.py`: `S3ObjectStorage` over a boto3 client, calls in worker threads; presigned
  POST with `content-length-range`, exact key condition and SSE; SSE-S3 on every put; `delete_prefix` with
  pagination and batches of 1000; botocore and client errors translated to domain errors.
- `tests/fakes/storage.py`: in-memory fake with the same validation and error contract.
- `tests/contracts/test_storage_contract.py` (contract on fake and MinIO) and
  `tests/unit/domain/test_storage_keys.py`.
### How it works
A ticket is a presigned POST: S3 checks the signed policy on upload, so an oversized file, a different key or
an expired policy is refused before it lands. Keys are built from validated ids only. Reads use HTTP Range
headers; `delete_prefix` lists with pagination and deletes in batches, counting only what was removed.
### Steps and commits
| # | Commit | What changed | Tests turned green |
|---|---|---|---|
| 1 | fcb33c0 docs(S07): resolve open question and record upload policy | Q1; D-013; design wording | — |
| 2 | 55be7ed test(S07): add storage contract tests (xfail) | keys (unit), contracts (MinIO) | — |
| 3 | 64401fe feat(S07): add storage keys and port with fake | keys, port, fake | AC-4 |
| 4 | 0bf500e feat(S07): add S3 adapter: put, head, stream, read_range | adapter core | AC-3, AC-5 |
| 5 | a8924b3 feat(S07): add presigned upload with size policy | presign | AC-1, AC-2 |
| 6 | 5458a30 feat(S07): add delete_prefix | delete | AC-6 |
| 7 | 07b3904 fix(S07): address review findings | D-015 validation, error contract, stronger contracts | — |
### Verification
- `make check`: 145 passed (ruff, format, mypy, lint-imports 4 KEPT).
- `make itest`: 9 passed against MinIO (5 contract tests on both backends plus the migration test).
- AC-1 proves the size gate with a control upload (204) and the refusal (400, EntityTooLarge).
- AC-2 proves expiry with a control upload (204), a sleep of two seconds and a refusal (403, expired).
### Decisions
D-013 (presigned POST), D-014 (tenant segment, MinIO-only policy tests), D-015 (upload limits and error contract)
### Problems and fixes
- MinIO needs a KMS key for SSE-S3; set in the test fixture (`MINIO_KMS_SECRET_KEY`).
- Strict xfail markers were removed one test at a time as the adapter gained each method (protocol).
- A `make check` failure was not caught on the first attempt because the commit line ran after it; the
  commit was redone once lint passed.
### Review findings
- architecture-reviewer: 3 findings (positive controls for AC-1/AC-2; error translation for connection
  errors; fake and adapter must raise the same errors). Fixed the first and last; connection-error translation
  fixed in the shared `_call` helper.
- security-reviewer: 3 findings (prefix can match other tenants; key not bound to the incoming layout;
  read start negative). All fixed through domain validators (D-015).
- test-reviewer: 6 findings (AC-1/AC-2 status-only checks; SSE on the iterator path; fake divergence on
  missing keys and EOF; no test beyond one batch; unclear variable name). Fixed except the rename, which is
  cosmetic and left as is.
### Follow-ups
- `put` with an async iterator buffers the whole object in memory. Multipart upload is needed before large
  generated objects (S10). Recorded as a known limitation.
- AC-2 uses a real two-second sleep, because MinIO judges the policy against its own clock.
- The 2 GiB upload cap is provisional (D-015); revisit with S09 ingest limits.
- `upload_id` is the last key segment; S08 should pass the server-generated id through explicitly.

## S05 — Schema, repositories, unit of work   (2026-11-26 → 2026-11-26)
Branch: feat/S05-persistence   Merged: 2af874b (PR #13)   Tag: —
### What was built
- `domain/jobs.py`: `Job`, `Media` (tenant-scoped), `Result` dataclasses; `domain/config.py` equality by canonical JSON.
- `application/ports/repositories.py`: JobRepository, MediaRepository, ResultRepository, UnitOfWork protocols.
- `infrastructure/db/`: Core table definitions (models.py, mirrors migration exactly and feeds Alembic),
  SQL repositories with ON CONFLICT and compare-and-set, SqlUnitOfWork (translates database errors), make_engine.
- `migrations/versions/0002_core_tables.py`: media, jobs, results, transcript_versions, segments, chunks, outbox.
- `tests/fakes/repositories.py` and `tests/contracts/test_repositories_contract.py` (15 tests, fake and Postgres).
### How it works
A unit of work owns one connection and one transaction. Media dedupe is per tenant. A result is claimed with a
single INSERT ... ON CONFLICT DO NOTHING RETURNING, so 20 concurrent claims give one row and one creator. Job state
changes are a single UPDATE with WHERE state = expected, so a stale call changes nothing. The config is stored as
canonical text, so the round trip is byte-exact.
### Steps and commits
| # | Commit | What changed | Tests turned green |
|---|---|---|---|
| 1 | d541541 docs(S05): resolve open question and record persistence decisions | Q1; D-016, D-017 | — |
| 2 | 10017e5 test(S05): add repository contract tests (xfail) | contract tests | — |
| 3 | 37bb8d9 feat(S05): add Job, Media, Result domain models | models | — |
| 4 | caeb883 feat(S05): add repository ports and fakes | ports, fakes | fake side |
| 5 | 8202cd6 build(S05): add core tables migration | migration 0002 (D-018) | state CHECK, migration round trip |
| 6 | 26052c6 feat(S05): add SQLAlchemy repositories and unit of work | SQL repositories, uow | Postgres side |
| 7 | 4999a6e fix(S05): address review findings | D-019 | — |
### Verification
- `make check`: 145 passed.
- `make itest`: 24 passed (repository contracts on both backends, storage contracts, migration round trip).
- Migration round trip passes at head 0002_core_tables.
### Decisions
D-016 (model shapes, round trip), D-017 (apply keyed by job id: accepted exception), D-018 (migration, durations in ms,
HEAD moved to 0002), D-019 (review decisions: per-tenant media, deterministic result ids, canonical config text,
ref_count CHECK, error translation, attempt_count in apply, shared results accepted with an S08 requirement).
### Problems and fixes
- The first Postgres run failed on the state CHECK test because the test read every CHECK on jobs. It now reads
  only ck_jobs_state.
- Media helper gave every media the same hash, so the second media row silently resolved to the first and the job
  foreign key failed. Helper now hashes a distinct seed.
- With result ids equal to result keys, a losing concurrent claim hit the primary key, which an ON CONFLICT target
  on result_key does not cover. Fixed with an unqualified ON CONFLICT DO NOTHING.
- The first concurrency test was not gated; all claimants now wait on one event before starting.
- Commit 6 was followed by a pre-commit formatter failure that rolled back the commit. Fixed by formatting first.
- S07 correction: the storage expiry test (AC-2) used a one-second policy that had already expired when its control
  upload was sent. It now uses three seconds and sleeps until just past expires_at. The change landed in the S05
  branch; it is recorded here because the S07 entry was already merged.
### Review findings
- architecture-reviewer: 11 findings. Fixed: fake/pg mismatch on incr_ref and duplicate add; apply could not persist
  attempt_count; SQL errors not translated; uow built its own engine (now takes an AsyncEngine); result ids random
  (now deterministic); Alembic target_metadata unset (now set); models missing columns (now mirror all tables);
  D-017 exception not in BUILD_LOG (this entry). Float round trip through JSONB (now canonical text column).
- security-reviewer: 5 findings. Fixed: media dedupe leaked across tenants (per-tenant media); ref_count could go
  negative (CHECK and guarded update); SQL errors leaked (translated). Accepted with a requirement: shared results
  across tenants (S08 must not return created, result_id or ref_count to clients); apply keyed by job id (D-017).
- test-reviewer: 8 findings. Fixed: AC-3 stale call used the same transition; AC-5 fixture had no rich fields;
  AC-2 did not count rows; AC-1 could match another constraint; interface gaps (get_by_key, incr_ref, dedupe,
  duplicate add) now tested on both backends; random result ids; concurrency without a start gate.
- Note: the three reviewers were not re-run on the fixed head 4999a6e. Their findings were checked against the code
  and each was fixed or recorded in D-019.
### Follow-ups
- S06 needs lease, claim and fencing queries on jobs (lease columns exist, unused).
- S08: the API must not expose result created flag, result_id or ref_count; tenant scoping of results is by design
  shared internally, enforced at the API layer.
- Fake get returns the stored object, so the AC-5 pass on the fake is an identity check. Accepted; the Postgres side
  is the real proof.
- result_key UNIQUE and ref counting: deletion of unreferenced results belongs to S21.

## S06 — Postgres job queue, lease, fencing, reconciler   (2026-11-26 → 2026-11-26)
Branch: feat/S06-postgres-job-queue   Merged: f216ccd (PR #15)   Tag: —
### What was built
- `application/ports/{queue,clock}.py`: JobQueue, Reconciler, Clock, Lease, ReconcileReport.
- `application/worker_loop.py`: claim, heartbeat in its own task, run the handler, complete only while the lease is held.
- `infrastructure/db/queue.py`: one-statement claim (FOR UPDATE SKIP LOCKED, priority then seq), heartbeat, fenced complete, cancellation check.
- `infrastructure/db/reconciler.py`: one transaction expires dead leases through the domain rules and requeues due retries.
- `migrations/versions/0003_queue_columns.py`: started_at, FIFO seq, claim index (D-021).
- `tests/fakes/queue.py`, `tests/fakes/clock.py`; contract tests on fake and Postgres; chaos test; worker unit tests.
### How it works
A claim picks the highest-priority, oldest claimable row and sets the lease in the same statement, using the database
clock. Every heartbeat and complete is fenced by owner, attempt and liveness. The reconciler moves an expired lease
through transition(LEASE_EXPIRED): retry with backoff while attempts remain, otherwise POISON_JOB.
### Steps and commits
| # | Commit | What changed | Tests turned green |
|---|---|---|---|
| 1 | 3961f9a docs(S06): resolve open question and record queue decisions | Q1; D-020, D-021 | — |
| 2 | 97f7229 test(S06): add queue contract and chaos tests (xfail) | contracts, chaos | — |
| 3 | daf2191 feat(S06): add queue and clock ports with fakes | ports, fakes, domain errors | fake side |
| 4 | 8d4f5c9 feat(S06): claim with FOR UPDATE SKIP LOCKED | claim, migration 0003 | priority, concurrent claims |
| 5 | 217de1c feat(S06): add heartbeat and fenced complete | heartbeat, complete, cancellation | cancellation |
| 6 | 90f712b feat(S06): add reconciler | reconciler | expiry, poison, retry |
| 7 | 0d53825 feat(S06): add worker loop with cancellation | worker loop, chaos xfail removed | chaos |
| 8 | e10ecbd fix(S06): address review findings | D-022 | — |
### Verification
- `make check`: 150 passed.
- `make itest`: 40 passed (queue contracts on both backends, chaos run, storage, repositories, migration round trip).
- Chaos run: 1,000 jobs, 20% of first attempts abandoned, 8 workers, fixed seed. All jobs reach a terminal state, no job
  completes twice, and every abandoned owner's late complete is refused.
### Decisions
D-020 (database time for lease comparisons; fairness out of scope), D-021 (migration 0003, queue fields on Job),
D-022 (review decisions and accepted residual risks).
### Problems and fixes
- Shared pg fixture imported across test modules produced duplicate-import errors; moved to tests/conftest.py.
- The claim tests ran before reconciler existed; the reconciler import was made lazy in the test helper.
- The reconciler's first version poisoned on the wrong state (PROCESSING only); pending leases were released without
  limit until review found it.
- A duplicated return line in claim was caught by mypy (unreachable statement).
### Review findings
- security-reviewer: 5 findings. Fixed: complete now requires a live lease; claim respects the attempt limit. Accepted:
  queue is worker-internal (no tenant parameter, D-022); the from-state of a Transition is not checked in SQL (residual,
  recorded). A stale write is not logged yet (S20).
- architecture-reviewer: 12 findings. Fixed: claim translates database errors; pending expiry poisons at the limit;
  transient heartbeat errors retried; Reconciler.run_once docstring corrected (D-022). Accepted: direct PROCESSING in
  claim SQL (the CLAIMED edge); float lease seconds; asyncio.sleep injectable; handler checkpoint via heartbeat until S10.
- test-reviewer: 8 findings. Fixed: chaos run now sends stale completes and asserts abandonments happened; worker tests
  for transient, permanent and lost lease; heartbeat-after-reconciler and future-retry contracts. The chaos run keeps a
  real 1-second lease (the documented exception).
- Note: reviewers ran on the pre-fix head; findings were checked and fixed, not re-reviewed.
### Follow-ups
- Pass the from-state into complete (D-022 residual).
- Log stale writes (S20). Between-stage cancellation checkpoint (S10).

## S08 — API, auth, job endpoints   (2026-11-26 → 2026-11-26)
Branch: feat/S08-api-auth-jobs   Merged: f9eeca3 (PR #17)   Tag: —
### What was built
- Endpoints: `POST /v1/uploads`, `POST /v1/transcriptions` (Idempotency-Key), `GET /v1/transcriptions/{id}`,
  `POST /v1/transcriptions/{id}:cancel`, `DELETE /v1/transcriptions/{id}` (202, marks only),
  `GET /v1/transcriptions/{id}/result?format=json` (409 until completed, 404 after: no body until S10).
- Application: create upload ticket, create job, get job, get result, cancel, request deletion, authenticate API key.
- Infrastructure: API key, tenant limit and idempotency repositories; SystemClock; migration 0004 (tenants, api_keys,
  idempotency_keys with request_hash, jobs.deletion_requested_at, RLS on jobs).
- Presentation: FastAPI app factory, bearer and scope dependencies, problem+json for application and validation errors.
- `make seed` (local tenant and key, printed once, saved to git-ignored `.env.local`); `make openapi` and the drift test.
### How it works
A bearer key is hashed and looked up in the system scope; the key's tenant then scopes every query. Each unit of work
sets `app.tenant_id` (or `app.system` for workers) for its transaction; RLS hides other tenants' jobs even from raw SQL
run as the API role. Job creation locks the tenant row, checks idempotency and limits, then writes media, job and
idempotency record together and returns 202 with Location.
### Steps and commits
| # | Commit | What changed | Tests turned green |
|---|---|---|---|
| 1 | bc268bc docs(S08): resolve open question and record API decisions | Q1; D-023..D-025 | — |
| 2 | 7d8aba0 test(S08): add API and use-case tests (xfail) | integration, unit | — |
| 3 | 04381a3 build(S08): add tenants, api_keys, idempotency tables and RLS | migration 0004, system scope in queue | queue and repository suites still green |
| 4 | 529bb4d feat(S08): add API key auth, scopes and problem+json errors | auth, errors, make seed | — |
| 5 | b3cc416 feat(S08): add upload ticket endpoint | upload route | auth tests |
| 6 | 4783d84 feat(S08): add create job with idempotency key and concurrency limit | create route, non-superuser API database | create, idempotency, limit, RLS |
| 7 | 2199357 feat(S08): add get, cancel, delete request and result endpoints | job routes | read, cancel, delete, other-tenant |
| 8 | 910cbee docs(S08): generate OpenAPI snapshot | docs/openapi.json, drift test | — |
| 9 | 150ac9b fix(S08): address review findings | D-027 | hardening suite (7) |
### Verification
- `make check`: 158 passed. `make itest`: 57 passed (API, RLS, idempotency, queue, chaos, storage, repositories, migrations).
- No S08 xfail markers remain.
### Decisions
D-023 (upload placeholder media), D-024 (RLS policy, system scope, role split), D-025 (quota, concurrency, idempotency,
webhooks refused, progress), D-026 (key format, hashing, problem+json), D-027 (review decisions and residuals).
### Problems and fixes
- Superusers bypass RLS, so the API tests run as a non-superuser role on their own database.
- Queue tests shared a database with API jobs, which made the queue see extra work; the API suite now has its own database.
- Cancel re-read the job after commit and got 404 because row-level security had lost the tenant setting. Found by the
  new cancel test; fixed by building the answer before commit.
- The first other-tenant test passed for the wrong reason: routes did not exist yet, so 404 matched. A positive control
  was added.
- Duplicate-key race and idempotency reuse were found by review; fixed with a tenant row lock and a request hash.
### Review findings
- security-reviewer: 9 findings. Fixed: idempotency race; body binding; expired key reuse; fail-open scope; deletion marker
  skipped by workers; upload id validation; system lookup narrowed to the auth use case. Residual: results not
  tenant-scoped (S10 requirement), apply keyed by job id (D-017), quota inert until S09.
- architecture-reviewer: 10 findings. Fixed: clock port used; auth moved to the application layer; problem+json for
  validation; dead result branch removed; idempotency race and expired keys. Residual: none blocking.
- test-reviewer: 12 findings. Fixed: positive controls; concurrent-limit race; cancel success; body binding; quota;
  cross-tenant RLS; Retry-After integer and absent when terminal. Residual: AC-4 checks job count by id, not per tenant.
- Note: reviewers ran on the pre-fix head. Findings were checked and fixed; they were not re-reviewed.
### Follow-ups
- S09 sets real media durations, so quota starts to count. S10 adds tenant scoping to results before writing bodies.
- Production must use a NOBYPASSRLS role (D-024). S20 adds webhooks; S21 performs deletion.
