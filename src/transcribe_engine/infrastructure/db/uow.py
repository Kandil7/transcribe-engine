"""SQLAlchemy unit of work: one connection and one transaction per `async with` block (S05).

Leaving the block without `commit()` rolls the transaction back. Database errors are translated into
TransientError (connection-level, retry is sensible) or PermanentError (integrity) here,
at the adapter boundary (CLAUDE.md). The engine is built by the composition root, not here.
"""

from types import TracebackType
from typing import Self

from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncTransaction

from transcribe_engine.domain.errors import PermanentError, TransientError
from transcribe_engine.infrastructure.db.repositories import (
    SqlJobRepository,
    SqlMediaRepository,
    SqlResultRepository,
)

__all__ = ["SqlUnitOfWork"]


def _translate(exc: SQLAlchemyError) -> Exception:
    """Keep SQL text and parameters out of the error the caller sees."""
    if isinstance(exc, OperationalError | InterfaceError):
        return TransientError("database connection failed")
    if isinstance(exc, IntegrityError):
        return PermanentError("database rejected the write")
    return PermanentError("database error")


class SqlUnitOfWork:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
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
        try:
            if self._tx is not None and self._tx.is_active:
                await self._tx.rollback()
        finally:
            if self._conn is not None:
                await self._conn.close()
        if isinstance(exc, SQLAlchemyError):
            raise _translate(exc) from exc

    async def commit(self) -> None:
        if self._tx is None:
            raise RuntimeError("commit() outside the unit of work")
        try:
            await self._tx.commit()
        except SQLAlchemyError as exc:
            raise _translate(exc) from exc
