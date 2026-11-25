"""POST /v1/uploads: issue a presigned POST ticket for a tenant-scoped upload (S08)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from transcribe_engine.application.ports.auth import ApiPrincipal
from transcribe_engine.application.use_cases.create_upload import CreateUploadTicket
from transcribe_engine.presentation.api.deps import require_scope
from transcribe_engine.presentation.api.schemas import UploadTicketOut

router = APIRouter()


@router.post("/v1/uploads", status_code=201, response_model=UploadTicketOut)
async def create_upload(
    request: Request,
    principal: Annotated[ApiPrincipal, Depends(require_scope("transcribe:write"))],
) -> UploadTicketOut:
    use_case = CreateUploadTicket(request.app.state.storage)
    result = await use_case(principal.tenant_id)
    return UploadTicketOut(
        upload_id=result.upload_id,
        url=result.url,
        fields=result.fields,
        expires_at=result.expires_at,
        max_bytes=result.max_bytes,
    )
