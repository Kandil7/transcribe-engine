"""Composition root: the only module allowed to import from every layer (S08 onward).

Wires Ports to Adapters and builds the API app. Workers are wired here too in S10.
"""

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from transcribe_engine.application.ports.storage import ObjectStorage
from transcribe_engine.infrastructure.clock import SystemClock
from transcribe_engine.infrastructure.db.uow import SqlUnitOfWork
from transcribe_engine.presentation.api.app import create_app

__all__ = ["build_app"]


def build_app(engine: AsyncEngine, storage: ObjectStorage) -> FastAPI:
    def make_uow(tenant_id: str | None) -> SqlUnitOfWork:
        return SqlUnitOfWork(engine, tenant_id=tenant_id)

    return create_app(make_uow, storage, SystemClock())
