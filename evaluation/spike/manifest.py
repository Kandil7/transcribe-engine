"""S00 dev manifest: one JSON object per speech turn (rules in evaluation/guidelines.ar.md).

Stdlib only: this is spike tooling and must run before the engine stack exists. Times are integer
milliseconds at the boundary (ADR-0003). The manifest holds text only; audio stays in data/.
"""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

CONDITIONS: frozenset[str] = frozenset({"clean", "noisy", "code_switch", "silent", "music"})
EMPTY_TEXT_CONDITIONS: frozenset[str] = frozenset({"silent", "music"})
REQUIRED_KEYS: tuple[str, ...] = (
    "audio",
    "offset_ms",
    "duration_ms",
    "text",
    "speaker",
    "conditions",
)
# §8: no punctuation, Latin or Arabic (comma, semicolon, question mark).
PUNCTUATION: frozenset[str] = frozenset(".,;:!?،؛؟")
# §8: no tashkeel (fathatan..sukun) and no tatweel.
DIACRITICS = re.compile("[ً-ْـ]")
SPEAKER = re.compile(r"S\d+")
MIN_TOTAL_MS = 60 * 60 * 1000
MIN_SPEAKERS = 5
REQUIRED_CONDITIONS: tuple[str, ...] = ("clean", "noisy", "code_switch")


class ManifestError(ValueError):
    """A manifest line breaks the format. The message names the line and rule, never the text."""


@dataclass(frozen=True)
class Turn:
    audio: str
    offset_ms: int
    duration_ms: int
    text: str
    speaker: str
    conditions: tuple[str, ...]


@dataclass(frozen=True)
class Summary:
    turns: int
    speakers: int
    total_ms: int
    conditions: dict[str, int]


def parse_line(line_no: int, raw: str) -> Turn:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"line {line_no}: not valid JSON") from exc
    if not isinstance(obj, dict):
        raise ManifestError(f"line {line_no}: expected a JSON object")
    missing = [key for key in REQUIRED_KEYS if key not in obj]
    if missing:
        raise ManifestError(f"line {line_no}: missing {', '.join(missing)}")

    audio = _text_field(line_no, obj, "audio", allow_empty=False)
    speaker = _text_field(line_no, obj, "speaker", allow_empty=False)
    if not SPEAKER.fullmatch(speaker):
        raise ManifestError(f"line {line_no}: speaker must look like S1, S2, ... (§9)")
    offset_ms = _integer_field(line_no, obj, "offset_ms", minimum=0)
    duration_ms = _integer_field(line_no, obj, "duration_ms", minimum=1)
    conditions = _conditions_field(line_no, obj)
    text = _text_field(line_no, obj, "text", allow_empty=True)
    _check_text(line_no, text, conditions)
    return Turn(audio, offset_ms, duration_ms, text, speaker, conditions)


def load(path: Path) -> list[Turn]:
    turns: list[Turn] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            if raw.strip():
                turns.append(parse_line(line_no, raw))
    return turns


def summarize(turns: Iterable[Turn]) -> Summary:
    rows = list(turns)
    counts: dict[str, int] = {}
    for turn in rows:
        for condition in turn.conditions:
            counts[condition] = counts.get(condition, 0) + 1
    return Summary(
        turns=len(rows),
        speakers=len({turn.speaker for turn in rows}),
        total_ms=sum(turn.duration_ms for turn in rows),
        conditions=dict(sorted(counts.items())),
    )


def coverage_problems(summary: Summary) -> list[str]:
    """The S00 coverage gate (§11): ≥ 60 min, ≥ 5 speakers, and each required condition present."""
    problems: list[str] = []
    if summary.total_ms < MIN_TOTAL_MS:
        problems.append(f"total is {summary.total_ms / 60_000:.1f} min, under 60 min")
    if summary.speakers < MIN_SPEAKERS:
        problems.append(f"{summary.speakers} speakers, need at least 5 speakers")
    for condition in REQUIRED_CONDITIONS:
        if condition not in summary.conditions:
            problems.append(f"no turns with condition {condition}")
    if not EMPTY_TEXT_CONDITIONS & summary.conditions.keys():
        problems.append("no silent or music turn")
    return problems


def _text_field(line_no: int, obj: dict[str, object], key: str, *, allow_empty: bool) -> str:
    value = obj[key]
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ManifestError(f"line {line_no}: {key} must be a non-empty string")
    return value


def _integer_field(line_no: int, obj: dict[str, object], key: str, *, minimum: int) -> int:
    value = obj[key]
    # type() check so that booleans and floats (seconds) are rejected at the boundary.
    if type(value) is not int or value < minimum:
        raise ManifestError(f"line {line_no}: {key} must be an integer ≥ {minimum} (milliseconds)")
    return value


def _conditions_field(line_no: int, obj: dict[str, object]) -> tuple[str, ...]:
    value = obj["conditions"]
    if not isinstance(value, list) or not value or not all(isinstance(c, str) for c in value):
        raise ManifestError(f"line {line_no}: conditions must be a non-empty list of strings")
    unknown = sorted(set(value) - CONDITIONS)
    if unknown:
        raise ManifestError(f"line {line_no}: unknown condition {', '.join(unknown)} (§10)")
    return tuple(value)


def _check_text(line_no: int, text: str, conditions: tuple[str, ...]) -> None:
    if any(ch in PUNCTUATION for ch in text):
        raise ManifestError(f"line {line_no}: text must not contain punctuation (§8)")
    if DIACRITICS.search(text):
        raise ManifestError(f"line {line_no}: text must not contain diacritics (§8)")
    if any(ch.isascii() and ch.isupper() for ch in text):
        raise ManifestError(f"line {line_no}: Latin words must be lowercase (§3)")
    if set(conditions) <= EMPTY_TEXT_CONDITIONS and text.strip():
        raise ManifestError(f"line {line_no}: silent or music turns must have empty text (§7)")
