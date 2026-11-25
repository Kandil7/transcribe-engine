"""Contract tests for ObjectStorage (S07). Run against the Fake and the real S3 adapter (MinIO).

Imports happen inside each test so the module collects before the implementation exists.
Policy-enforcement and encryption tests (AC-1, AC-2, AC-5) run against MinIO only (D-014).
"""

import asyncio
import contextlib
import importlib
from datetime import UTC, datetime, timedelta
from types import ModuleType

import boto3
import httpx
import pytest
from botocore.exceptions import ClientError
from testcontainers.minio import MinioContainer

pytestmark = [pytest.mark.integration, pytest.mark.contract]

MINIO_IMAGE = "cgr.dev/chainguard/minio:latest"  # D-002


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _s3(minio: MinioContainer) -> object:
    """Real adapter on a MinIO bucket created for the test run."""
    s3_mod = _mod("transcribe_engine.infrastructure.storage.s3")
    cfg = minio.get_config()
    client = boto3.client(
        "s3",
        endpoint_url=f"http://{cfg['endpoint']}",
        aws_access_key_id=cfg["access_key"],
        aws_secret_access_key=cfg["secret_key"],
        region_name="us-east-1",
    )
    with contextlib.suppress(ClientError):  # already created by an earlier test in this session
        client.create_bucket(Bucket="contract-test")
    return s3_mod.S3ObjectStorage(client, "contract-test")


def _fake() -> object:
    return _mod("tests.fakes.storage").FakeObjectStorage()


async def _post_file(ticket: object, payload: bytes) -> httpx.Response:
    """Submit a file to a presigned POST ticket exactly as a browser form would."""
    async with httpx.AsyncClient() as client:
        return await client.post(
            ticket.url,  # type: ignore[attr-defined]
            data=dict(ticket.fields),  # type: ignore[attr-defined]
            files={"file": ("upload.bin", payload)},
        )


async def test_read_range_exact_bytes(minio: MinioContainer) -> None:
    """AC-3: a range read returns exactly the requested bytes, including at the end."""
    data = bytes(range(256)) * 4
    for storage in (_fake(), _s3(minio)):
        await storage.put("contract/range.bin", data)  # type: ignore[attr-defined]
        assert await storage.read_range("contract/range.bin", 10, 5) == data[10:15]  # type: ignore[attr-defined]
        assert await storage.read_range("contract/range.bin", len(data) - 3, 3) == data[-3:]  # type: ignore[attr-defined]


async def test_reads_past_the_end_and_missing_keys_are_permanent_errors(
    minio: MinioContainer,
) -> None:
    """A missing key or a start at or past the end raises PermanentError on both backends."""
    domain_errors = _mod("transcribe_engine.domain.errors")
    data = b"0123456789"
    for storage in (_fake(), _s3(minio)):
        await storage.put("contract/short.bin", data)  # type: ignore[attr-defined]
        with pytest.raises(domain_errors.PermanentError):
            await storage.read_range("contract/short.bin", len(data), 1)  # type: ignore[attr-defined]
        with pytest.raises(domain_errors.PermanentError):
            await storage.read_range("contract/does-not-exist.bin", 0, 1)  # type: ignore[attr-defined]


async def test_delete_prefix_counts(minio: MinioContainer) -> None:
    """AC-6: delete_prefix returns the number of objects removed and leaves other keys alone."""
    for storage in (_fake(), _s3(minio)):
        for name in ("a", "b", "c"):
            await storage.put(f"del/{name}", b"x")  # type: ignore[attr-defined]
        await storage.put("keep/z", b"y")  # type: ignore[attr-defined]
        assert await storage.delete_prefix("del/") == 3  # type: ignore[attr-defined]
        assert await storage.head("keep/z") is not None  # type: ignore[attr-defined]
        assert await storage.head("del/a") is None  # type: ignore[attr-defined]


async def test_delete_prefix_handles_more_than_one_batch(minio: MinioContainer) -> None:
    """AC-6: more than 1000 keys are listed across pages and deleted in batches."""
    for storage in (_fake(), _s3(minio)):
        for index in range(1001):
            await storage.put(f"bulk/{index:04d}", b"x")  # type: ignore[attr-defined]
        assert await storage.delete_prefix("bulk/") == 1001  # type: ignore[attr-defined]
        assert await storage.head("bulk/0000") is None  # type: ignore[attr-defined]


async def test_delete_prefix_rejects_unsafe_prefixes(minio: MinioContainer) -> None:
    """A prefix must name a whole segment: empty or without a trailing '/' is refused (D-015)."""
    for storage in (_fake(), _s3(minio)):
        for prefix in ("", "work/t1/job1"):
            with pytest.raises(ValueError, match="prefix"):
                await storage.delete_prefix(prefix)  # type: ignore[attr-defined]


async def test_upload_over_limit_rejected(minio: MinioContainer) -> None:
    """AC-1: a presigned POST over max_bytes is refused with EntityTooLarge; the same ticket accepts
    a file within the limit, so the refusal is caused by size and not by a broken form."""
    storage = _s3(minio)
    ticket = await storage.presign_upload(  # type: ignore[attr-defined]
        "incoming/t1/u1", max_bytes=10, expires=timedelta(minutes=15)
    )
    control = await _post_file(ticket, b"x" * 10)
    assert control.status_code == 204
    refused = await _post_file(ticket, b"x" * 11)
    assert refused.status_code == 400
    assert "EntityTooLarge" in refused.text


async def test_ticket_expires(minio: MinioContainer) -> None:
    """AC-2: a ticket accepted when issued is refused after its three-second expiry.

    The sleep is real time: MinIO judges the policy against its own clock, so the Clock port
    cannot drive it (documented exception in BUILD_LOG).
    """
    storage = _s3(minio)
    ticket = await storage.presign_upload(  # type: ignore[attr-defined]
        "incoming/t1/u2", max_bytes=100, expires=timedelta(seconds=3)
    )
    control = await _post_file(ticket, b"x" * 5)
    assert control.status_code == 204
    # Sleep past expires_at (MinIO compares whole seconds against its own clock).
    await asyncio.sleep((ticket.expires_at - datetime.now(UTC)).total_seconds() + 1)
    refused = await _post_file(ticket, b"x" * 5)
    assert refused.status_code == 403
    assert "expired" in refused.text.lower()


async def test_put_sets_sse(minio: MinioContainer) -> None:
    """AC-5: every put is server-side encrypted, from bytes and from an async iterator."""
    storage = _s3(minio)

    async def chunks() -> object:
        yield b"sec"
        yield b"ret"

    await storage.put("contract/sse-bytes.bin", b"secret")  # type: ignore[attr-defined]
    await storage.put("contract/sse-iter.bin", chunks())  # type: ignore[attr-defined]
    for key in ("contract/sse-bytes.bin", "contract/sse-iter.bin"):
        info = await storage.head(key)  # type: ignore[attr-defined]
        assert info is not None
        assert info.encryption == "AES256"
