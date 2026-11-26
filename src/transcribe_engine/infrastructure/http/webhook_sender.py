"""HTTP webhook sender and DNS resolver for the publisher (S20, D-048, D-053).

The sender connects to the address the publisher verified, not to the name, so DNS cannot change
the target between the check and the connect (rebinding). The original host stays the Host header
and the TLS server name, so certificates are still checked against the destination. Redirects are
not followed: a 3xx is a failed attempt. Transport failures are TransientError without the URL.
"""

import socket
from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit

import httpx

from transcribe_engine.domain.errors import TransientError

__all__ = ["DnsResolver", "HttpWebhookSender", "resolve_host"]

DEFAULT_TIMEOUT_S = 10.0


class HttpWebhookSender:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT_S, follow_redirects=False
        )

    async def send(self, url: str, body: bytes, headers: Mapping[str, str], address: str) -> int:
        parts = urlsplit(url)
        host = parts.hostname or ""
        literal = f"[{address}]" if ":" in address else address
        pinned = urlunsplit((parts.scheme, literal, parts.path or "/", parts.query, ""))
        request_headers = {**headers, "Host": host}
        try:
            response = await self._client.post(
                pinned,
                content=body,
                headers=request_headers,
                extensions={"sni_hostname": host},
            )
        except httpx.TransportError as exc:
            # The message keeps no URL or body; those can name a tenant's destination.
            raise TransientError("webhook transport failed") from exc
        return response.status_code

    async def aclose(self) -> None:
        await self._client.aclose()


class DnsResolver:
    """The Resolver port over the system resolver (D-053)."""

    def resolve(self, host: str) -> list[str]:
        return resolve_host(host)


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
