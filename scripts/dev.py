"""Run the local stack (S10, `make dev`): compose services, migrations, the bucket, the API and the
cpu and gpu workers. Each process's output is prefixed by its name. Ctrl-C stops everything.

Workers run as local processes so they can use this machine's FFmpeg and, later, its GPU. Postgres
and MinIO run in docker-compose.
"""

import subprocess
import sys
import threading
from typing import IO

import boto3
from botocore.exceptions import ClientError

from transcribe_engine.infrastructure.settings import Settings

API_PORT = 8000


def _ensure_bucket(settings: Settings) -> None:
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    try:
        client.create_bucket(Bucket=settings.s3_bucket)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in (
            "BucketAlreadyOwnedByYou",
            "BucketAlreadyExists",
        ):
            raise


def _pump(name: str, stream: IO[str]) -> None:
    for line in stream:
        sys.stdout.write(f"[{name}] {line}")
        sys.stdout.flush()


def _start(name: str, args: list[str]) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.stdout is not None:
        threading.Thread(target=_pump, args=(name, process.stdout), daemon=True).start()
    return process


def main() -> int:
    subprocess.run(["docker", "compose", "up", "-d", "--wait"], check=True)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    settings = Settings()
    _ensure_bucket(settings)
    processes = {
        "api": _start(
            "api",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "transcribe_engine.api_server:create",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(API_PORT),
            ],
        ),
        "cpu": _start("cpu", [sys.executable, "-m", "transcribe_engine.worker", "cpu"]),
        "gpu": _start("gpu", [sys.executable, "-m", "transcribe_engine.worker", "gpu"]),
    }
    sys.stdout.write(f"stack up: API on http://127.0.0.1:{API_PORT}; Ctrl-C to stop\n")
    try:
        while all(p.poll() is None for p in processes.values()):
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes.values():
            if process.poll() is None:
                process.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
