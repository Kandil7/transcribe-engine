# S06 — Postgres job queue, lease, fencing, reconciler

| | |
|---|---|
| Phase | 2 |
| Depends on | S05 |
| Branch | `feat/S06-postgres-job-queue` |
| Design sections | تدفق البيانات › لماذا Postgres كطابور؛ آلة الحالات › آليات الاعتمادية؛ البيانات والتشغيل › تشغيل الـ GPU Worker |
| ADRs | 0002, 0006 |

## Goal
Workers claim jobs from Postgres without a broker, hold a lease with heartbeats, write results only
while they own the lease, and a reconciler recovers dead workers. No job is lost or processed twice.

## Interfaces
```python
@dataclass(frozen=True)
class Lease:
    job_id: str; owner: str; attempt: int; until: datetime

class JobQueue(Protocol):
    async def claim(self, queue: str, owner: str, lease_for: timedelta) -> tuple[Job, Lease] | None: ...
    async def heartbeat(self, lease: Lease, extend_by: timedelta) -> Lease:
        """Raises LeaseLostError if owner/attempt no longer match."""
    async def complete(self, lease: Lease, t: Transition, *, stage: JobStage | None = None) -> bool:
        """Fenced: WHERE id AND lease_owner AND attempt_count = lease.attempt."""
    async def is_cancelled(self, job_id: str) -> bool: ...

class Reconciler(Protocol):
    async def run_once(self, now: datetime) -> ReconcileReport: ...   # expired leases + due retries

class Clock(Protocol):
    def now(self) -> datetime: ...
```

## Files
- `src/transcribe_engine/application/ports/{queue,clock}.py`
- `src/transcribe_engine/infrastructure/db/queue.py`, `.../reconciler.py`
- `src/transcribe_engine/application/worker_loop.py` — claim → heartbeat task → handler → complete
- `tests/fakes/{queue,clock}.py`, `tests/contracts/test_queue_contract.py`,
  `tests/integration/test_queue_chaos.py`

## Rules
- Claim query as in the design: `FOR UPDATE SKIP LOCKED LIMIT 1`, order `priority DESC, created_at`,
  filter `queue`, `run_after <= now()`; sets `PROCESSING`, `lease_owner`, `lease_until`,
  `attempt_count + 1`, `started_at` `[D: لماذا Postgres كطابور]`.
- Claimable: `QUEUED` on any queue; `PENDING_VALIDATION` on queue `cpu` (state kept, lease set) `[ADR-0006]`.
- Lease 2 min; heartbeat every 30 s from a separate task, independent of the handler `[D: آليات الاعتمادية]`.
- Fencing on every result write `[D: آليات الاعتمادية]`.
- Reconciler: expired lease → `LEASE_EXPIRED` event (retry or POISON_JOB); `RETRY_SCHEDULED` with
  `run_after <= now` → `RETRY_DUE` `[D: آليات الاعتمادية]`.
- Handler sees cancellation between stages and on each heartbeat `[D: آليات الاعتمادية]`.
- Time only from `Clock`; tests never sleep.

## Edge cases
- Worker killed mid-job → reconciler moves it on; the old worker's late `complete` returns False.
- Heartbeat after the reconciler took the job → `LeaseLostError`, handler aborts.
- Clock skew: all lease comparisons use the DB's `now()` in SQL; `Clock` only in the Fake.

## Acceptance criteria
- **AC-1** `[D: لماذا Postgres كطابور]` — `test_queue_contract.py::test_concurrent_claims_unique`
  (contract, integration): 200 jobs, 16 concurrent claimers → each job claimed exactly once.
- **AC-2** `[D: آليات الاعتمادية]` — `::test_fenced_complete_rejects_stale_owner` (contract).
- **AC-3** `[D: آليات الاعتمادية]` — `::test_expired_lease_retried_then_poison` (contract): 3 expiries → FAILED(POISON_JOB).
- **AC-4** `[D: آليات الاعتمادية]` — `::test_retry_due_requeues` (contract) with fake clock.
- **AC-5** `[D: آليات الاعتمادية]` — `test_queue_chaos.py::test_kill_workers_no_loss_no_dup` (integration):
  1,000 short jobs, workers randomly cancelled → all jobs terminal, no job completed twice (seed fixed).
- **AC-6** `[D: آليات الاعتمادية]` — `::test_cancel_observed_on_heartbeat` (contract).
- **AC-7** — `::test_priority_then_fifo` (contract).

## Commit plan
1. `docs(S06): add spec`
2. `test(S06): add queue contract and chaos tests (xfail)`
3. `feat(S06): add queue and clock ports with fakes`
4. `feat(S06): claim with FOR UPDATE SKIP LOCKED`
5. `feat(S06): add heartbeat and fenced complete`
6. `feat(S06): add reconciler`
7. `feat(S06): add worker loop with cancellation`

## Open questions
- [ ] Q1 — Fair scheduling between tenants is not in the design doc. Proposed: out of scope; revisit
  when one tenant's batch delays others (metric in S20).
