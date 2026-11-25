# S05 — Schema, repositories, unit of work

| | |
|---|---|
| Phase | 2 |
| Depends on | S02, S03 |
| Branch | `feat/S05-persistence` |
| Design sections | البيانات والتشغيل › الجداول الأساسية؛ آلة الحالات › الحالات؛ تدفق البيانات › مفتاح الـ Idempotency |
| ADRs | 0002 (Postgres as queue), 0006 |

## Goal
Core tables exist with constraints that mirror the domain rules, and repositories persist domain
objects through Ports, with contract tests against Fakes and real Postgres.

## Scope
- In: tables `media`, `jobs`, `results`, `transcript_versions`, `segments`, `chunks`, `outbox`;
  `JobRepository`, `MediaRepository`, `ResultRepository`, `UnitOfWork`; in-memory Fakes.
- Out (→ S06): claim/lease queries. (→ S08): `tenants`, `api_keys`, RLS policies.
  (→ S18): RAG tables. (→ S19): `artifacts`.

## Interfaces
```python
class JobRepository(Protocol):
    async def add(self, job: Job) -> None: ...
    async def get(self, tenant_id: str, job_id: str) -> Job | None: ...
    async def apply(self, job_id: str, t: Transition, *, expected: JobState,
                    stage: JobStage | None = None) -> bool:
        """Compare-and-set on state. False if the current state != expected."""
class MediaRepository(Protocol):
    async def upsert(self, media: Media) -> Media: ...      # unique by sha256
class ResultRepository(Protocol):
    async def claim_key(self, result_key: str, media_id: str, config: PipelineConfig) -> tuple[Result, bool]:
        """INSERT ... ON CONFLICT DO NOTHING RETURNING; bool = created by this call."""
    async def get_by_key(self, result_key: str) -> Result | None: ...
    async def incr_ref(self, result_id: str, delta: int) -> int: ...
class UnitOfWork(Protocol):
    jobs: JobRepository; media: MediaRepository; results: ResultRepository
    async def __aenter__(self) -> Self: ...
    async def commit(self) -> None: ...
```

## Files
- `src/transcribe_engine/domain/jobs.py` (+ `Job`, `Media`, `Result` dataclasses)
- `src/transcribe_engine/application/ports/repositories.py`
- `src/transcribe_engine/infrastructure/db/{models,session,repositories,uow}.py`
- `migrations/versions/0002_core_tables.py`
- `tests/fakes/repositories.py`, `tests/contracts/test_repositories_contract.py`

## Rules
- Columns per "الجداول الأساسية" `[D]`; `jobs.pipeline_config` JSONB; words as JSONB inside `segments` `[D]`.
- `CHECK (state IN (...))` equals `JobState` values; a test compares them `[D: الحالات]`.
- `results.result_key` UNIQUE; created with `INSERT ... ON CONFLICT DO NOTHING RETURNING` `[D: مفتاح الـ Idempotency]`.
- Every query on `jobs` takes `tenant_id` `[D: الهوية والصلاحيات]`.
- State changes are compare-and-set (`WHERE id=:id AND state=:expected`) using `domain.transition()`.
- `chunks`: `chunk_id` PK, `job_id`, `idx`, `total`, `start_sample`, `end_sample`, `pad_before`,
  `pad_after`, `state`, `attempt_count`, `result_key_s3`; UNIQUE(`job_id`,`idx`) `[D: التقسيم]`.

## Edge cases
- Two concurrent `claim_key` calls with the same key: exactly one returns `created=True`.
- `apply` with stale `expected` returns False and changes nothing.

## Acceptance criteria
- **AC-1** `[D: الحالات]` — `test_repositories_contract.py::test_state_check_matches_domain` (integration).
- **AC-2** `[D: مفتاح الـ Idempotency]` — `::test_claim_key_concurrent` (contract, integration):
  20 concurrent calls → one creator, 19 readers, one row.
- **AC-3** — `::test_apply_compare_and_set` (contract): stale expected → False, row unchanged.
- **AC-4** `[D: الهوية والصلاحيات]` — `::test_get_other_tenant_returns_none` (contract).
- **AC-5** — `::test_job_round_trip` (contract): all fields survive save/load, config JSON byte-equal.
- **AC-6** — `tests/integration/test_migrations.py::test_round_trip` still passes with 0002.

## Commit plan
1. `docs(S05): add spec`
2. `test(S05): add repository contract tests (xfail)`
3. `feat(S05): add Job, Media, Result domain models`
4. `feat(S05): add repository ports and fakes` (contract tests pass for fakes)
5. `build(S05): add core tables migration`
6. `feat(S05): add SQLAlchemy repositories and unit of work` (contract tests pass for Postgres)

## Open questions
- [x] Q1 — `segments` stored per `transcript_version` (design) or as one JSONB document per version?
  Proposed: rows per segment (needed for pagination and search), words JSONB per segment.
  **Resolved (autopilot, 2026-11-26, D-016):** accepted as proposed; it matches the design table.
