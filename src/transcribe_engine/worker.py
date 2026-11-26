"""Worker entry point (S10): `python -m transcribe_engine.worker cpu|gpu|publisher`.

`publisher` runs the webhook outbox loop (S20) instead of claiming jobs.

Each process claims jobs from one queue, runs the handler, and writes the outcome through the fenced
queue. The reconciler runs between polls, so a crashed worker's lease is reclaimed. Handlers and
adapters come from the composition root (main.py).
"""

import asyncio
import os
import sys
import uuid
from datetime import timedelta

from transcribe_engine import main as composition
from transcribe_engine.application.ports.queue import JobQueue
from transcribe_engine.application.use_cases.publish_outbox import OutboxPublisher
from transcribe_engine.application.worker_loop import Handler, WorkerSettings, run_once
from transcribe_engine.infrastructure.db.queue import SqlJobQueue
from transcribe_engine.infrastructure.db.reconciler import SqlReconciler
from transcribe_engine.infrastructure.db.session import make_engine
from transcribe_engine.infrastructure.observability.logging import configure_logging
from transcribe_engine.infrastructure.settings import Settings

__all__ = ["main", "serve"]

ROLES = ("cpu", "gpu", "publisher")


async def serve(
    queue: JobQueue,
    handler: Handler,
    reconciler: SqlReconciler,
    settings: Settings,
    queue_name: str,
) -> None:
    """Claim and process jobs forever, reconciling between polls."""
    owner = f"{queue_name}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    worker = WorkerSettings(
        queue_name=queue_name,
        owner=owner,
        lease_for=timedelta(seconds=settings.lease_seconds),
        heartbeat_every=settings.heartbeat_seconds,
    )
    while True:
        await reconciler.run_once()
        worked = await run_once(queue, handler, worker)
        if not worked:
            await asyncio.sleep(settings.poll_seconds)


async def serve_publisher(publisher: OutboxPublisher, settings: Settings) -> None:
    """Deliver due webhook events forever (S20). Sleeps when nothing is due."""
    while True:
        delivered = await publisher.run_once()
        if delivered == 0:
            await asyncio.sleep(settings.poll_seconds)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ROLES:
        sys.stderr.write("usage: python -m transcribe_engine.worker cpu|gpu|publisher\n")
        return 2
    role = argv[1]
    configure_logging()
    settings = Settings()
    engine = make_engine(settings.database_url)
    if role == "publisher":
        asyncio.run(serve_publisher(composition.build_publisher(engine), settings))
        return 0
    storage = composition.build_storage(settings)
    ingest, process = composition.build_handlers(engine, storage, settings)
    handler: Handler = ingest if role == "cpu" else process
    asyncio.run(serve(SqlJobQueue(engine), handler, SqlReconciler(engine), settings, role))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
