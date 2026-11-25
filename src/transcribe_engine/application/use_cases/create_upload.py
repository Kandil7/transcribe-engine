"""Create an upload ticket (S08). The upload id is server-generated; the key is tenant-scoped."""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.domain.storage_keys import incoming_key

__all__ = ["UPLOAD_MAX_BYTES", "UPLOAD_TTL", "CreateUploadTicket", "UploadTicketResult"]

UPLOAD_MAX_BYTES = 2 * 2**30  # D-015: provisional cap, matches the storage adapter
UPLOAD_TTL = timedelta(minutes=15)  # S07: a ticket is valid 15 minutes


@dataclass(frozen=True)
class UploadTicketResult:
    upload_id: str
    url: str
    fields: dict[str, str]
    expires_at: datetime
    max_bytes: int


class CreateUploadTicket:
    def __init__(self, storage: ObjectStorage) -> None:
        self._storage = storage

    async def __call__(self, tenant_id: str) -> UploadTicketResult:
        upload_id = secrets.token_hex(16)
        ticket = await self._storage.presign_upload(
            incoming_key(tenant_id, upload_id), UPLOAD_MAX_BYTES, UPLOAD_TTL
        )
        return UploadTicketResult(
            upload_id=upload_id,
            url=ticket.url,
            fields=dict(ticket.fields),
            expires_at=ticket.expires_at,
            max_bytes=ticket.max_bytes,
        )
