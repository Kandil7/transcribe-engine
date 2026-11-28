"""Chapters of a transcript (S19, AC-6): GET /v1/transcriptions/{job_id}/chapters.

`format=json` returns the chapter list. `format=youtube` returns "mm:ss title" lines (h:mm:ss from
one hour), which YouTube accepts for chapters. YouTube needs at least three chapters, and the first
starts at 00:00 (the domain rule starts the first chapter at 0).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from transcribe_engine.application.errors import ChaptersTooFewError, ChaptersUnavailableError
from transcribe_engine.application.ports.auth import ApiPrincipal
from transcribe_engine.domain.chapters import Chapter
from transcribe_engine.presentation.api.deps import require_scope
from transcribe_engine.presentation.api.schemas import ChapterOut, ChaptersOut

router = APIRouter()

YOUTUBE_MIN_CHAPTERS = 3


def _youtube_time(ms: int) -> str:
    seconds = ms // 1000
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _youtube_text(chapters: tuple[Chapter, ...]) -> str:
    if len(chapters) < YOUTUBE_MIN_CHAPTERS:
        raise ChaptersTooFewError
    lines = [f"{_youtube_time(c.start_ms)} {c.title}" for c in chapters]
    return "\n".join(lines) + "\n"


@router.get("/v1/transcriptions/{job_id}/chapters", response_model=None)
async def get_chapters(
    request: Request,
    job_id: str,
    principal: Annotated[ApiPrincipal, Depends(require_scope("transcribe:read"))],
    fmt: Annotated[Literal["json", "youtube"], Query(alias="format")] = "json",
) -> Response:
    service = request.app.state.chapters
    if service is None:
        raise ChaptersUnavailableError
    result = await service(principal.tenant_id, job_id)
    if fmt == "youtube":
        return PlainTextResponse(_youtube_text(result.chapters))
    body = ChaptersOut(
        job_id=job_id,
        version=result.version,
        chapters=[
            ChapterOut(title=c.title, start_ms=c.start_ms, end_ms=c.end_ms) for c in result.chapters
        ],
    )
    return JSONResponse(content=body.model_dump())
