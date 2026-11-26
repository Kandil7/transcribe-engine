"""S09 media contract: the real FFmpeg adapters (AC-1, AC-2, AC-6, AC-8).

These run the real ffprobe and ffmpeg binaries. Fixtures are generated into a temp directory, never
committed. Tests skip with a reason when the binaries are not on PATH.
Imports happen inside helpers so the module collects before the adapters exist.
"""

import importlib
import shutil
import subprocess
import sys
import wave
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.contract


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _require(binary: str) -> None:
    if shutil.which(binary) is None:
        pytest.skip(f"{binary} is not on PATH")


def _sine(path: Path, codec_args: list[str], rate: int = 44_100, channels: int = 2) -> Path:
    """Generate one second of sine with ffmpeg into `path`."""
    subprocess.run(  # noqa: S603 - fixed argv, no shell, test fixture (D-029)
        [  # noqa: S607 - ffmpeg resolved from PATH in a test fixture (D-029)
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-ac",
            str(channels),
            "-ar",
            str(rate),
            *codec_args,
            "-y",
            str(path),
        ],
        check=True,
        timeout=60,
    )
    return path


def _probe(work: Path) -> Any:
    return _mod("transcribe_engine.infrastructure.media.ffprobe").FfprobeMediaProbe(work_root=work)


def _normalizer() -> Any:
    return _mod("transcribe_engine.infrastructure.media.ffmpeg").FfmpegNormalizer()


async def test_playlist_rejected(tmp_path: Path) -> None:
    """AC-1. An .mp3 that is really an HLS playlist pointing at file:///etc/passwd is refused.

    The magic-byte check refuses it before any FFmpeg process starts, so nothing is opened from the
    referenced path. Positive control: a real WAV named .mp3 is probed (test_extension_ignored...).
    """
    media = _mod("transcribe_engine.application.ports.media")
    playlist = tmp_path / "evil.mp3"
    playlist.write_text(
        "#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:1.0,\nfile:///etc/passwd\n#EXT-X-ENDLIST\n",
        encoding="utf-8",
    )
    with pytest.raises(media.UnsupportedMediaError):
        await _probe(tmp_path).probe(playlist)


async def test_extension_ignored_format_from_probe(tmp_path: Path) -> None:
    """AC-2. The format comes from ffprobe, not the file name: a WAV named .mp3 probes as wav."""
    _require("ffprobe")
    _require("ffmpeg")
    wav = _sine(tmp_path / "source.wav", ["-c:a", "pcm_s16le"])
    disguised = wav.rename(tmp_path / "disguised.mp3")
    info = await _probe(tmp_path).probe(disguised)
    assert "wav" in info.format_name
    assert info.duration_ms == pytest.approx(1000, abs=50)
    assert info.sample_rate == 44_100
    assert info.channels == 2


async def test_output_is_pcm16_mono_16k(tmp_path: Path) -> None:
    """AC-6. Normalization writes 16 kHz mono 16-bit PCM WAV."""
    _require("ffmpeg")
    src = _sine(tmp_path / "in.flac", ["-c:a", "flac"], rate=44_100, channels=2)
    dst = tmp_path / "audio.wav"
    result = await _normalizer().to_pcm16_mono_16k(src, dst, timeout_s=60)
    with wave.open(str(dst), "rb") as handle:
        assert handle.getframerate() == 16_000
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
    assert result.sample_rate == 16_000
    assert result.channels == 1
    assert result.duration_ms == pytest.approx(1000, abs=50)


async def test_probe_timeout_is_transient(tmp_path: Path) -> None:
    """AC-8. A stalled probe binary is a transient failure (the job may retry), not a bad file."""
    domain_errors = _mod("transcribe_engine.domain.errors")
    stalled = (sys.executable, "-c", "import time; time.sleep(60)")
    probe = _mod("transcribe_engine.infrastructure.media.ffprobe").FfprobeMediaProbe(
        work_root=tmp_path, binary=stalled, timeout_s=1.0
    )
    clip = tmp_path / "clip.wav"
    clip.write_bytes(b"RIFF" + b"\x00" * 64)
    with pytest.raises(domain_errors.TransientError):
        await probe.probe(clip)
