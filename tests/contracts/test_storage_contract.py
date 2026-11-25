"""Contract tests for ObjectStorage (S07). Run against the Fake and the real S3 adapter (MinIO).

Imports happen inside each test so the module collects before the implementation exists.
Policy-enforcement and encryption tests (AC-1, AC-2, AC-5) run against MinIO only (D-014).
"""

import asyncio
import contextlib
import importlib
from collections.abc import Iterator
from datetime import timedelta
from types import ModuleType

import boto3
import httpx
import pytest
from botocore.exceptions import ClientError
from testcontainers.minio import MinioContainer

pytestmark = [pytest.mark.integration, pytest.mark.contract]

MINIO_IMAGE = "cgr.dev/chainguard/minio:latest"  # D-002


@pytest.fixture(scope="session")
def minio() -> Iterator[MinioContainer]:
    container = MinioContainer(MINIO_IMAGE).with_env(
        "MINIO_KMS_SECRET_KEY", "local-test:MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    )
    with container:
        yield container


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


async def test_read_range_exact_bytes(minio: MinioContainer) -> None:
    """AC-3: a range read returns exactly the requested bytes, including at the end."""
    data = bytes(range(256)) * 4
    for storage in (_fake(), _s3(minio)):
        await storage.put("contract/range.bin", data)
        assert await storage.read_range("contract/range.bin", 10, 5) == data[10:15]
        assert await storage.read_range("contract/range.bin", len(data) - 3, 3) == data[-3:]


async def test_delete_prefix_counts(minio: MinioContainer) -> None:
    """AC-6: delete_prefix returns the number of objects removed and leaves other keys alone."""
    for storage in (_fake(), _s3(minio)):
        for name in ("a", "b", "c"):
            await storage.put(f"del/{name}", b"x")
        await storage.put("keep/z", b"y")
        assert await storage.delete_prefix("del/") == 3
        assert await storage.head("keep/z") is not None
        assert await storage.head("del/a") is None


async def test_upload_over_limit_rejected(minio: MinioContainer) -> None:
    """AC-1: a presigned POST larger than max_bytes is refused by S3."""
    storage = _s3(minio)
    ticket = await storage.presign_upload(
        "incoming/t1/u1", max_bytes=10, expires=timedelta(minutes=15)
    )
    async with httpx.AsyncClient() as client:
        response = await client.post(
            ticket.url, data=dict(ticket.fields), files={"file": ("big.bin", b"x" * 11)}
        )
    assert response.status_code >= 400


async def test_ticket_expires(minio: MinioContainer) -> None:
    """AC-2: after the expiry the policy is refused. Uses a one-second expiry."""
    storage = _s3(minio)
    ticket = await storage.presign_upload(
        "incoming/t1/u2", max_bytes=100, expires=timedelta(seconds=1)
    )
    await asyncio.sleep(2)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            ticket.url, data=dict(ticket.fields), files={"file": ("ok.bin", b"x" * 5)}
        )
    assert response.status_code >= 400


async def test_put_sets_sse(minio: MinioContainer) -> None:
    """AC-5: every put is server-side encrypted; head reports it."""
    storage = _s3(minio)
    await storage.put("contract/sse.bin", b"secret")
    info = await storage.head("contract/sse.bin")
    assert info is not None
    assert info.encryption == "AES256"
