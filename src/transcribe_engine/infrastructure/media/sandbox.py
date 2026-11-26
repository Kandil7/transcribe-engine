"""Run one FFmpeg tool: list argv, no shell, minimal environment, hard timeout (S09, D-029).

The production CPU worker runs in a Linux container that adds cgroup limits and a non-root user.
This function provides what any host can: no shell, a bounded time, a fixed environment, stderr
discarded (FFmpeg error text can contain file names, and the logs must not), and a cap on output.
"""

import asyncio
import os
from collections.abc import Sequence

from transcribe_engine.domain.errors import TransientError

__all__ = ["MAX_OUTPUT_BYTES", "run_tool"]

MAX_OUTPUT_BYTES = 16 * 2**20
_KEPT_ENV = ("PATH", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP")


async def run_tool(argv: Sequence[str], timeout_s: float) -> tuple[int, bytes]:
    """Return (exit code, stdout). Raises TransientError when the tool exceeds `timeout_s`."""
    env = {key: value for key, value in os.environ.items() if key in _KEPT_ENV}
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=env,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout_s)
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise TransientError("media tool timed out") from exc
    return process.returncode or 0, stdout[:MAX_OUTPUT_BYTES]
