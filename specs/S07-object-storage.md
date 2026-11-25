# S07 — Object storage and presigned uploads

| | |
|---|---|
| Phase | 2 |
| Depends on | S01 |
| Branch | `feat/S07-object-storage` |
| Design sections | تدفق البيانات › دورة الطلب (1–2)؛ الأمان › فحص الملفات وعزل FFmpeg، الخصوصية؛ التقسيم (Range GET) |
| ADRs | — |

## Goal
Clients upload straight to S3/MinIO with a short-lived, size-limited, tenant-scoped URL; workers read
whole objects or byte ranges through one Port.

## Interfaces
```python
@dataclass(frozen=True)
class UploadTicket:
    upload_id: str; url: str; fields: Mapping[str, str]; expires_at: datetime; max_bytes: int

class ObjectStorage(Protocol):
    async def presign_upload(self, key: str, max_bytes: int, expires: timedelta) -> UploadTicket: ...
    async def head(self, key: str) -> ObjectInfo | None: ...
    async def read_range(self, key: str, start: int, length: int) -> bytes: ...
    def stream(self, key: str, chunk_bytes: int = 8 * 2**20) -> AsyncIterator[bytes]: ...
    async def put(self, key: str, data: bytes | AsyncIterator[bytes]) -> None: ...
    async def delete_prefix(self, prefix: str) -> int: ...

def incoming_key(tenant_id: str, upload_id: str) -> str   # incoming/{tenant}/{upload_id}
def work_key(tenant_id: str, job_id: str, name: str) -> str
```

## Files
- `src/transcribe_engine/application/ports/storage.py`, `src/transcribe_engine/domain/storage_keys.py`
- `src/transcribe_engine/infrastructure/storage/s3.py`
- `tests/fakes/storage.py`, `tests/contracts/test_storage_contract.py`

## Rules
- Presigned URL valid 15 min, size limit in the signed policy `[D: دورة الطلب]`.
- Keys always start with the tenant id; ids are server-generated, never from client input `[D: الهوية والصلاحيات]`.
- Server-side encryption on every put `[D: الخصوصية]`.
- Range reads for chunk audio (`offset = header + start_sample × 2`) `[D: التقسيم]`.
- boto3 is sync: run it in a thread pool inside the adapter; the Port stays async.

## Acceptance criteria
- **AC-1** `[D: دورة الطلب]` — `test_storage_contract.py::test_upload_over_limit_rejected` (integration, MinIO).
- **AC-2** `[D: دورة الطلب]` — `::test_ticket_expires` (integration): URL rejected after expiry (short expiry in test).
- **AC-3** `[D: التقسيم]` — `::test_read_range_exact_bytes` (contract).
- **AC-4** `[D: الهوية والصلاحيات]` — `test_storage_keys.py::test_keys_prefixed_by_tenant` (unit, Hypothesis on ids).
- **AC-5** `[D: الخصوصية]` — `::test_put_sets_sse` (integration): `head` shows encryption.
- **AC-6** — `::test_delete_prefix_counts` (contract).

## Commit plan
1. `docs(S07): add spec`
2. `test(S07): add storage contract tests (xfail)`
3. `feat(S07): add storage keys and port with fake`
4. `feat(S07): add S3 adapter: put, head, stream, read_range`
5. `feat(S07): add presigned upload with size policy`
6. `feat(S07): add delete_prefix`

## Open questions
- [x] Q1 — The design says "Presigned PUT URL … مع حد الحجم في التوقيع". S3 enforces a size range on
  presigned **POST** policies (`content-length-range`), not on plain PUT. Proposed: presigned POST,
  plus a `head()` size check at ingest (S09) as the second gate; update the design wording.
  **Resolved (autopilot, 2026-11-26, D-013):** accepted. The ticket is a presigned POST with a
  `content-length-range` condition and a `key` condition; `max_bytes` is enforced by S3.
