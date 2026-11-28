"""Response schemas for the S08 API. Field names are the public contract (see docs/openapi.json)."""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


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
    speakers: int | None = Field(default=None, ge=1, le=10)  # D-083
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
    segment_id: str = Field(max_length=64)
    word_index_from: int = Field(ge=0)
    word_index_to: int = Field(ge=0)
    new_text: str = Field(max_length=2000)


MAX_TEXT_CHARS_PER_REQUEST = 20_000  # the sum of new_text over all edits (S22 review)


class CorrectionIn(BaseModel):
    base_version: int = Field(ge=1)
    edits: list[EditIn] = Field(default_factory=list, max_length=500)
    speaker_renames: dict[str, str] = Field(default_factory=dict, max_length=64)

    @model_validator(mode="after")
    def _bounded_text(self) -> "CorrectionIn":
        if sum(len(edit.new_text) for edit in self.edits) > MAX_TEXT_CHARS_PER_REQUEST:
            raise ValueError("edits carry too much text in one request")
        if any(len(k) > 64 or len(v) > 200 for k, v in self.speaker_renames.items()):
            raise ValueError("speaker ids and labels are limited to 64 and 200 characters")
        return self


class VersionOut(BaseModel):
    job_id: str
    version: int


class IndexOut(BaseModel):
    job_id: str
    version: int
    chunks: int
    embedded: int
    reused: int


class SearchHitOut(BaseModel):
    chunk_id: str
    job_id: str
    version: int
    media_id: str
    start_ms: int
    end_ms: int
    body: str
    score: float
    deeplink: str


class SearchOut(BaseModel):
    hits: list[SearchHitOut]


class RagChunkOut(BaseModel):
    chunk_id: str
    start_ms: int
    end_ms: int
    body: str


class RagChunksOut(BaseModel):
    job_id: str
    chunks: list[RagChunkOut]


class ChapterOut(BaseModel):
    title: str
    start_ms: int
    end_ms: int


class ChaptersOut(BaseModel):
    job_id: str
    version: int
    chapters: list[ChapterOut]
