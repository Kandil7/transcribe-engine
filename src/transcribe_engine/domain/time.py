"""Time units. Inside the pipeline time is integer samples; at boundaries it is integer ms.

No floats anywhere (ADR-0003). `samples_to_ms` floors, so a partial millisecond is never rounded up.
"""

__all__ = ["SAMPLE_RATE", "ms_to_samples", "samples_to_ms"]

SAMPLE_RATE = 16_000


def samples_to_ms(samples: int, sample_rate: int = SAMPLE_RATE) -> int:
    """Convert a sample count to whole milliseconds, rounding down."""
    return samples * 1000 // sample_rate


def ms_to_samples(ms: int, sample_rate: int = SAMPLE_RATE) -> int:
    """Convert milliseconds to samples. Exact whenever `ms * sample_rate` is a multiple of 1000."""
    return ms * sample_rate // 1000
