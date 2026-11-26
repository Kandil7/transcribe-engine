"""Authenticate a bearer API key (S08, D-026).

The key is hashed before lookup, so the raw key is never stored or compared. The lookup needs
no tenant: it runs in the system scope, and later queries use the key's tenant.
"""

import hashlib
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from transcribe_engine.application.errors import UnauthorizedError
from transcribe_engine.application.ports.auth import ApiPrincipal
from transcribe_engine.application.ports.repositories import UnitOfWork

__all__ = ["AuthenticateApiKey", "key_hash"]

MakeUow = Callable[[str | None], AbstractAsyncContextManager[UnitOfWork]]


def key_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AuthenticateApiKey:
    def __init__(self, make_uow: MakeUow) -> None:
        self._make_uow = make_uow

    async def __call__(self, raw: str) -> ApiPrincipal:
        if not raw:
            raise UnauthorizedError
        async with self._make_uow(None) as uow:
            principal = await uow.api_keys.find_by_hash(key_hash(raw))
        if principal is None:
            raise UnauthorizedError
        return principal
