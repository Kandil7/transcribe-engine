"""Webhook rules (S20, design: نقاط النهاية). Pure domain logic, standard library only.

- `sign`: HMAC-SHA256 over "<timestamp>.<body>". The receiver recomputes it and compares in
  constant time. The timestamp is in the signed string, so a replayed body with an old timestamp
  fails.
- `is_public_destination`: the destination is refused unless it is https on port 443 and every
  address it resolves to is global. IPv4-embedded IPv6 forms (mapped, 6to4, NAT64) are checked by
  their embedded IPv4 address too. The publisher pins the verified address for the send (D-053).
- `retry_offsets`: seconds after the first attempt at which each retry is sent. Delays double from
  30 s and cap at one hour; the schedule ends at 24 hours.
"""

import hashlib
import hmac
import ipaddress
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit

__all__ = ["is_public_destination", "retry_offsets", "sign"]

RETRY_WINDOW_S = 24 * 3600
FIRST_RETRY_DELAY_S = 30
MAX_RETRY_DELAY_S = 3600

Resolver = Callable[[str], Sequence[str]]


def sign(body: bytes, secret: bytes, ts: int) -> str:
    message = f"{ts}.".encode() + body
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def is_public_destination(url: str, resolve: Resolver) -> bool:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return False
    try:
        port = parts.port
    except ValueError:
        return False
    if port not in (None, 443):
        return False
    host = parts.hostname
    addresses = [host] if _is_ip_literal(host) else list(resolve(host))
    if not addresses:
        return False
    return all(_is_public_address(address) for address in addresses)


def retry_offsets() -> tuple[int, ...]:
    offsets: list[int] = []
    elapsed = 0
    delay = FIRST_RETRY_DELAY_S
    while True:
        elapsed += delay
        if elapsed > RETRY_WINDOW_S:
            break
        offsets.append(elapsed)
        delay = min(delay * 2, MAX_RETRY_DELAY_S)
    return tuple(offsets)


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def _is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address.strip("[]"))
    candidates: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [ip]
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            candidates.append(ip.ipv4_mapped)
        if ip.sixtofour is not None:
            candidates.append(ip.sixtofour)
        if ip in _NAT64:
            candidates.append(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    return all(_is_global(candidate) for candidate in candidates)


def _is_global(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # `is_global` is False for shared CGNAT space (100.64/10), which cloud metadata services use.
    return bool(ip.is_global) and not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )
