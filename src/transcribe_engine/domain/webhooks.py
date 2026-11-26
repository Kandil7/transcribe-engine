"""Webhook rules (S20, design: نقاط النهاية). Pure domain logic, standard library only.

- `sign`: HMAC-SHA256 over "<timestamp>.<body>". The receiver recomputes it and compares in
  constant time. The timestamp is in the signed string, so a replayed body with an old timestamp
  fails.
- `is_public_destination`: the destination is refused unless it is https and every address it
  resolves to is public. The check runs at send time, so a DNS record that changes to a private
  address after registration is refused too (SSRF, DNS rebinding).
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


def _is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address.strip("[]"))
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )
