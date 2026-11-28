"""S19 AC-6 (integration, Postgres and MinIO, through the API): a transcript's chapters.

Chapters come from the transcript's pauses (D-081: by rule, no LLM). The YouTube format lists
them as "mm:ss title", and the first chapter starts at 00:00. Positive control: the chapter
list has a chapter for each long pause, and the first one starts at zero.
"""

import importlib
from types import ModuleType

import httpx
import pytest

from tests.integration.api_support import (
    auth,
    force_state,
    issue_key,
    new_tenant,
    seed_tenant,
    storage_for,
    upload,
)
from transcribe_engine.infrastructure.db.session import make_engine

pytestmark = [pytest.mark.integration, pytest.mark.contract]
PAYLOAD = b"RIFF" + b"\x00" * 64


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _segments_with_pauses(segment_count: int, seconds_each: int, pause_ms: int) -> list[object]:
    """Words spaced 1 s apart in segments of `seconds_each`, separated by `pause_ms` of silence."""
    merge = _mod("transcribe_engine.domain.merge")
    words = []
    cursor = 0
    for chunk_idx in range(segment_count):
        for i in range(seconds_each):
            words.append(merge.Word(f"w{chunk_idx}-{i}", cursor, cursor + 900, 0.9, chunk_idx))
            cursor += 1_000
        cursor += pause_ms
    return words


async def test_youtube_chapters_format(app_url: str, minio: object) -> None:
    merge = _mod("transcribe_engine.domain.merge")
    uow_mod = _mod("transcribe_engine.infrastructure.db.uow")
    tenant = new_tenant()
    engine = make_engine(app_url)
    await seed_tenant(engine, tenant)
    key = await issue_key(engine, tenant, ["transcribe:write", "transcribe:read"])
    app = _mod("transcribe_engine.main").build_app(engine=engine, storage=storage_for(minio))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            upload_id = await upload(client, key, PAYLOAD)
            created = await client.post(
                "/v1/transcriptions",
                headers=auth(key),
                json={"upload_id": upload_id, "language": "ar", "diarization": False},
            )
            job_id = created.json()["id"]
            await force_state(engine, job_id, "COMPLETED")
            merged = merge.MergedWords(
                words=tuple(_segments_with_pauses(4, 40, 3_000)), sample_rate=16_000
            )
            async with uow_mod.SqlUnitOfWork(engine, tenant_id=tenant) as uow:
                await uow.chunks.save_transcript(tenant, job_id, merged)
                await uow.commit()

            response = await client.get(
                f"/v1/transcriptions/{job_id}/chapters",
                params={"format": "youtube"},
                headers=auth(key),
            )
            assert response.status_code == 200
            lines = response.text.strip().splitlines()
            assert len(lines) == 4, lines
            assert lines[0].startswith("00:00 "), lines[0]

            as_json = await client.get(f"/v1/transcriptions/{job_id}/chapters", headers=auth(key))
            chapters = as_json.json()["chapters"]
            assert chapters[0]["start_ms"] == 0
            assert len(chapters) == 4
    finally:
        await engine.dispose()
