"""In-memory ObjectStorage for unit tests and the shared contract tests (S07).

The fake does not enforce upload policies or encryption; those are proven against MinIO (D-014).
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from transcribe_engine.application.ports.storage import ObjectInfo, UploadTicket
from transcribe_engine.domain.errors import PermanentError
from transcribe_engine.domain.storage_keys import check_incoming_key, check_prefix


@dataclass
class FakeObjectStorage:
    objects: dict[str, bytes] | None = None

    def __post_init__(self) -> None:
        if self.objects is None:
            self.objects = {}

    def _object(self, key: str) -> bytes:
        data = self._store().get(key)
        if data is None:  # S3 answers 404 NoSuchKey: a permanent error for the caller
            raise PermanentError("object store rejected request: NoSuchKey")
        return data

    def _store(self) -> dict[str, bytes]:
        assert self.objects is not None
        return self.objects

    async def presign_upload(self, key: str, max_bytes: int, expires: timedelta) -> UploadTicket:
        check_incoming_key(key)
        if not 1 <= max_bytes <= 2 * 2**30 or not timedelta(0) < expires <= timedelta(minutes=15):
            raise ValueError("upload limits out of range")
        return UploadTicket(
            upload_id=key.rsplit("/", 1)[-1],
            url=f"fake://upload/{key}",
            fields={"key": key},
            expires_at=datetime.now(UTC) + expires,
            max_bytes=max_bytes,
        )

    async def head(self, key: str) -> ObjectInfo | None:
        data = self._store().get(key)
        if data is None:
            return None
        return ObjectInfo(key=key, size=len(data), encryption=None)

    async def read_range(self, key: str, start: int, length: int) -> bytes:
        if start < 0:
            raise ValueError("start must be >= 0")
        data = self._object(key)
        if length > 0 and start >= len(data):  # S3 answers 416 InvalidRange here (D-015 contract)
            raise PermanentError("object store rejected request: InvalidRange")
        return data[start : start + length]

    async def stream(self, key: str, chunk_bytes: int = 8 * 2**20) -> AsyncIterator[bytes]:
        data = self._object(key)
        for offset in range(0, len(data), chunk_bytes):
            yield data[offset : offset + chunk_bytes]

    async def put(self, key: str, data: bytes | AsyncIterator[bytes]) -> None:
        if isinstance(data, bytes):
            self._store()[key] = data
            return
        chunks = [chunk async for chunk in data]
        self._store()[key] = b"".join(chunks)

    async def delete_prefix(self, prefix: str) -> int:
        check_prefix(prefix)
        doomed = [k for k in self._store() if k.startswith(prefix)]
        for key in doomed:
            del self._store()[key]
        return len(doomed)
