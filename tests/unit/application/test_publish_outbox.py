"""S20 publisher on fakes: AC-4 (retries follow the schedule until 24 hours, then the row is
abandoned), plus the signature header and the SSRF refusal at send time.

Each refusal has a positive control: a publisher that never retries, or never sends, cannot pass
the schedule test; a publisher that accepts every destination cannot pass the SSRF test.
Imports happen inside helpers so the module collects before the code exists.
"""

import importlib
import json
from datetime import timedelta
from types import ModuleType
from typing import Any

from tests.fakes.clock import FakeClock
from tests.fakes.outbox import FakeOutbox, FakeSecrets, FakeSender

SECRET = b"whsec_current"
SECRET_NEW = b"whsec_next"
TENANT = "tenant-a"
PUBLIC_HOST = "hook.public.test"
URL = f"https://{PUBLIC_HOST}/hooks/transcripts"
PUBLIC_IP = "93.184.216.34"
PRIVATE_IP = "10.0.0.7"


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _resolve(host: str) -> list[str]:
    table = {PUBLIC_HOST: [PUBLIC_IP], "rebind.public.test": [PUBLIC_IP, PRIVATE_IP]}
    return table[host]


def _payload(url: str = URL) -> dict[str, Any]:
    return {
        "event": "transcript.completed",
        "job_id": "job-1",
        "tenant_id": TENANT,
        "webhook_url": url,
    }


def _publisher(
    outbox: FakeOutbox, sender: FakeSender, clock: FakeClock, secrets: FakeSecrets | None = None
) -> Any:
    publish = _mod("transcribe_engine.application.use_cases.publish_outbox")
    return publish.OutboxPublisher(
        outbox,
        secrets or FakeSecrets({TENANT: (SECRET,)}),
        sender,
        clock,
        _resolve,
    )


async def test_retry_schedule_until_24h() -> None:
    """AC-4: attempts happen at creation and at each offset from `retry_offsets()`, the last one
    within 24 hours; after the last failed attempt the row is abandoned and never sent again.
    Positive control: the schedule has more than one retry, so the backoff really grows."""
    webhooks = _mod("transcribe_engine.domain.webhooks")
    clock = FakeClock()
    created = clock.now()
    outbox = FakeOutbox()
    outbox.add("transcript.completed", _payload(), created_at=created)
    sender = FakeSender(clock, statuses=[500] * 500)
    publisher = _publisher(outbox, sender, clock)

    expected = [created] + [created + timedelta(seconds=s) for s in webhooks.retry_offsets()]
    assert len(expected) > 2
    assert expected[-1] - created <= timedelta(hours=24)

    await publisher.run_once()
    steps = 0
    while (due := outbox.next_due_time()) is not None:
        steps += 1
        assert steps < 1000, "the publisher keeps a row due forever"
        clock.current = due
        await publisher.run_once()

    attempt_times = [sent_at for sent_at, *_ in sender.calls]
    assert attempt_times == expected
    row = outbox.rows[1]
    assert row.abandoned_at is not None
    assert row.published_at is None
    await publisher.run_once()
    assert len(sender.calls) == len(expected)


async def test_success_on_a_retry_stops_the_schedule() -> None:
    """Positive control for AC-4: a 2xx on the second attempt delivers the event.

    Retries end there."""
    clock = FakeClock()
    outbox = FakeOutbox()
    outbox.add("transcript.completed", _payload(), created_at=clock.now())
    sender = FakeSender(clock, statuses=[503, 204])
    publisher = _publisher(outbox, sender, clock)

    await publisher.run_once()
    clock.current = outbox.pending_due_times()[0]
    await publisher.run_once()
    assert outbox.rows[1].published_at is not None
    assert outbox.pending_due_times() == []
    assert len(sender.calls) == 2


async def test_signature_header_signs_with_every_active_secret() -> None:
    """Each active secret gives one v1 signature over "<ts>.<body>" (D-048); the body is the
    JSON payload. Positive control: the signature recomputed from the body matches."""
    webhooks = _mod("transcribe_engine.domain.webhooks")
    clock = FakeClock()
    outbox = FakeOutbox()
    outbox.add("transcript.completed", _payload(), created_at=clock.now())
    sender = FakeSender(clock)
    secrets = FakeSecrets({TENANT: (SECRET, SECRET_NEW)})
    await _publisher(outbox, sender, clock, secrets).run_once()

    sent_at, url, body, headers = sender.calls[0]
    assert url == URL
    assert json.loads(body)["job_id"] == "job-1"
    ts = int(sent_at.timestamp())
    expected = [webhooks.sign(body, s, ts) for s in (SECRET, SECRET_NEW)]
    signature = headers["X-Transcribe-Signature"]
    assert signature == f"t={ts}," + ",".join(f"v1={sig}" for sig in expected)


async def test_private_destination_is_abandoned_without_sending() -> None:
    """AC-3 at send time: a destination that resolves to a private address is never called and
    its row is abandoned. Positive control: the public destination is sent to."""
    clock = FakeClock()
    outbox = FakeOutbox()
    outbox.add(
        "transcript.completed",
        _payload("https://rebind.public.test/hook"),
        created_at=clock.now(),
    )
    outbox.add("transcript.completed", _payload(), created_at=clock.now())
    sender = FakeSender(clock)
    await _publisher(outbox, sender, clock).run_once()

    assert [url for _, url, _, _ in sender.calls] == [URL]
    assert outbox.rows[1].abandoned_at is not None
    assert outbox.rows[2].published_at is not None


async def test_transient_transport_error_is_retried() -> None:
    """A TransientError from the sender is a failed attempt, not a crash.

    It is rescheduled on the same schedule as an HTTP failure."""
    webhooks = _mod("transcribe_engine.domain.webhooks")
    clock = FakeClock()
    created = clock.now()
    outbox = FakeOutbox()
    outbox.add("transcript.completed", _payload(), created_at=created)
    sender = FakeSender(clock, raise_transient=True)
    await _publisher(outbox, sender, clock).run_once()
    assert outbox.rows[1].attempts == 1
    first_retry = created + timedelta(seconds=webhooks.retry_offsets()[0])
    assert outbox.pending_due_times() == [first_retry]
