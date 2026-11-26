import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest


def _module(name: str) -> ModuleType:
    # Imported lazily so the test file collects even when the module is missing.
    return importlib.import_module(name)


def _row(**overrides: object) -> str:
    row: dict[str, object] = {
        "audio": "dev/call_01.wav",
        "offset_ms": 0,
        "duration_ms": 4200,
        "text": "عايز أروح البيت",
        "speaker": "S1",
        "conditions": ["clean"],
    }
    row.update(overrides)
    return json.dumps(row, ensure_ascii=False)


def test_valid_turn_parses_into_integer_milliseconds() -> None:
    manifest = _module("evaluation.spike.manifest")

    turn = manifest.parse_line(1, _row())
    assert turn.offset_ms == 0
    assert turn.duration_ms == 4200
    assert turn.conditions == ("clean",)
    assert turn.speaker == "S1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"offset_ms": 1.5},  # seconds or fractions are not allowed at boundaries
        {"offset_ms": -1},
        {"duration_ms": 0},
        {"text": "عايز أروح، البيت"},  # guidelines §8: no punctuation
        {"text": "I want to go"},  # guidelines §3: Latin words in lowercase
        {"text": "عَايز"},  # guidelines §8: no diacritics
        {"speaker": "Speaker1"},  # guidelines §9: S1, S2, ...
        {"conditions": ["studio"]},  # guidelines §10: closed set
        {"conditions": []},
        {"conditions": ["silent"], "text": "عايز"},  # guidelines §7: silent means empty text
    ],
)
def test_invalid_turn_is_rejected(overrides: dict[str, object]) -> None:
    manifest = _module("evaluation.spike.manifest")

    with pytest.raises(manifest.ManifestError):
        manifest.parse_line(1, _row(**overrides))


def test_missing_key_is_named_in_the_error() -> None:
    manifest = _module("evaluation.spike.manifest")

    row = json.loads(_row())
    del row["speaker"]
    with pytest.raises(manifest.ManifestError, match="speaker"):
        manifest.parse_line(7, json.dumps(row, ensure_ascii=False))


def test_summary_counts_turns_speakers_duration_and_conditions(tmp_path: Path) -> None:
    manifest = _module("evaluation.spike.manifest")

    path = tmp_path / "manifest.jsonl"
    path.write_text(
        _row(offset_ms=0, duration_ms=1000, speaker="S1")
        + "\n"
        + _row(offset_ms=1000, duration_ms=2000, speaker="S2", conditions=["noisy"])
        + "\n",
        encoding="utf-8",
    )
    summary = manifest.summarize(manifest.load(path))
    assert summary.turns == 2
    assert summary.speakers == 2
    assert summary.total_ms == 3000
    assert summary.conditions == {"clean": 1, "noisy": 1}


def test_coverage_gate_reports_each_gap() -> None:
    manifest = _module("evaluation.spike.manifest")

    summary = manifest.summarize([manifest.Turn("a.wav", 0, 1000, "عايز", "S1", ("clean",))])
    problems = manifest.coverage_problems(summary)
    assert any("60 min" in problem for problem in problems)
    assert any("5 speakers" in problem for problem in problems)
    assert any("noisy" in problem for problem in problems)


def test_full_coverage_passes_the_gate() -> None:
    manifest = _module("evaluation.spike.manifest")

    turns = [
        manifest.Turn("a.wav", 0, 1_800_000, "عايز أروح البيت", "S1", ("clean",)),
        manifest.Turn("a.wav", 1_800_000, 1_200_000, "إزاي", "S2", ("noisy",)),
        manifest.Turn("b.wav", 0, 600_000, "meeting النهارده", "S3", ("code_switch",)),
        manifest.Turn("c.wav", 0, 1000, "", "S4", ("silent",)),
        manifest.Turn("c.wav", 1000, 1000, "", "S5", ("music",)),
    ]
    assert manifest.coverage_problems(manifest.summarize(turns)) == []


def test_cli_prints_counts_and_exits_zero_on_a_valid_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _module("evaluation.spike.validate_manifest")

    path = tmp_path / "manifest.jsonl"
    path.write_text(_row() + "\n", encoding="utf-8")
    assert cli.main([str(path)]) == 0
    out = capsys.readouterr().out
    assert "turns: 1" in out
    assert "speakers: 1" in out
