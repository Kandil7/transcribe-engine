# S21 — Privacy, retention, deletion

| | |
|---|---|
| Phase | 5 |
| Depends on | S08, S18 |
| Branch | `feat/S21-privacy-retention-deletion` |
| Design sections | الأمان والخصوصية › الخصوصية ودورة حياة البيانات؛ نقاط النهاية (DELETE) |
| ADRs | — |

## Goal
Data lives only as long as allowed, deletion really removes everything a tenant owns for a job, and
shared cache results disappear only when no one owns them.

## Rules `[D: الخصوصية ودورة حياة البيانات]`
- S3 server-side encryption and TLS between services.
- Audio retention 30 days by default, per-tenant setting, via lifecycle rules and a daily sweeper.
- `DELETE /v1/transcriptions/{id}` removes: original audio, normalized audio, stage intermediates,
  transcript versions, segments, RAG chunks and embeddings, artifacts; keeps a content-free audit row.
- Shared results use `ref_count`; physical deletion only at 0.
- No transcript text in logs (S20 AC-5 covers logging).
- Evaluation and training data only from our own or explicitly consented audio; a `training_consent`
  flag on tenant/job gates S22 exports.

## Interfaces
```python
class DeleteJobData:   # use case
    async def __call__(self, tenant_id: str, job_id: str) -> DeletionReport: ...
class RetentionSweeper:
    async def run_once(self, now: datetime) -> SweepReport: ...
@dataclass(frozen=True)
class DeletionReport:
    objects_deleted: int; rows_deleted: Mapping[str, int]; result_released: bool
```

## Files
- `src/transcribe_engine/application/use_cases/{delete_job_data,retention_sweeper}.py`
- `src/transcribe_engine/infrastructure/db/audit.py`; migration for `audit_log`, `training_consent`
- `tests/integration/test_deletion.py`

## Acceptance criteria
- **AC-1** — `test_deletion.py::test_delete_removes_everything` (integration): after DELETE, no object
  under the job prefix, no rows in any table for the job, no search hit.
- **AC-2** — `::test_shared_result_kept_until_last_owner` (integration): two tenants, same file.
- **AC-3** — `::test_audit_row_has_no_content` (integration).
- **AC-4** — `test_retention_sweeper.py::test_expired_audio_removed_per_tenant_setting` (unit, fake clock).
- **AC-5** — `test_deletion.py::test_delete_is_idempotent` (integration).
- **AC-6** — `test_storage_contract.py::test_put_sets_sse` (from S07) still green.

## Commit plan
1. `docs(S21): add spec`
2. `test(S21): add deletion and retention tests (xfail)`
3. `build(S21): add audit log and consent columns`
4. `feat(S21): add DeleteJobData across storage, DB and index`
5. `feat(S21): add retention sweeper and lifecycle config`

## Open questions
- [ ] Q1 — Egypt's Personal Data Protection Law (No. 151 of 2020) and data residency (where GPUs run):
  needs legal review before production; may add region pinning per tenant.
