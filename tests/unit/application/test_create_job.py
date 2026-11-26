"""AC-9 (S08): create-job use case on fakes. Presentation maps the domain errors to 404 and 422.

Each refusal is paired with a positive control, so a use case that always raises cannot pass.
Imports happen inside test bodies so the module collects before the use case exists.
"""

import importlib
from types import ModuleType

import pytest


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _command(upload_id: str, **overrides: object) -> object:
    use_cases = _mod("transcribe_engine.application.use_cases.create_job")
    fields: dict[str, object] = {
        "tenant_id": "tenant-a",
        "upload_id": upload_id,
        "language": "ar",
        "engine": None,
        "diarization": False,
        "webhook_url": None,
        "idempotency_key": None,
    }
    fields.update(overrides)
    return use_cases.CreateJobCommand(**fields)  # type: ignore[arg-type]


async def _world(max_active_jobs: int = 5, quota_audio_ms: int | None = None) -> tuple[object, ...]:
    """Fakes for the unit of work, storage, clock and tenant limits for tenant-a."""
    fakes_repo = _mod("tests.fakes.repositories")
    fakes_storage = _mod("tests.fakes.storage")
    fakes_tenants = _mod("tests.fakes.tenants")
    fakes_clock = _mod("tests.fakes.clock")
    store = fakes_repo.FakeStore()
    storage = fakes_storage.FakeObjectStorage()
    await storage.put("incoming/tenant-b/upload-b", b"RIFF")
    tenants = fakes_tenants.FakeTenants()
    tenants.add("tenant-a", max_active_jobs=max_active_jobs, quota_audio_ms=quota_audio_ms)

    def make_uow(tenant_id: str | None = None) -> object:
        return fakes_tenants.FakeApiUnitOfWork(store, tenants)

    return make_uow, storage, tenants, store, fakes_clock.FakeClock()


def _create(make_uow: object, storage: object, clock: object) -> object:
    use_cases = _mod("transcribe_engine.application.use_cases.create_job")
    return use_cases.CreateTranscriptionJob(make_uow, storage, clock)  # type: ignore[arg-type]


async def test_valid_upload_creates_a_queued_cpu_job() -> None:
    """Positive control: the same path with a real upload and language 'ar' creates one job."""
    make_uow, storage, _, store, clock = await _world()
    await storage.put("incoming/tenant-a/upload-a", b"RIFF")  # type: ignore[attr-defined]
    result = await _create(make_uow, storage, clock)(_command("upload-a"))  # type: ignore[operator]
    assert result.status == 202
    job = store.jobs[result.job_id]
    assert job.state.value == "PENDING_VALIDATION"
    assert job.queue == "cpu"
    assert len(store.jobs) == 1


async def test_upload_missing_is_not_found_and_writes_nothing() -> None:
    errors = _mod("transcribe_engine.application.errors")
    make_uow, storage, _, store, clock = await _world()
    with pytest.raises(errors.UploadNotFoundError):
        await _create(make_uow, storage, clock)(_command("upload-missing"))  # type: ignore[operator]
    assert store.jobs == {}


async def test_another_tenants_upload_is_not_found() -> None:
    """The incoming key is tenant-scoped, so tenant-a cannot see tenant-b's object."""
    errors = _mod("transcribe_engine.application.errors")
    make_uow, storage, _, store, clock = await _world()
    with pytest.raises(errors.UploadNotFoundError):
        await _create(make_uow, storage, clock)(_command("upload-b"))  # type: ignore[operator]
    assert store.jobs == {}


async def test_unsupported_language_is_refused_before_any_write() -> None:
    errors = _mod("transcribe_engine.application.errors")
    make_uow, storage, _, store, clock = await _world()
    await storage.put("incoming/tenant-a/upload-a", b"RIFF")  # type: ignore[attr-defined]
    with pytest.raises(errors.UnsupportedLanguageError):
        await _create(make_uow, storage, clock)(_command("upload-a", language="en"))  # type: ignore[operator]
    assert store.jobs == {}


async def test_webhook_is_refused_until_s20() -> None:
    errors = _mod("transcribe_engine.application.errors")
    make_uow, storage, _, store, clock = await _world()
    await storage.put("incoming/tenant-a/upload-a", b"RIFF")  # type: ignore[attr-defined]
    with pytest.raises(errors.UnsupportedFeatureError):
        await _create(make_uow, storage, clock)(  # type: ignore[operator]
            _command("upload-a", webhook_url="https://example.invalid/hook")
        )
    assert store.jobs == {}


async def test_concurrency_limit_refuses_the_extra_job() -> None:
    errors = _mod("transcribe_engine.application.errors")
    make_uow, storage, _, _, clock = await _world(max_active_jobs=1)
    await storage.put("incoming/tenant-a/upload-1", b"RIFF")  # type: ignore[attr-defined]
    await storage.put("incoming/tenant-a/upload-2", b"RIFF")  # type: ignore[attr-defined]
    create = _create(make_uow, storage, clock)
    await create(_command("upload-1"))  # type: ignore[operator]
    with pytest.raises(errors.TooManyActiveJobsError):
        await create(_command("upload-2"))  # type: ignore[operator]


async def test_quota_refuses_once_the_tenant_has_used_it() -> None:
    """D-025: quota is enforced on used audio, set directly here until S09 fills it."""
    errors = _mod("transcribe_engine.application.errors")
    make_uow, storage, _, store, clock = await _world(quota_audio_ms=1_000)
    media_mod = _mod("transcribe_engine.domain.jobs")
    store.media_by_tenant_sha[("tenant-a", "x")] = media_mod.Media(
        id="m-used",
        tenant_id="tenant-a",
        sha256="x",
        storage_key="k",
        duration_ms=1_000,
        format="wav",
        size_bytes=1,
    )
    await storage.put("incoming/tenant-a/upload-q", b"RIFF")  # type: ignore[attr-defined]
    with pytest.raises(errors.QuotaExceededError):
        await _create(make_uow, storage, clock)(_command("upload-q"))  # type: ignore[operator]
