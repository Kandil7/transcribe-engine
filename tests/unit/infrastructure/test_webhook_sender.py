"""S20 webhook sender on httpx's mock transport: the body and headers arrive unchanged, redirects
are not followed, and transport failures are TransientError without the URL in the message.

Each check has a positive control (a 204 is returned; the request count is exactly one), so a
sender that always fails or never sends cannot pass.
"""

import httpx
import pytest

from transcribe_engine.domain.errors import TransientError
from transcribe_engine.infrastructure.http.webhook_sender import HttpWebhookSender

URL = "https://hook.public.test/transcripts"
BODY = b'{"event":"transcript.completed","job_id":"job-1"}'
HEADERS = {"Content-Type": "application/json", "X-Transcribe-Signature": "t=1,v1=ab"}


def _sender(handler: httpx.MockTransport) -> HttpWebhookSender:
    return HttpWebhookSender(httpx.AsyncClient(transport=handler))


async def test_body_and_headers_are_sent_unchanged() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    status = await _sender(httpx.MockTransport(handler)).send(URL, BODY, HEADERS)
    assert status == 204
    assert len(seen) == 1
    assert seen[0].content == BODY
    assert seen[0].headers["x-transcribe-signature"] == "t=1,v1=ab"
    assert str(seen[0].url) == URL


async def test_redirect_is_not_followed() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://10.0.0.7/private"})

    status = await _sender(httpx.MockTransport(handler)).send(URL, BODY, HEADERS)
    assert status == 302
    assert len(seen) == 1


async def test_transport_error_is_transient_and_keeps_the_url_out() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"refused by {request.url.host}")

    with pytest.raises(TransientError) as caught:
        await _sender(httpx.MockTransport(handler)).send(URL, BODY, HEADERS)
    assert str(caught.value) == "webhook transport failed"
    assert "hook.public.test" not in str(caught.value)
