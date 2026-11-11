"""Audio I/O shared by the engine and the annotation features.

- ``ensure_ffmpeg_on_path`` — make a ``ffmpeg`` binary discoverable for
  subprocess decoders (coherex and this package both shell out).
- ``load_audio_16k`` — decode any audio file to a float32 mono waveform
  via the ffmpeg CLI. transformers.audio_utils.load_audio needs
  torchcodec + shared-FFmpeg DLLs this box lacks, so the pipeline
  standardizes on the plain CLI.
"""

from __future__ import annotations


def ensure_ffmpeg_on_path() -> str | None:
    """Make a `ffmpeg` binary discoverable for coherex subprocess calls.

    coherex.audio.load_audio hard-codes ``ffmpeg`` on PATH. On machines
    without a system ffmpeg (e.g. Windows + imageio-ffmpeg only), copy the
    resolved binary to ``data/bin/ffmpeg.exe`` and prepend it to PATH.
    Returns the ffmpeg path, or None if none could be found.
    """
    import os
    import shutil

    from .youtube import resolve_ffmpeg

    exe = resolve_ffmpeg()
    if not exe or not os.path.exists(exe):
        return shutil.which("ffmpeg")
    # Only usable as-is when literally named ffmpeg(.exe), e.g. not the
    # imageio-ffmpeg `ffmpeg-win-x86_64-v7.1.exe` build.
    if os.path.basename(exe).lower() in ("ffmpeg", "ffmpeg.exe"):
        d = os.path.dirname(os.path.abspath(exe))
        if d not in os.environ.get("PATH", ""):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        return exe
    shim_dir = os.path.join("data", "bin")
    os.makedirs(shim_dir, exist_ok=True)
    shim = os.path.abspath(os.path.join(shim_dir, "ffmpeg.exe"))
    if not os.path.exists(shim):
        shutil.copyfile(exe, shim)
    d = os.path.dirname(shim)
    if d not in os.environ.get("PATH", ""):
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
    return shim


def load_audio_16k(path: str, sampling_rate: int = 16000):
    """Decode audio to a float32 mono waveform via the ffmpeg CLI:
    ffmpeg -i <path> -f f32le -ac 1 -ar <rate> pipe:1
    """
    import subprocess

    import numpy as np

    ensure_ffmpeg_on_path()
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        path,
        "-f",
        "f32le",
        "-ac",
        "1",
        "-ar",
        str(sampling_rate),
        "pipe:1",
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()
