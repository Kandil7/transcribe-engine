---
name: add-port-adapter
description: Add a new Port, or a new Adapter for an existing Port (ASR, VAD, aligner, diarizer, storage, queue, media probe, embeddings).
---
1. **Port** — `src/transcribe_engine/application/ports/<name>.py`: a `typing.Protocol`.
   Signatures use domain types only (no numpy arrays, no SQLAlchemy rows, no boto3 objects).
   If the Port has capabilities that differ by implementation, expose a frozen
   `<Name>Capabilities` dataclass (see `ASRCapabilities` in docs/design.md, "الـ Ports").
2. **Fake** — `tests/fakes/<name>.py`: deterministic, in-memory, no sleeps, no randomness
   unless seeded. It must be able to simulate `TransientError` and `PermanentError` on demand.
3. **Contract test** — `tests/contracts/test_<name>_contract.py`, parametrized over
   `[fake, real]`, marked `@pytest.mark.contract`. The real case is also `integration`
   (or `gpu` for model adapters). Same assertions for both; this keeps the Fake honest.
4. **Adapter** — `src/transcribe_engine/infrastructure/<area>/<impl>.py`.
   - Catch library exceptions at the boundary and raise `TransientError` / `PermanentError`.
   - Record `name` and `revision` for provenance.
   - Configuration through a pydantic-settings class in infrastructure, never globals.
5. **Wire** it only in `src/transcribe_engine/main.py`.
6. Run `make check` and `make itest` (and `pytest -m gpu` locally for model adapters).
