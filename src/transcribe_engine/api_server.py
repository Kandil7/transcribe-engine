"""ASGI entry point for the API in the local runtime (S10).

Run with: `uvicorn transcribe_engine.api_server:create --factory`. Settings: TE_* variables.
"""

from fastapi import FastAPI

from transcribe_engine import main as composition
from transcribe_engine.infrastructure.db.session import make_engine
from transcribe_engine.infrastructure.settings import Settings

__all__ = ["create"]


def create() -> FastAPI:
    settings = Settings()
    engine = make_engine(settings.database_url)
    storage = composition.build_storage(settings)
    return composition.build_app(engine, storage, embedder=composition.build_embedder(settings))
