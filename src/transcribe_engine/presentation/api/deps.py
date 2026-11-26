"""Request dependencies: the API key principal and scope checks (S08, D-026).

Authentication is an application use case (AuthenticateApiKey); this module only reads the header.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from transcribe_engine.application.errors import ForbiddenError, UnauthorizedError
from transcribe_engine.application.ports.auth import ApiPrincipal
from transcribe_engine.application.use_cases.authenticate import AuthenticateApiKey

BEARER_PREFIX = "Bearer "


async def current_principal(request: Request) -> ApiPrincipal:
    header = request.headers.get("authorization", "")
    if not header.startswith(BEARER_PREFIX):
        raise UnauthorizedError
    raw = header[len(BEARER_PREFIX) :].strip()
    principal = await AuthenticateApiKey(request.app.state.make_uow)(raw)
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
