"""Port for object storage (S07). Adapters live in infrastructure; boto3 is hidden behind this.

Every method is async. Adapters that call a sync client run it in a thread pool.
"""

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

__all__ = ["ObjectInfo", "ObjectStorage", "UploadTicket"]


@dataclass(frozen=True)
class UploadTicket:
    upload_id: str
    url: str
    fields: Mapping[str, str]  # signed policy fields; the client adds the file as the last field
    expires_at: datetime
    max_bytes: int


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    encryption: str | None  # e.g. "AES256" when server-side encryption is on


class ObjectStorage(Protocol):
    async def presign_upload(
        self, key: str, max_bytes: int, expires: timedelta
    ) -> UploadTicket: ...

    async def head(self, key: str) -> ObjectInfo | None: ...

    async def read_range(self, key: str, start: int, length: int) -> bytes: ...

    def stream(self, key: str, chunk_bytes: int = 8 * 2**20) -> AsyncIterator[bytes]: ...

    async def put(self, key: str, data: bytes | AsyncIterator[bytes]) -> None: ...

    async def delete_prefix(self, prefix: str) -> int: ...

    async def delete(self, key: str) -> bool:
        """Delete one object. True if it existed. Idempotent (S21)."""
        ...
