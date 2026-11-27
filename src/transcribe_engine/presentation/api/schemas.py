"""Response schemas for the S08 API. Field names are the public contract (see docs/openapi.json)."""

from datetime import datetime

from pydantic import BaseModel, Field


class UploadTicketOut(BaseModel):
    upload_id: str
    url: str
    fields: dict[str, str]
    expires_at: datetime
    max_bytes: int


class CreateTranscriptionIn(BaseModel):
    upload_id: str = Field(pattern=r"^[0-9a-f]{32}$")  # ids are server-generated (D-023)
    language: str
    engine: str | None = None
    diarization: bool = False
    webhook_url: str | None = None


class JobOut(BaseModel):
    id: str
    state: str
    stage: str | None
    progress: int
    warnings: list[str]
    error_code: str | None


class DeletionOut(BaseModel):
    id: str
    deletion_requested_at: datetime


class EditIn(BaseModel):
    segment_id: str
    word_index_from: int = Field(ge=0)
    word_index_to: int = Field(ge=0)
    new_text: str = Field(max_length=2000)


class CorrectionIn(BaseModel):
    base_version: int = Field(ge=1)
    edits: list[EditIn] = Field(default_factory=list, max_length=500)
    speaker_renames: dict[str, str] = Field(default_factory=dict)


class VersionOut(BaseModel):
    job_id: str
    version: int
