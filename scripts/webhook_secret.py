"""Create a webhook signing secret for a tenant (S20, D-082).

Usage: uv run python scripts/webhook_secret.py <tenant_id>

Needs TE_SECRET_KEY (base64 of 32 random bytes). The new secret is printed once; only its
sealed form is stored. Older secrets beyond the two newest are retired. The key is never printed.
"""

import asyncio
import sys

from transcribe_engine.infrastructure.db.outbox import add_webhook_secret
from transcribe_engine.infrastructure.db.session import make_engine
from transcribe_engine.infrastructure.security.secret_box import parse_key
from transcribe_engine.infrastructure.settings import Settings


async def run(tenant_id: str) -> int:
    settings = Settings()
    if settings.secret_key is None:
        sys.stderr.write("set TE_SECRET_KEY first (base64 of 32 random bytes)\n")
        return 2
    key = parse_key(settings.secret_key.get_secret_value())
    engine = make_engine(settings.database_url)
    try:
        secret = await add_webhook_secret(engine, key, tenant_id)
    finally:
        await engine.dispose()
    sys.stdout.write(f"tenant {tenant_id}: secret (shown once): {secret}\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.stderr.write("usage: webhook_secret.py <tenant_id>\n")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(run(sys.argv[1])))
