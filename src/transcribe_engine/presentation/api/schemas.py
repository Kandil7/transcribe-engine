"""Response schemas for the S08 API. Field names are the public contract (see docs/openapi.json)."""

from datetime import datetime

from pydantic import BaseModel


class UploadTicketOut(BaseModel):
    upload_id: str
    url: str
    fields: dict[str, str]
    expires_at: datetime
    max_bytes: int
