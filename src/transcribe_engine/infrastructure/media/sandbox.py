"""Run one FFmpeg tool: list argv, no shell, minimal environment, hard timeout (S09, D-029).

The production CPU worker runs in a Linux container that adds cgroup limits and a non-root user.
This function provides what any host can: no shell, a bounded time, a fixed environment, stderr
discarded (FFmpeg error text can contain file names, and the logs must not), and a cap on output.
"""

import asyncio
import contextlib
import os
from collections.abc import Sequence

from transcribe_engine.application.ports.media import CorruptMediaError
from transcribe_engine.domain.errors import TransientError

__all__ = ["MAX_OUTPUT_BYTES", "run_tool"]

MAX_OUTPUT_BYTES = 16 * 2**20
_READ_CHUNK = 64 * 1024
_STOP_TIMEOUT_S = 10.0
_KEPT_ENV = ("PATH", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP")


async def run_tool(argv: Sequence[str], timeout_s: float) -> tuple[int, bytes]:
    """Return (exit code, stdout). Raises TransientError on timeout and CorruptMediaError when
    stdout passes MAX_OUTPUT_BYTES. Either way the process is killed first (review fix, D-029)."""
    env = {key: value for key, value in os.environ.items() if key in _KEPT_ENV}
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=env,
    )
    try:
        return await asyncio.wait_for(_drain(process), timeout_s)
    except TimeoutError as exc:
        await _stop(process)
        raise TransientError("media tool timed out") from exc
    except CorruptMediaError:
        await _stop(process)
        raise


async def _drain(process: asyncio.subprocess.Process) -> tuple[int, bytes]:
    """Read stdout in chunks and stop as soon as it exceeds the cap, so memory is bounded."""
    buffer = bytearray()
    if process.stdout is None:
        raise CorruptMediaError("media tool has no stdout pipe")
    while chunk := await process.stdout.read(_READ_CHUNK):
        buffer += chunk
        if len(buffer) > MAX_OUTPUT_BYTES:
            raise CorruptMediaError("media tool produced too much output")
    code = await process.wait()
    return code, bytes(buffer)


async def _stop(process: asyncio.subprocess.Process) -> None:
    """Kill the tool and reap it. On Windows, wait() can block while stdout is unread, so drain
    the pipe to EOF first, and bound both steps so a stuck child cannot stall the worker."""
    if process.returncode is None:
        process.kill()
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(_discard(process), _STOP_TIMEOUT_S)


async def _discard(process: asyncio.subprocess.Process) -> None:
    if process.stdout is not None:
        while await process.stdout.read(_READ_CHUNK):
            pass
    await process.wait()
