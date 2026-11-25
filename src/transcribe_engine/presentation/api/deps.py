"""Request dependencies: the API key principal and scope checks (S08, D-026).

The key is hashed with SHA-256 and looked up in the system scope (api_keys has no RLS). The tenant
the key belongs to scopes every later query in the request.
"""

import hashlib
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from transcribe_engine.application.errors import ForbiddenError, UnauthorizedError
from transcribe_engine.application.ports.auth import ApiPrincipal

BEARER_PREFIX = "Bearer "


def key_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def current_principal(request: Request) -> ApiPrincipal:
    header = request.headers.get("authorization", "")
    if not header.startswith(BEARER_PREFIX):
        raise UnauthorizedError
    raw = header[len(BEARER_PREFIX) :].strip()
    if not raw:
        raise UnauthorizedError
    make_uow = request.app.state.make_uow
    principal: ApiPrincipal | None
    async with make_uow(None) as uow:
        principal = await uow.api_keys.find_by_hash(key_hash(raw))
    if principal is None:
        raise UnauthorizedError
    request.state.principal = principal
    return principal


def require_scope(scope: str) -> Callable[..., object]:
    async def _check(
        principal: Annotated[ApiPrincipal, Depends(current_principal)],
    ) -> ApiPrincipal:
        if scope not in principal.scopes:
            raise ForbiddenError
        return principal

    return _check
