"""Offline tests for src/diarize.py — pure annotation, no model stacks."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from diarize import Turn, assign_speakers

TURNS = [
    {"start": 0.0, "end": 10.0, "speaker": "SPEAKER_00"},
    {"start": 10.0, "end": 20.0, "speaker": "SPEAKER_01"},
    {"start": 25.0, "end": 30.0, "speaker": "SPEAKER_00"},
]


def test_segment_majority_overlap():
    segs = [
        {"start": 0.0, "end": 5.0, "text": "a"},  # entirely 00
        {"start": 8.0, "end": 15.0, "text": "b"},  # 2s in 00, 5s in 01
        {"start": 21.0, "end": 23.0, "text": "c"},  # gap: no speaker
    ]
    out, _words, speakers = assign_speakers(segs, [], TURNS)
    assert [s["speaker"] for s in out] == ["SPEAKER_00", "SPEAKER_01", ""]
    assert speakers == ["SPEAKER_00", "SPEAKER_01"]


def test_word_assignment_and_inner_words():
    segs = [
        {
            "start": 0.0,
            "end": 20.0,
            "text": "hello",
            "words": [
                {"word": "hello", "start": 1.0, "end": 2.0},
                {"word": "world", "start": 11.0, "end": 12.0},
            ],
        }
    ]
    words = [
        {"word": "hello", "start": 1.0, "end": 2.0, "score": 0.9},
        {"word": "world", "start": 11.0, "end": 12.0, "score": 0.8},
    ]
    out_segs, out_words, speakers = assign_speakers(segs, words, TURNS)
    assert out_words[0]["speaker"] == "SPEAKER_00"
    assert out_words[1]["speaker"] == "SPEAKER_01"
    # nested segment words are annotated copies too
    assert out_segs[0]["words"][0]["speaker"] == "SPEAKER_00"
    assert out_segs[0]["words"][1]["speaker"] == "SPEAKER_01"
    # inputs are not mutated
    assert "speaker" not in segs[0] and "speaker" not in words[0]
    assert speakers == ["SPEAKER_00", "SPEAKER_01"]


def test_no_turns():
    segs = [{"start": 0.0, "end": 5.0, "text": "a"}]
    out, _words, speakers = assign_speakers(segs, [], [])
    assert "speaker" not in out[0] or out[0]["speaker"] == ""
    assert speakers == []


def test_touching_turns_boundary():
    # interval exactly at the boundary belongs to whichever overlaps
    segs = [{"start": 9.0, "end": 11.0, "text": "x"}]
    out, _, _ = assign_speakers(segs, [], TURNS)
    # 1s in each of 00/01 — equal overlap, first max wins (00)
    assert out[0]["speaker"] == "SPEAKER_00"


def test_turn_dataclass():
    t = Turn(1.0, 2.0, "SPEAKER_00")
    assert t.start == 1.0 and t.speaker == "SPEAKER_00"


def test_load_audio_16k_roundtrip(tmp_path):
    import wave

    from diarize import _load_audio_16k

    # 0.25s of 16kHz silence as 16-bit PCM wav
    wav = tmp_path / "t.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 4000)
    audio = _load_audio_16k(str(wav), 16000)
    assert audio.dtype.name == "float32"
    assert 3900 <= audio.shape[0] <= 4100  # ~0.25s at 16kHz
