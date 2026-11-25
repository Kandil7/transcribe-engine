"""Local seed (S08, autopilot 6.2): create a local tenant and an API key, print the key once,
and write it to `.env.local` (git-ignored). Run with `make seed`. Re-running issues a new key.
"""

import asyncio
import hashlib
import secrets
from pathlib import Path

from sqlalchemy import text

from transcribe_engine.infrastructure.db.session import make_engine
from transcribe_engine.infrastructure.settings import Settings

TENANT = "local"
SCOPES = ["transcribe:write", "transcribe:read"]
ENV_FILE = Path(__file__).resolve().parents[1] / ".env.local"


async def _seed(url: str) -> str:
    raw = "te_" + secrets.token_urlsafe(24)
    engine = make_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO tenants (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"),
                {"id": TENANT},
            )
            await conn.execute(
                text(
                    "INSERT INTO api_keys (id, tenant_id, key_hash, scopes) "
                    "VALUES (:id, :tenant, :hash, :scopes)"
                ),
                {
                    "id": secrets.token_hex(16),
                    "tenant": TENANT,
                    "hash": hashlib.sha256(raw.encode()).hexdigest(),
                    "scopes": SCOPES,
                },
            )
    finally:
        await engine.dispose()
    return raw


def main() -> None:
    raw = asyncio.run(_seed(Settings().database_url))
    ENV_FILE.write_text(f"TE_LOCAL_API_KEY={raw}\n", encoding="utf-8")
    print(f"Local tenant '{TENANT}' ready. API key (shown once, saved to .env.local):")
    print(raw)


if __name__ == "__main__":
    main()
