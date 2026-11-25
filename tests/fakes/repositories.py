"""In-memory repositories and unit of work for the contract tests (S05).

All units of work from one FakeStore share data. Writes are immediate; there is no rollback,
which the contract tests do not rely on.
"""

from dataclasses import dataclass, field, replace
from typing import Self
from uuid import uuid4

from transcribe_engine.domain.config import PipelineConfig
from transcribe_engine.domain.jobs import Job, JobStage, JobState, Media, Result, Transition


@dataclass
class FakeStore:
    jobs: dict[str, Job] = field(default_factory=dict)
    media_by_sha: dict[str, Media] = field(default_factory=dict)
    results_by_key: dict[str, Result] = field(default_factory=dict)


class FakeJobRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    async def add(self, job: Job) -> None:
        if job.id in self._store.jobs:
            raise ValueError("job id already exists")
        self._store.jobs[job.id] = job

    async def get(self, tenant_id: str, job_id: str) -> Job | None:
        job = self._store.jobs.get(job_id)
        if job is None or job.tenant_id != tenant_id:
            return None
        return job

    async def apply(
        self, job_id: str, t: Transition, *, expected: JobState, stage: JobStage | None = None
    ) -> bool:
        job = self._store.jobs.get(job_id)
        if job is None or job.state != expected:
            return False
        self._store.jobs[job_id] = replace(
            job, state=t.to, error_code=t.error_code, stage=stage or job.stage
        )
        return True


class FakeMediaRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    async def upsert(self, media: Media) -> Media:
        return self._store.media_by_sha.setdefault(media.sha256, media)


class FakeResultRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    async def claim_key(
        self, result_key: str, media_id: str, config: PipelineConfig
    ) -> tuple[Result, bool]:
        existing = self._store.results_by_key.get(result_key)
        if existing is not None:
            return existing, False
        created = Result(
            id=uuid4().hex, result_key=result_key, media_id=media_id, config=config, ref_count=0
        )
        self._store.results_by_key[result_key] = created
        return created, True

    async def get_by_key(self, result_key: str) -> Result | None:
        return self._store.results_by_key.get(result_key)

    async def incr_ref(self, result_id: str, delta: int) -> int:
        for key, result in self._store.results_by_key.items():
            if result.id == result_id:
                updated = replace(result, ref_count=result.ref_count + delta)
                self._store.results_by_key[key] = updated
                return updated.ref_count
        raise KeyError(result_id)


class FakeUnitOfWork:
    def __init__(self, store: FakeStore) -> None:
        self.jobs = FakeJobRepository(store)
        self.media = FakeMediaRepository(store)
        self.results = FakeResultRepository(store)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def commit(self) -> None:
        return None
