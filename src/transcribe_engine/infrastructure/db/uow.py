"""SQLAlchemy unit of work: one connection and one transaction per `async with` block (S05).

Leaving the block without `commit()` rolls the transaction back.
"""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncTransaction

from transcribe_engine.infrastructure.db.repositories import (
    SqlJobRepository,
    SqlMediaRepository,
    SqlResultRepository,
)
from transcribe_engine.infrastructure.db.session import make_engine

__all__ = ["SqlUnitOfWork"]


class SqlUnitOfWork:
    def __init__(self, url_or_engine: str | AsyncEngine) -> None:
        if isinstance(url_or_engine, str):
            self._engine = make_engine(url_or_engine)
            self._owns_engine = True
        else:
            self._engine = url_or_engine
            self._owns_engine = False
        self._conn: AsyncConnection | None = None
        self._tx: AsyncTransaction | None = None
        self.jobs: SqlJobRepository
        self.media: SqlMediaRepository
        self.results: SqlResultRepository

    async def __aenter__(self) -> Self:
        self._conn = await self._engine.connect()
        self._tx = await self._conn.begin()
        self.jobs = SqlJobRepository(self._conn)
        self.media = SqlMediaRepository(self._conn)
        self.results = SqlResultRepository(self._conn)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._tx is not None and self._tx.is_active:
            await self._tx.rollback()
        if self._conn is not None:
            await self._conn.close()
        if self._owns_engine:
            await self._engine.dispose()

    async def commit(self) -> None:
        if self._tx is None:
            raise RuntimeError("commit() outside the unit of work")
        await self._tx.commit()
