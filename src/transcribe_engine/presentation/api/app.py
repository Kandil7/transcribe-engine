"""FastAPI application factory (S08). Dependencies arrive as values; no infrastructure imports."""

from collections.abc import Callable

from fastapi import FastAPI

from transcribe_engine.application.ports.clock import Clock
from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.presentation.api.errors import install_error_handlers
from transcribe_engine.presentation.api.routes_jobs import router as jobs_router
from transcribe_engine.presentation.api.routes_transcriptions import router as transcriptions_router
from transcribe_engine.presentation.api.routes_uploads import router as uploads_router


def create_app(
    make_uow: Callable[[str | None], object], storage: ObjectStorage, clock: Clock
) -> FastAPI:
    """`make_uow(tenant_id)` opens a unit of work scoped to a tenant (None = system, D-024)."""
    app = FastAPI(title="Transcribe Engine", version="0.1.0")
    app.state.make_uow = make_uow
    app.state.storage = storage
    app.state.clock = clock
    install_error_handlers(app)
    app.include_router(uploads_router)
    app.include_router(transcriptions_router)
    app.include_router(jobs_router)
    return app
