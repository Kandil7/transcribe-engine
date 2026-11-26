"""HTTP webhook sender and DNS resolver for the publisher (S20, D-048).

The sender never follows redirects: a 3xx answer is a failed attempt, so a redirect cannot move the
request to an address the SSRF check never saw. Transport failures (connect, timeout, TLS) are
TransientError and follow the retry schedule. The resolver is the one the publisher uses to check
each destination at send time.
"""

import socket
from collections.abc import Mapping

import httpx

from transcribe_engine.domain.errors import TransientError

__all__ = ["HttpWebhookSender", "resolve_host"]

DEFAULT_TIMEOUT_S = 10.0


class HttpWebhookSender:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT_S, follow_redirects=False
        )

    async def send(self, url: str, body: bytes, headers: Mapping[str, str]) -> int:
        try:
            response = await self._client.post(url, content=body, headers=dict(headers))
        except httpx.TransportError as exc:
            # The message keeps no URL or body; those can name a tenant's destination.
            raise TransientError("webhook transport failed") from exc
        return response.status_code

    async def aclose(self) -> None:
        await self._client.aclose()


def resolve_host(host: str) -> list[str]:
    """Every address the name resolves to. An empty list means the name does not resolve, which the
    publisher treats as not public."""
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    addresses: list[str] = []
    for info in infos:
        address = str(info[4][0])
        if address not in addresses:
            addresses.append(address)
    return addresses
