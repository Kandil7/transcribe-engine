"""Engine construction. NullPool: no connections are reused between units of work."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

__all__ = ["SYSTEM_SCOPE", "make_engine"]

# Workers and the reconciler act for every tenant: each transaction sets the system scope (D-024).
SYSTEM_SCOPE = text("SELECT set_config('app.system', 'on', true)")


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, poolclass=NullPool)
