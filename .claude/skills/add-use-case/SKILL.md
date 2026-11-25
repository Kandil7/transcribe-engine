---
name: add-use-case
description: Add an application use case (e.g. CreateTranscriptionJob, CancelJob, ProcessChunk) with its unit tests on fakes.
---
1. File: `src/transcribe_engine/application/use_cases/<verb_noun>.py`. One public class with
   `__init__(self, <ports...>)` and one `async def __call__(self, cmd: <Command>) -> <Result>`.
2. `Command` and `Result` are frozen dataclasses in the same file. No pydantic here.
3. The use case orchestrates; rules live in the domain. If you write an `if` about job state,
   idempotency or time conversion here, move it into `domain/`.
4. Transactions: accept a `UnitOfWork` port when more than one repository write must be atomic.
5. Errors: raise domain errors only. Never catch `Exception`.
6. Tests: `tests/unit/application/test_<verb_noun>.py` using `tests/fakes/`. One test per
   acceptance criterion plus the failure paths (transient, permanent, not found, not owner).
7. Expose it in `main.py`; presentation calls it through dependency injection.
