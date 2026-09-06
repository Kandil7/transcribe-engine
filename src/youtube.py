"""YouTube metadata + audio via yt-dlp (imports deferred so tests stay light)."""

from __future__ import annotations

import time
from pathlib import Path

WATCH_URL = "https://www.youtube.com/watch?v={vid}"

AUDIO_DIR = "data/raw_audio"
_REUSE_MIN_BYTES = 1024 * 1024


def wav_duration(path: str | Path) -> float:
    """Duration in seconds of a wav file, -1.0 if unreadable (stdlib)."""
    import wave

    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:  # noqa: BLE001
        return -1.0


def _reusable_wav(path: Path, expected_duration: float = 0) -> bool:
    if not path.exists() or path.stat().st_size < _REUSE_MIN_BYTES:
        return False
    if expected_duration > 0:
        dur = wav_duration(path)
        if dur < 0:
            return False
        if abs(dur - expected_duration) > max(10.0, 0.05 * expected_duration):
            return False
    return True


def resolve_ffmpeg() -> str | None:
    """Locate an ffmpeg binary: env override → imageio-ffmpeg → PATH."""
    import os
    import shutil

    for env in ("FFMPEG_LOCATION", "FFMPEG_DIR", "FFMPEG_PATH"):
        p = os.environ.get(env)
        if p:
            return p
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass
    return shutil.which("ffmpeg")


def video_id_from_url(url: str) -> str:
    """Deterministic video id from a watch/shorts URL ('' if unparseable)."""
    from urllib.parse import parse_qs, urlparse

    try:
        q = parse_qs(urlparse(url).query)
        if q.get("v"):
            return q["v"][0]
        path = urlparse(url).path.strip("/").split("/")
        if path and path[-1]:
            return path[-1]
    except Exception:  # noqa: BLE001
        pass
    return ""


def extract_metadata(url: str) -> dict:
    """Fetch video metadata without downloading. Tolerant to missing fields.

    ``noplaylist`` is critical: a watch URL carrying ``&list=``/``&index=``
    params must never expand into a playlist download.
    """
    import yt_dlp

    with yt_dlp.YoutubeDL(
        {"quiet": True, "no_warnings": True, "noplaylist": True}
    ) as ydl:
        info = ydl.extract_info(url, download=False)
    # Defensive: if a playlist container ever slips through, take its entry
    # matching the URL instead of recording the playlist id as the video.
    if info.get("_type") == "playlist":
        want = video_id_from_url(url)
        entries = [e for e in (info.get("entries") or []) if e]
        pick = next(
            (e for e in entries if e.get("id") == want), entries[0] if entries else None
        )
        info = pick or {}
    vid = info.get("id", "") or video_id_from_url(url)
    thumbs = info.get("thumbnails") or []
    thumb_url = thumbs[-1].get("url") if thumbs else info.get("thumbnail")
    upload = info.get("upload_date") or ""
    upload_date = (
        f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}" if len(upload) == 8 else ""
    )
    return {
        "video_id": vid,
        "video_title": info.get("title", ""),
        "channel": info.get("channel") or "",
        "channel_id": info.get("channel_id") or "",
        "upload_date": upload_date,
        "source_url": info.get("webpage_url") or url,
        "duration": float(info.get("duration") or 0),
        "license": info.get("license") or "",
        "tags": info.get("tags") or [],
        "thumbnail_url": thumb_url,
    }


def download_audio(
    url: str,
    output_dir: str = AUDIO_DIR,
    ffmpeg_location: str | None = None,
    expected_duration: float = 0,
) -> tuple[str, bool]:
    """Download best audio as 16kHz mono WAV.

    Returns ``(wav_path, reused)``. Resumable: an existing wav whose
    duration matches ``expected_duration`` is reused instead of
    re-downloading (saves bandwidth on retries). ``noplaylist`` guards
    against watch URLs carrying ``&list=`` params.
    """
    import logging

    log = logging.getLogger("transcribe-engine")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    vid = video_id_from_url(url)
    if vid:
        existing = Path(output_dir) / f"{vid}.wav"
        if _reusable_wav(existing, expected_duration):
            log.info(
                "reuse existing audio %s (%.1fMB)",
                existing,
                existing.stat().st_size / 1e6,
            )
            return str(existing), True
    import yt_dlp  # heavy import only needed when actually downloading

    ffmpeg_location = ffmpeg_location or resolve_ffmpeg()
    opts = {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],
        "postprocessor_args": ["-ar", "16000", "-ac", "1"],
        "outtmpl": f"{output_dir}/%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    if ffmpeg_location:
        opts["ffmpeg_location"] = ffmpeg_location
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info.get("_type") == "playlist":
            raise ValueError(f"refusing playlist download for {url!r}")
        base = Path(ydl.prepare_filename(info)).with_suffix("")
    return str(base.with_suffix(".wav")), False


def get_playlist_video_urls(playlist_url: str, delay: float = 1.0) -> list[str]:
    """Expand a playlist to watch URLs. Skips private/deleted entries."""
    import yt_dlp

    with yt_dlp.YoutubeDL(
        {"quiet": True, "no_warnings": True, "extract_flat": True}
    ) as ydl:
        info = ydl.extract_info(playlist_url, download=False)
    urls: list[str] = []
    for entry in info.get("entries") or []:
        if not entry:
            continue
        vid = entry.get("id")
        if vid:
            urls.append(WATCH_URL.format(vid=vid))
    time.sleep(delay)
    return urls
