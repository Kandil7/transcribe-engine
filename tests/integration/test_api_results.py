"""S15 AC-8 over HTTP: every result format and both subtitle endpoints, with profiles.

Runs against Postgres and MinIO (Testcontainers), like test_api_result.py. The transcript is
written through the unit of work, as ProcessJob does. Each refusal has a positive control.
"""

import importlib
from types import ModuleType

import pytest

from tests.integration.api_support import (
    auth,
    build_client,
    create_job,
    force_state,
    issue_key,
    new_tenant,
    seed_tenant,
    storage_for,
    upload,
)
from transcribe_engine.infrastructure.db.session import make_engine

pytestmark = [pytest.mark.integration]

PAYLOAD = b"RIFF" + b"\x00" * 64
FORMATS = ("canonical", "txt", "md", "csv", "srt", "vtt")


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


async def test_formats_and_profiles(minio: object, app_url: str) -> None:
    """AC-8: each format answers 200 with its media type. The vertical profile splits a long
    fixture that the broadcast profile keeps as one cue, so the profile reaches the output.
    Positive control: the valid calls return 200; a bad format is 422."""
    tenant = new_tenant()
    engine = make_engine(app_url)
    await seed_tenant(engine, tenant)
    key = await issue_key(engine, tenant, ["transcribe:write", "transcribe:read"])
    merge = _mod("transcribe_engine.domain.merge")
    uow_mod = _mod("transcribe_engine.infrastructure.db.uow")
    merged = merge.MergedWords(
        words=tuple(merge.Word("كلمة", i * 500, i * 500 + 450, None, 0) for i in range(10)),
        sample_rate=16_000,
    )
    async with build_client(engine, storage_for(minio)) as client:  # type: ignore[arg-type]
        upload_id = await upload(client, key, PAYLOAD)
        job_id = (await create_job(client, key, upload_id)).json()["id"]
        await force_state(engine, job_id, "COMPLETED")
        async with uow_mod.SqlUnitOfWork(engine, tenant_id=tenant) as uow:
            await uow.chunks.save_transcript(tenant, job_id, merged)
            await uow.commit()
        base = f"/v1/transcriptions/{job_id}"
        for name in FORMATS:
            response = await client.get(f"{base}/result?format={name}", headers=auth(key))
            assert response.status_code == 200, name
            assert response.content, name
        broadcast = await client.get(
            f"{base}/subtitles?format=srt&profile=broadcast", headers=auth(key)
        )
        vertical = await client.get(
            f"{base}/subtitles?format=srt&profile=social_vertical", headers=auth(key)
        )
        refused = await client.get(f"{base}/result?format=docx", headers=auth(key))
    assert broadcast.status_code == 200
    assert vertical.status_code == 200
    assert broadcast.content != vertical.content
    assert refused.status_code == 422
    assert refused.json()["code"] == "unsupported_feature"
    await engine.dispose()
