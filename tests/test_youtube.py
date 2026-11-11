"""Offline tests for youtube helpers (no network, no yt-dlp download)."""

import sys
import wave
from pathlib import Path

import pytest

from src.youtube import (
    _reusable_wav,
    download_audio,
    video_id_from_url,
    wav_duration,
)


def test_video_id_from_url_watch():
    assert (
        video_id_from_url("https://www.youtube.com/watch?v=ZXWzWWXzPmU")
        == "ZXWzWWXzPmU"
    )


def test_video_id_from_url_ignores_list_params():
    url = "https://www.youtube.com/watch?v=ZXWzWWXzPmU&list=PLxxx&index=2"
    assert video_id_from_url(url) == "ZXWzWWXzPmU"


def test_video_id_from_url_shorts():
    assert (
        video_id_from_url("https://www.youtube.com/shorts/abcDEF123_-") == "abcDEF123_-"
    )


def test_video_id_from_url_unparseable():
    assert video_id_from_url("not a url") == "not a url"


def _write_wav(path: Path, seconds: float) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))


def test_wav_duration(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, 10.0)
    assert wav_duration(p) == pytest.approx(10.0)
    assert wav_duration(tmp_path / "missing.wav") == -1.0


def test_reusable_wav_validates_duration(tmp_path):
    p = tmp_path / "v.wav"
    _write_wav(p, 5.0)
    # 5s mono 16-bit = ~160KB, below the 1MB floor -> not reusable
    assert not _reusable_wav(p, 5.0)
    big = tmp_path / "big.wav"
    with wave.open(str(big), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000 * 60)
    assert big.stat().st_size > 1024 * 1024
    assert _reusable_wav(big, 60.0)
    assert not _reusable_wav(big, 600.0)  # duration mismatch -> re-download


def test_download_audio_reuses_validated_wav(tmp_path, monkeypatch):
    vid = "VID12345678"
    wav = tmp_path / f"{vid}.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000 * 60)
    # yt-dlp must never be touched on the reuse path: block the import.
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    path, reused = download_audio(
        f"https://www.youtube.com/watch?v={vid}",
        output_dir=str(tmp_path),
        expected_duration=60.0,
    )
    assert reused is True
    assert path == str(wav)
