"""SQLAlchemy unit of work: one connection and one transaction per `async with` block (S05).

Leaving the block without `commit()` rolls the transaction back. Database errors are translated into
TransientError (connection-level, retry is sensible) or PermanentError (integrity) here,
at the adapter boundary (CLAUDE.md). The engine is built by the composition root, not here.
"""

from types import TracebackType
from typing import Self

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncTransaction

from transcribe_engine.domain.errors import PermanentError, TransientError
from transcribe_engine.infrastructure.db.api_keys import (
    SqlApiKeyRepository,
    SqlIdempotencyRepository,
    SqlTenantRepository,
)
from transcribe_engine.infrastructure.db.deletion import SqlDeletionStore
from transcribe_engine.infrastructure.db.repositories import (
    SqlChunkRepository,
    SqlJobRepository,
    SqlMediaRepository,
    SqlResultRepository,
)
from transcribe_engine.infrastructure.db.session import SYSTEM_SCOPE

__all__ = ["SqlUnitOfWork", "translate_db_error"]


def translate_db_error(exc: SQLAlchemyError) -> Exception:
    """Keep SQL text and parameters out of the error the caller sees."""
    if isinstance(exc, OperationalError | InterfaceError):
        return TransientError("database connection failed")
    if isinstance(exc, IntegrityError):
        return PermanentError("database rejected the write")
    return PermanentError("database error")


class SqlUnitOfWork:
    def __init__(self, engine: AsyncEngine, *, tenant_id: str | None) -> None:
        self._engine = engine
        self._tenant_id = tenant_id  # None means the system scope (workers, tests) (D-024)
        self._conn: AsyncConnection | None = None
        self._tx: AsyncTransaction | None = None
        self.jobs: SqlJobRepository
        self.media: SqlMediaRepository
        self.results: SqlResultRepository
        self.tenants: SqlTenantRepository
        self.idempotency: SqlIdempotencyRepository
        self.api_keys: SqlApiKeyRepository
        self.chunks: SqlChunkRepository
        self.deletions: SqlDeletionStore

    async def __aenter__(self) -> Self:
        self._conn = await self._engine.connect()
        self._tx = await self._conn.begin()
        if self._tenant_id is not None:
            await self._conn.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": self._tenant_id},
            )
        else:
            await self._conn.execute(SYSTEM_SCOPE)
        self.jobs = SqlJobRepository(self._conn)
        self.media = SqlMediaRepository(self._conn)
        self.results = SqlResultRepository(self._conn)
        self.tenants = SqlTenantRepository(self._conn)
        self.idempotency = SqlIdempotencyRepository(self._conn)
        self.api_keys = SqlApiKeyRepository(self._conn)
        self.chunks = SqlChunkRepository(self._conn)
        self.deletions = SqlDeletionStore(self._conn)
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
            raise translate_db_error(exc) from exc

    async def commit(self) -> None:
        if self._tx is None:
            raise RuntimeError("commit() outside the unit of work")
        try:
            await self._tx.commit()
        except SQLAlchemyError as exc:
            raise translate_db_error(exc) from exc
