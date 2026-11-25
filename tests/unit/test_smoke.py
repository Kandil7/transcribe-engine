from transcribe_engine.domain.errors import PermanentError, TransientError


def test_error_taxonomy_is_disjoint() -> None:
    assert not issubclass(TransientError, PermanentError)
    assert not issubclass(PermanentError, TransientError)
