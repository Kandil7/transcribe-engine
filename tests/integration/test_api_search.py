"""S18 AC-8 (integration, Postgres and MinIO): a search hit carries the media id, the start and
end in milliseconds, and a player deep link with ?t=<seconds>.

Positive control: the indexed word is found; a word that was never said returns no hits.
"""

import importlib
from types import ModuleType

import httpx
import pytest

from tests.fakes.embedder import FakeEmbedder
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


async def test_hit_has_deeplink(app_url: str, minio: object) -> None:
    main = _mod("transcribe_engine.main")
    uow_mod = _mod("transcribe_engine.infrastructure.db.uow")
    merge = _mod("transcribe_engine.domain.merge")
    tenant = new_tenant()
    engine = make_engine(app_url)
    await seed_tenant(engine, tenant)
    key = await issue_key(engine, tenant, ["transcribe:write", "transcribe:read"])
    app = main.build_app(engine=engine, storage=storage_for(minio), embedder=FakeEmbedder())
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
        words = ["alpha", "beta", "gamma", "delta"] * 5
        merged = merge.MergedWords(
            words=tuple(
                merge.Word(w, 5_000 + i * 400, 5_000 + i * 400 + 350, None, 0)
                for i, w in enumerate(words)
            ),
            sample_rate=16_000,
        )
        async with uow_mod.SqlUnitOfWork(engine, tenant_id=tenant) as uow:
            await uow.chunks.save_transcript(tenant, job_id, merged)
            await uow.commit()

        indexed = await client.post(f"/v1/transcriptions/{job_id}:index", headers=auth(key))
        assert indexed.status_code == 202

        hits = (await client.get("/v1/search", params={"q": "beta"}, headers=auth(key))).json()[
            "hits"
        ]
        assert hits
        hit = hits[0]
        assert hit["media_id"]
        assert hit["start_ms"] >= 0
        assert hit["end_ms"] > hit["start_ms"]
        assert f"?t={hit['start_ms'] // 1000}" in hit["deeplink"]

        none = (await client.get("/v1/search", params={"q": "zzznever"}, headers=auth(key))).json()[
            "hits"
        ]
        assert none == []
