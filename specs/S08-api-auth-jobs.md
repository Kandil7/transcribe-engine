# S08 — API, auth, job endpoints

| | |
|---|---|
| Phase | 2 |
| Depends on | S05, S06, S07 |
| Branch | `feat/S08-api-auth-jobs` |
| Design sections | تدفق البيانات › دورة الطلب، مفتاح الـ Idempotency (Idempotency-Key)، نقاط النهاية؛ الأمان › الهوية والصلاحيات |
| ADRs | — |

## Goal
A tenant with an API key can request an upload ticket, create a transcription job, read its status,
cancel it, and request deletion, and can never see another tenant's jobs.

## Scope
- In: `POST /v1/uploads`, `POST /v1/transcriptions`, `GET /v1/transcriptions/{id}`,
  `POST /v1/transcriptions/{id}:cancel`, `DELETE /v1/transcriptions/{id}` (marks for deletion, returns 202),
  `GET /v1/transcriptions/{id}/result?format=json`; API keys; scopes; RLS; `Idempotency-Key`;
  concurrent-job limit.
- Out (→ S15): other formats. (→ S20): webhooks. (→ S21): actual data deletion. (→ S18): `/v1/search`.

## Interfaces
```python
class CreateTranscriptionJob:   # use case
    async def __call__(self, cmd: CreateJobCommand) -> CreateJobResult: ...
@dataclass(frozen=True)
class CreateJobCommand:
    tenant_id: str; upload_id: str; language: str; engine: str | None
    diarization: bool; webhook_url: str | None; idempotency_key: str | None
class ApiKeyRepository(Protocol):
    async def find_by_hash(self, key_hash: str) -> ApiPrincipal | None: ...
```

## Files
- `src/transcribe_engine/application/use_cases/{create_upload,create_job,get_job,cancel_job,request_deletion}.py`
- `src/transcribe_engine/presentation/api/{app,deps,errors,routes_uploads,routes_transcriptions,schemas}.py`
- `src/transcribe_engine/infrastructure/db/api_keys.py`; `migrations/versions/0003_tenants_keys_rls.py`
- `tests/unit/application/test_*.py`, `tests/integration/test_api_*.py`

## Rules
- Request cycle steps 1–5 `[D: دورة الطلب]`: job created as `PENDING_VALIDATION` on queue `cpu` in one
  transaction; response `202 Accepted` + `Location: /v1/transcriptions/{id}`.
- API keys stored as SHA-256 hash, scopes `transcribe:write`, `transcribe:read` `[D: الهوية والصلاحيات]`.
- Every repository call takes `tenant_id`; Postgres RLS on `jobs` as a second layer `[D: الهوية والصلاحيات]`.
- Another tenant's job id → 404 (not 403), so ids leak nothing `[D: نقاط النهاية]`.
- `Idempotency-Key`: unique on `(tenant_id, idempotency_key)` for 24 h; a repeat returns the original
  response `[D: مفتاح الـ Idempotency]`.
- GET returns `state`, `stage`, `progress`, `warnings`, `error_code`, plus `Retry-After` while non-terminal `[D: نقاط النهاية]`.
- Cancel on a terminal job → 409. DELETE → 202 and sets `deletion_requested_at`.
- Concurrent active jobs per tenant above limit → 429 `[D: الهوية والصلاحيات]`.
- Errors as RFC 9457 problem+json. No transcript text or filenames in logs.

## Acceptance criteria
- **AC-1** `[D: دورة الطلب]` — `test_api_transcriptions.py::test_create_returns_202_and_location` (integration).
- **AC-2** `[D: الهوية والصلاحيات]` — `::test_other_tenant_gets_404` for GET, cancel, delete, result (integration).
- **AC-3** `[D: الهوية والصلاحيات]` — `test_api_rls.py::test_rls_blocks_raw_query_without_tenant` (integration).
- **AC-4** `[D: مفتاح الـ Idempotency]` — `::test_idempotency_key_replays_response` (integration): 2 calls → 1 job.
- **AC-5** — `::test_missing_or_bad_key_401`, `::test_wrong_scope_403` (integration).
- **AC-6** `[D: نقاط النهاية]` — `::test_get_non_terminal_has_retry_after` (integration).
- **AC-7** — `::test_cancel_terminal_409` (integration).
- **AC-8** `[D: الهوية والصلاحيات]` — `::test_concurrency_limit_429` (integration).
- **AC-9** — `test_create_job.py::*` (unit, fakes): upload missing, upload of other tenant, language not
  supported → domain errors mapped to 404/404/422.

## Commit plan
1. `docs(S08): add spec`
2. `test(S08): add API and use-case tests (xfail)`
3. `build(S08): add tenants, api_keys, idempotency tables and RLS`
4. `feat(S08): add API key auth and scopes`
5. `feat(S08): add upload ticket endpoint`
6. `feat(S08): add create job with idempotency key and concurrency limit`
7. `feat(S08): add get, cancel, delete-request, result(json) endpoints`
8. `docs(S08): generate OpenAPI snapshot` (`docs/openapi.json`, checked in CI for drift)

## Open questions
- [ ] Q1 — Monthly audio-hours quota is in the design ("Quotas لكل Tenant") without numbers. Proposed:
  field on `tenants`, enforced at create time, default unlimited until pricing exists.
