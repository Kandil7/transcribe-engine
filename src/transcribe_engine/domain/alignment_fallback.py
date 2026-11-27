"""Segment-time fallback for forced alignment (S14, D-077).

When alignment fails, the words of a segment are spread evenly over the segment's span, in order.
Each word gets a share of the span in proportion to its length, so a longer word takes a longer
span. The result is flagged as fallback. Times are integer samples, relative to the window start.
"""

from transcribe_engine.domain.merge import RawWord

__all__ = ["segment_times"]


def segment_times(text: str, start: int, end: int) -> tuple[RawWord, ...]:
    words = text.split()
    if not words:
        return ()
    if end <= start:
        raise ValueError("segment span must be positive")
    weights = [len(word) for word in words]
    total = sum(weights)
    span = end - start
    out: list[RawWord] = []
    cumulative = 0
    for word, weight in zip(words, weights, strict=True):
        begin = start + round(span * cumulative / total)
        cumulative += weight
        finish = start + round(span * cumulative / total)
        out.append(
            RawWord(text=word, local_start=begin, local_end=finish, conf=None, fallback=True)
        )
    return tuple(out)
