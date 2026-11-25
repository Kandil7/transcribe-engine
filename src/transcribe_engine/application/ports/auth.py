"""API key authentication port (S08). Keys are stored as SHA-256 hashes only (D-026)."""

from dataclasses import dataclass
from typing import Protocol

__all__ = ["ApiKeyRepository", "ApiPrincipal"]


@dataclass(frozen=True)
class ApiPrincipal:
    tenant_id: str
    key_id: str
    scopes: frozenset[str]


class ApiKeyRepository(Protocol):
    async def find_by_hash(self, key_hash: str) -> ApiPrincipal | None:
        """Active (not revoked) key with this hash, or None."""
        ...
