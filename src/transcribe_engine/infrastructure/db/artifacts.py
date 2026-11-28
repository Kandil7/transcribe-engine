"""Postgres artifact store (S19). Every statement runs in a transaction that sets the tenant,
so the row-level policy applies (D-024). `put` is an upsert on the key: a retried derivation
rewrites its row."""

import json
from collections.abc import Mapping
from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from transcribe_engine.domain.artifacts import Artifact, ArtifactKind

__all__ = ["SqlArtifactStore"]


async def _set_tenant(conn: AsyncConnection, tenant_id: str) -> None:
    await conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})


class SqlArtifactStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get(
        self,
        tenant_id: str,
        transcript_id: str,
        transcript_version: int,
        kind: ArtifactKind,
        model: str,
        model_version: str,
    ) -> Artifact | None:
        async with self._engine.begin() as conn:
            await _set_tenant(conn, tenant_id)
            row = (
                await conn.execute(
                    text(
                        "SELECT transcript_id, transcript_version, kind, model, model_version, "
                        "payload "
                        "FROM artifacts WHERE tenant_id = :t AND transcript_id = :tr "
                        "AND transcript_version = :v AND kind = :k AND model = :m "
                        "AND model_version = :mv"
                    ),
                    {
                        "t": tenant_id,
                        "tr": transcript_id,
                        "v": transcript_version,
                        "k": kind,
                        "m": model,
                        "mv": model_version,
                    },
                )
            ).first()
        if row is None:
            return None
        payload = row.payload
        if isinstance(payload, str):
            payload = json.loads(payload)
        return Artifact(
            transcript_id=row.transcript_id,
            transcript_version=int(row.transcript_version),
            kind=cast(ArtifactKind, row.kind),
            model=row.model,
            model_version=row.model_version,
            payload=cast(Mapping[str, object], payload),
        )

    async def put(self, tenant_id: str, artifact: Artifact) -> None:
        async with self._engine.begin() as conn:
            await _set_tenant(conn, tenant_id)
            await conn.execute(
                text(
                    "INSERT INTO artifacts (tenant_id, transcript_id, transcript_version, kind, "
                    "model, model_version, payload) "
                    "VALUES (:t, :tr, :v, :k, :m, :mv, CAST(:p AS jsonb)) "
                    "ON CONFLICT (tenant_id, transcript_id, transcript_version, kind, model, "
                    "model_version) DO UPDATE SET payload = EXCLUDED.payload"
                ),
                {
                    "t": tenant_id,
                    "tr": artifact.transcript_id,
                    "v": artifact.transcript_version,
                    "k": artifact.kind,
                    "m": artifact.model,
                    "mv": artifact.model_version,
                    "p": json.dumps(dict(artifact.payload), ensure_ascii=False),
                },
            )
