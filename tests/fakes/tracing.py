"""In-memory tracer for the S20 tests: records each closed span by job and stage."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class FakeTracer:
    closed: list[tuple[str, str, str]] = field(default_factory=list)  # (job_id, stage, status)

    @contextmanager
    def span(self, job_id: str, stage: str) -> Generator[None]:
        status = "ok"
        try:
            yield
        except BaseException:
            status = "error"
            raise
        finally:
            self.closed.append((job_id, stage, status))
