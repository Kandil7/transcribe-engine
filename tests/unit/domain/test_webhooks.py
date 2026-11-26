"""S20 webhooks (AC-2 signature known vector, AC-3 private destinations refused, AC-4 retries until
24 hours). Each refusal has a positive control, so a guard that refuses everything, or a signature
that ignores its input, cannot pass. Imports happen inside helpers so the module collects before
the code exists.
"""

import importlib
import itertools
from types import ModuleType

SECRET = b"whsec_test"
TS = 1_700_000_000
BODY = b'{"event":"transcript.completed"}'
# HMAC-SHA256 over "<ts>.<body>" with the secret above, computed with the standard library.
KNOWN_SIGNATURE = "92ec8f1397131b8d5577305bf3682970db6bd65c22c59da1a2928b997dca10ea"


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _resolver(table: dict[str, list[str]]) -> object:
    def resolve(host: str) -> list[str]:
        return table[host]

    return resolve


def test_signature_known_vector() -> None:
    """AC-2: the signature matches the known vector. Positive control: changing the timestamp or
    the body changes the signature."""
    webhooks = _mod("transcribe_engine.domain.webhooks")
    assert webhooks.sign(BODY, SECRET, TS) == KNOWN_SIGNATURE
    assert webhooks.sign(BODY, SECRET, TS + 1) != KNOWN_SIGNATURE
    assert webhooks.sign(BODY + b" ", SECRET, TS) != KNOWN_SIGNATURE


def test_private_destinations_rejected() -> None:
    """AC-3: loopback, private, link-local and a DNS name that resolves to a private address are
    refused. Positive control: a public address is accepted."""
    webhooks = _mod("transcribe_engine.domain.webhooks")
    table = {
        "loopback.test": ["127.0.0.1"],
        "private.test": ["10.1.2.3"],
        "metadata.test": ["169.254.169.254"],
        "v6loop.test": ["::1"],
        "rebind.test": ["93.184.216.34", "192.168.0.5"],
        "public.test": ["93.184.216.34"],
    }
    resolve = _resolver(table)
    for host in ("loopback.test", "private.test", "metadata.test", "v6loop.test", "rebind.test"):
        assert webhooks.is_public_destination(f"https://{host}/hook", resolve) is False, host
    assert webhooks.is_public_destination("https://public.test/hook", resolve) is True


def test_retry_schedule_until_24h() -> None:
    """AC-4: retries back off, grow, and stop by 24 hours. Positive control: the schedule has more
    than one retry, so the backoff really grows."""
    webhooks = _mod("transcribe_engine.domain.webhooks")
    offsets = webhooks.retry_offsets()
    assert len(offsets) > 1
    assert list(offsets) == sorted(offsets)
    assert len(set(offsets)) == len(offsets)
    assert offsets[-1] <= 24 * 3600
    gaps = [b - a for a, b in itertools.pairwise(offsets)]
    assert gaps[-1] > gaps[0]
