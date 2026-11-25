"""AC-9 (S08): create-job use case on fakes. Presentation maps the domain errors to 404 and 422.

Imports happen inside test bodies so the module collects before the use case exists.
"""

import importlib
from types import ModuleType

import pytest

pytestmark = [pytest.mark.xfail(strict=True, reason="S08")]


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


async def _world() -> tuple[object, object, object]:
    """Fakes for storage, unit of work and tenant limits. A tenant-a and a tenant-b upload exist."""
    fakes_repo = _mod("tests.fakes.repositories")
    fakes_storage = _mod("tests.fakes.storage")
    fakes_tenants = _mod("tests.fakes.tenants")
    store = fakes_repo.FakeStore()
    storage = fakes_storage.FakeObjectStorage()
    await storage.put("incoming/tenant-b/upload-b", b"RIFF")
    tenants = fakes_tenants.FakeTenants()
    tenants.add("tenant-a", max_active_jobs=5, quota_audio_ms=None)

    def make_uow() -> object:
        return fakes_tenants.FakeApiUnitOfWork(store, tenants)

    return make_uow, storage, tenants


async def test_upload_missing_is_not_found() -> None:
    errors = _mod("transcribe_engine.application.errors")
    use_cases = _mod("transcribe_engine.application.use_cases.create_job")
    make_uow, storage, _ = await _world()
    create = use_cases.CreateTranscriptionJob(make_uow, storage)
    with pytest.raises(errors.UploadNotFound):
        await create(_command("upload-missing"))


async def test_another_tenants_upload_is_not_found() -> None:
    """The incoming key is tenant-scoped, so tenant-a cannot see tenant-b's object."""
    errors = _mod("transcribe_engine.application.errors")
    use_cases = _mod("transcribe_engine.application.use_cases.create_job")
    make_uow, storage, _ = await _world()
    create = use_cases.CreateTranscriptionJob(make_uow, storage)
    with pytest.raises(errors.UploadNotFound):
        await create(_command("upload-b"))


async def test_unsupported_language_is_refused_before_any_write() -> None:
    errors = _mod("transcribe_engine.application.errors")
    use_cases = _mod("transcribe_engine.application.use_cases.create_job")
    make_uow, storage, _ = await _world()
    await storage.put("incoming/tenant-a/upload-a", b"RIFF")
    create = use_cases.CreateTranscriptionJob(make_uow, storage)
    with pytest.raises(errors.UnsupportedLanguage):
        await create(_command("upload-a", language="en"))


async def test_webhook_is_refused_until_s20() -> None:
    errors = _mod("transcribe_engine.application.errors")
    use_cases = _mod("transcribe_engine.application.use_cases.create_job")
    make_uow, storage, _ = await _world()
    await storage.put("incoming/tenant-a/upload-a", b"RIFF")
    create = use_cases.CreateTranscriptionJob(make_uow, storage)
    with pytest.raises(errors.UnsupportedFeature):
        await create(_command("upload-a", webhook_url="https://example.invalid/hook"))


async def test_concurrency_limit_refuses_the_extra_job() -> None:
    errors = _mod("transcribe_engine.application.errors")
    use_cases = _mod("transcribe_engine.application.use_cases.create_job")
    make_uow, storage, tenants = await _world()
    tenants.set_limit("tenant-a", max_active_jobs=1)
    await storage.put("incoming/tenant-a/upload-1", b"RIFF")
    await storage.put("incoming/tenant-a/upload-2", b"RIFF")
    create = use_cases.CreateTranscriptionJob(make_uow, storage)
    await create(_command("upload-1"))
    with pytest.raises(errors.TooManyActiveJobs):
        await create(_command("upload-2"))
