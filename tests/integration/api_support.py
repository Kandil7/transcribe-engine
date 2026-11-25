"""Helpers for the S08 API tests: tenants, API keys, an ASGI client, uploads.

The app and the storage adapter are imported inside the helpers, so test modules collect before
the implementation exists (xfail tests fail at call time, not at import time).
"""

import contextlib
import hashlib
import importlib
import secrets
from datetime import timedelta
from types import ModuleType
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.minio import MinioContainer

BUCKET = "api-test"


def mod(name: str) -> ModuleType:
    return importlib.import_module(name)


async def seed_tenant(
    engine: AsyncEngine,
    tenant_id: str,
    *,
    max_active_jobs: int = 5,
    quota_audio_ms: int | None = None,
) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO tenants (id, max_active_jobs, quota_audio_ms) "
                "VALUES (:id, :max_jobs, :quota) ON CONFLICT (id) DO NOTHING"
            ),
            {"id": tenant_id, "max_jobs": max_active_jobs, "quota": quota_audio_ms},
        )


async def issue_key(engine: AsyncEngine, tenant_id: str, scopes: list[str]) -> str:
    """Create an API key; only its SHA-256 hash is stored (D-026). Returns the raw key once."""
    raw = "te_" + secrets.token_urlsafe(24)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO api_keys (id, tenant_id, key_hash, scopes) "
                "VALUES (:id, :tenant, :hash, :scopes)"
            ),
            {
                "id": secrets.token_hex(16),
                "tenant": tenant_id,
                "hash": hashlib.sha256(raw.encode()).hexdigest(),
                "scopes": scopes,
            },
        )
    return raw


def storage_for(minio: MinioContainer) -> Any:
    boto3 = importlib.import_module("boto3")
    cfg = minio.get_config()
    client = boto3.client(
        "s3",
        endpoint_url=f"http://{cfg['endpoint']}",
        aws_access_key_id=cfg["access_key"],
        aws_secret_access_key=cfg["secret_key"],
        region_name="us-east-1",
    )
    with contextlib.suppress(client.exceptions.BucketAlreadyOwnedByYou):
        client.create_bucket(Bucket=BUCKET)
    s3_mod = mod("transcribe_engine.infrastructure.storage.s3")
    return s3_mod.S3ObjectStorage(client, BUCKET)


def build_client(engine: AsyncEngine, storage: Any) -> httpx.AsyncClient:
    main = mod("transcribe_engine.main")
    app = main.build_app(engine=engine, storage=storage)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def upload(client: httpx.AsyncClient, token: str, payload: bytes) -> str:
    """Ask for a ticket and POST the bytes as a browser form would. Returns the upload id."""
    response = await client.post("/v1/uploads", headers=_auth(token))
    assert response.status_code == 201, response.text
    body = response.json()
    async with httpx.AsyncClient() as raw:
        posted = await raw.post(
            body["url"], data=dict(body["fields"]), files={"file": ("a.wav", payload)}
        )
    assert posted.status_code == 204, posted.text
    return str(body["upload_id"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def auth(token: str) -> dict[str, str]:
    return _auth(token)


async def create_job(
    client: httpx.AsyncClient, token: str, upload_id: str, **extra: Any
) -> httpx.Response:
    body: dict[str, Any] = {"upload_id": upload_id, "language": "ar", "diarization": False}
    body.update(extra)
    return await client.post("/v1/transcriptions", json=body, headers=_auth(token))


async def force_state(engine: AsyncEngine, job_id: str, state: str) -> None:
    """Move a job to a state directly, for tests that need a terminal job."""
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.system', 'on', true)")
        )  # RLS test-only scope
        await conn.execute(
            text("UPDATE jobs SET state = :s WHERE id = :id"), {"s": state, "id": job_id}
        )


DEFAULT_TTL = timedelta(minutes=15)
