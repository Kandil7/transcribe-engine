"""Engine construction. NullPool: no connections are reused between units of work."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

__all__ = ["make_engine"]


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, poolclass=NullPool)
