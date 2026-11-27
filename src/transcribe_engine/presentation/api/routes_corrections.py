"""Human corrections (S22): save a new transcript version on a base version (D-061).

A stale base version is 409 (`stale_version`), an edit that needs alignment without an aligner is
503, and an edit that names a segment or word that is not there is 422.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from transcribe_engine.application.errors import CorrectionsUnavailableError
from transcribe_engine.application.ports.auth import ApiPrincipal
from transcribe_engine.domain.corrections import Edit
from transcribe_engine.presentation.api.deps import require_scope
from transcribe_engine.presentation.api.schemas import CorrectionIn, VersionOut

router = APIRouter()


@router.post("/v1/transcriptions/{job_id}/versions", status_code=201, response_model=VersionOut)
async def save_transcript_version(
    request: Request,
    job_id: str,
    body: CorrectionIn,
    principal: Annotated[ApiPrincipal, Depends(require_scope("transcribe:write"))],
) -> JSONResponse:
    save = request.app.state.save_correction
    if save is None:
        raise CorrectionsUnavailableError
    edits = tuple(
        Edit(
            segment_id=edit.segment_id,
            word_index_from=edit.word_index_from,
            word_index_to=edit.word_index_to,
            new_text=edit.new_text,
        )
        for edit in body.edits
    )
    version = await save(
        principal.tenant_id, job_id, body.base_version, edits, body.speaker_renames
    )
    return JSONResponse(
        status_code=201, content=VersionOut(job_id=job_id, version=version).model_dump()
    )
