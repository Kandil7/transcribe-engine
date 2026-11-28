"""Search (S18): index a completed transcript, search the tenant, list a transcript's chunks.

- POST /v1/transcriptions/{job_id}:index   builds the index of the job's latest version (D-085).
- GET  /v1/search?q=...                    full-text plus vector search over active versions.
- GET  /v1/transcriptions/{job_id}/rag-chunks   the chunks of the active version, in time order.

Every hit carries the media id, the start and end in milliseconds, and a player deep link (AC-8).
Without an embedder on this deployment these routes answer 503 (D-079).
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from transcribe_engine.application.errors import (
    SearchUnavailableError,
    TranscriptNotFoundError,
)
from transcribe_engine.application.ports.auth import ApiPrincipal
from transcribe_engine.application.ports.search import Embedder, SearchHit, SearchIndex
from transcribe_engine.application.ports.versions import TranscriptVersions
from transcribe_engine.application.use_cases.index_transcript import IndexTranscript
from transcribe_engine.application.use_cases.search_transcripts import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    SearchTranscripts,
)
from transcribe_engine.presentation.api.deps import require_scope
from transcribe_engine.presentation.api.schemas import (
    IndexOut,
    RagChunkOut,
    RagChunksOut,
    SearchHitOut,
    SearchOut,
)

router = APIRouter()


@dataclass(frozen=True)
class SearchServices:
    """What the search routes need. Built in main.py, where the adapters are chosen."""

    embedder: Embedder
    index: SearchIndex
    versions: TranscriptVersions


def _services(request: Request) -> SearchServices:
    services: SearchServices | None = request.app.state.search
    if services is None:
        raise SearchUnavailableError
    return services


def _deeplink(hit: SearchHit) -> str:
    return f"/media/{hit.media_id}?t={hit.start_ms // 1000}"


def _hit_out(hit: SearchHit) -> SearchHitOut:
    return SearchHitOut(
        chunk_id=hit.chunk_id,
        job_id=hit.transcript_id,
        version=hit.version,
        media_id=hit.media_id,
        start_ms=hit.start_ms,
        end_ms=hit.end_ms,
        body=hit.body,
        score=hit.score,
        deeplink=_deeplink(hit),
    )


@router.post("/v1/transcriptions/{job_id}:index", status_code=202, response_model=IndexOut)
async def index_transcription(
    request: Request,
    job_id: str,
    principal: Annotated[ApiPrincipal, Depends(require_scope("transcribe:write"))],
) -> JSONResponse:
    services = _services(request)
    transcript = await services.versions.latest(principal.tenant_id, job_id)
    if transcript is None:
        raise TranscriptNotFoundError
    result = await IndexTranscript(embedder=services.embedder, index=services.index)(
        transcript, tenant_id=principal.tenant_id
    )
    body = IndexOut(
        job_id=job_id,
        version=result.version,
        chunks=result.chunks,
        embedded=result.embedded,
        reused=result.reused,
    )
    return JSONResponse(status_code=202, content=body.model_dump())


@router.get("/v1/search", response_model=SearchOut)
async def search(
    request: Request,
    principal: Annotated[ApiPrincipal, Depends(require_scope("transcribe:read"))],
    q: Annotated[str, Query(min_length=1, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> SearchOut:
    services = _services(request)
    hits = await SearchTranscripts(embedder=services.embedder, index=services.index)(
        q, tenant_id=principal.tenant_id, limit=limit
    )
    return SearchOut(hits=[_hit_out(hit) for hit in hits])


@router.get("/v1/transcriptions/{job_id}/rag-chunks", response_model=RagChunksOut)
async def list_rag_chunks(
    request: Request,
    job_id: str,
    principal: Annotated[ApiPrincipal, Depends(require_scope("transcribe:read"))],
) -> RagChunksOut:
    services = _services(request)
    chunks = await services.index.chunks_of(principal.tenant_id, job_id)
    return RagChunksOut(
        job_id=job_id,
        chunks=[
            RagChunkOut(chunk_id=c.chunk_id, start_ms=c.start_ms, end_ms=c.end_ms, body=c.body)
            for c in chunks
        ],
    )
