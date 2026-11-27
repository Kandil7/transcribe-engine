"""CTC Viterbi forced alignment (S14, D-070), pure Python so the domain stays free of numpy.

Given per-frame log-probabilities and the target token ids, find the most likely path through
the CTC lattice (blank between tokens, and between repeats of the same token). Each target gets
the first and last frame where the path emits it. Frames are model frames; the adapter converts
them to samples.
"""

import math
from itertools import pairwise

__all__ = ["ctc_viterbi"]

_NEG = -math.inf


def ctc_viterbi(
    log_probs: list[list[float]], targets: list[int], blank: int
) -> tuple[tuple[int, int], ...]:
    """Inclusive (first_frame, last_frame) for each target token, in order."""
    if not targets:
        return ()
    repeats = sum(1 for a, b in pairwise(targets) if a == b)
    if len(log_probs) < len(targets) + repeats:
        raise ValueError("too few frames to place every token")
    extended = [blank]
    for token in targets:
        extended += [token, blank]
    back, final = _forward(log_probs, extended, blank)
    path = _backtrack(back, final)
    return _spans(path, len(targets))


def _forward(
    log_probs: list[list[float]], extended: list[int], blank: int
) -> tuple[list[list[int]], int]:
    """Best score per state, frame by frame. Returns the back-pointers and the final state."""
    states = len(extended)
    back = [[0] * states for _ in log_probs]
    prev = [_NEG] * states
    prev[0] = log_probs[0][blank]
    if states > 1:
        prev[1] = log_probs[0][extended[1]]
    for t in range(1, len(log_probs)):
        cur = [_NEG] * states
        for s in range(states):
            best, step = _best_predecessor(prev, extended, blank, s)
            if best > _NEG:
                cur[s] = best + log_probs[t][extended[s]]
            back[t][s] = step
        prev = cur
    end = states - 1
    if states > 1 and prev[states - 2] > prev[states - 1]:
        end = states - 2
    return back, end


def _best_predecessor(
    prev: list[float], extended: list[int], blank: int, s: int
) -> tuple[float, int]:
    """The best score that can reach state s, and how many states back it came from."""
    best, step = prev[s], 0
    if s >= 1 and prev[s - 1] > best:
        best, step = prev[s - 1], 1
    skip_allowed = s >= 2 and extended[s] != blank and extended[s] != extended[s - 2]
    if skip_allowed and prev[s - 2] > best:
        best, step = prev[s - 2], 2
    return best, step


def _backtrack(back: list[list[int]], final: int) -> list[int]:
    path = [0] * len(back)
    path[-1] = final
    for t in range(len(back) - 1, 0, -1):
        path[t - 1] = path[t] - back[t][path[t]]
    return path


def _spans(path: list[int], count: int) -> tuple[tuple[int, int], ...]:
    first: dict[int, int] = {}
    last: dict[int, int] = {}
    for t, s in enumerate(path):
        if s % 2 == 1:  # odd states are the target tokens
            k = (s - 1) // 2
            first.setdefault(k, t)
            last[k] = t
    if len(first) != count:
        raise ValueError("alignment did not place every token")
    return tuple((first[k], last[k]) for k in range(count))
