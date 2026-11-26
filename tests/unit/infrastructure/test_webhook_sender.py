"""S20 webhook sender on httpx's mock transport: the body and headers arrive unchanged, the send
goes to the pinned address with the original host kept (D-053), redirects are not followed (also by
the default client), transport failures are TransientError without the URL, and the httpx transport
loggers never print the URL.

Each check has a positive control (a 204 is returned; the request count is exactly one), so a
sender that always fails or never sends cannot pass.
"""

import io
import logging

import httpx
import pytest

from transcribe_engine.domain.errors import TransientError
from transcribe_engine.infrastructure.http.webhook_sender import HttpWebhookSender
from transcribe_engine.infrastructure.observability.logging import (
    json_handler,
    quiet_transport_loggers,
)

URL = "https://hook.public.test/transcripts?token=SECRET-QUERY-VALUE"
PINNED = "93.184.216.34"
BODY = b'{"event":"transcript.completed","job_id":"job-1"}'
HEADERS = {"Content-Type": "application/json", "X-Transcribe-Signature": "t=1,v1=ab"}


def _sender(handler: httpx.MockTransport) -> HttpWebhookSender:
    return HttpWebhookSender(httpx.AsyncClient(transport=handler))


async def test_body_and_headers_are_sent_unchanged() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    status = await _sender(httpx.MockTransport(handler)).send(URL, BODY, HEADERS, PINNED)
    assert status == 204
    assert len(seen) == 1
    assert seen[0].content == BODY
    assert seen[0].headers["x-transcribe-signature"] == "t=1,v1=ab"


async def test_connects_to_the_pinned_address_and_keeps_the_host() -> None:
    """D-053: the TCP target is the verified address; Host and TLS name stay the destination."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    await _sender(httpx.MockTransport(handler)).send(URL, BODY, HEADERS, PINNED)
    assert seen[0].url.host == PINNED
    assert seen[0].headers["host"] == "hook.public.test"
    assert seen[0].extensions["sni_hostname"] == "hook.public.test"


async def test_redirect_is_not_followed() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://10.0.0.7/private"})

    status = await _sender(httpx.MockTransport(handler)).send(URL, BODY, HEADERS, PINNED)
    assert status == 302
    assert len(seen) == 1


def test_default_client_does_not_follow_redirects() -> None:
    """The sender built without a client must keep the no-redirect setting."""
    assert HttpWebhookSender()._client.follow_redirects is False


async def test_transport_error_is_transient_and_keeps_the_url_out() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"refused by {request.url.host}")

    with pytest.raises(TransientError) as caught:
        await _sender(httpx.MockTransport(handler)).send(URL, BODY, HEADERS, PINNED)
    assert str(caught.value) == "webhook transport failed"
    assert "hook.public.test" not in str(caught.value)


async def test_transport_logs_never_print_the_webhook_url() -> None:
    """httpx logs each request URL at INFO; the query can hold a token. With the transport loggers
    quieted (as configure_logging does) the URL is absent. Positive control: a line logged by the
    application does reach the captured output."""
    buffer = io.StringIO()
    root = logging.getLogger()
    handler = json_handler(buffer)
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    quiet_transport_loggers()
    try:
        logging.getLogger("transcribe_engine.test").info("control line")

        def handler_ok(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200)

        await _sender(httpx.MockTransport(handler_ok)).send(URL, BODY, HEADERS, PINNED)
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)
        logging.getLogger("httpx").setLevel(logging.NOTSET)
        logging.getLogger("httpcore").setLevel(logging.NOTSET)
    logged = buffer.getvalue()
    assert "control line" in logged
    assert "SECRET-QUERY-VALUE" not in logged
