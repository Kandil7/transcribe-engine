"""YouTube metadata + audio via yt-dlp (imports deferred so tests stay light)."""

from __future__ import annotations

import time
from pathlib import Path

WATCH_URL = "https://www.youtube.com/watch?v={vid}"


def extract_metadata(url: str) -> dict:
    """Fetch video metadata without downloading. Tolerant to missing fields."""
    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    thumbs = info.get("thumbnails") or []
    thumb_url = thumbs[-1].get("url") if thumbs else info.get("thumbnail")
    upload = info.get("upload_date") or ""
    upload_date = (
        f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}" if len(upload) == 8 else ""
    )
    return {
        "video_id": info.get("id", ""),
        "video_title": info.get("title", ""),
        "channel": info.get("channel") or "",
        "channel_id": info.get("channel_id") or "",
        "upload_date": upload_date,
        "source_url": info.get("webpage_url") or url,
        "duration": float(info.get("duration") or 0),
        "tags": info.get("tags") or [],
        "thumbnail_url": thumb_url,
    }


def download_audio(url: str, output_dir: str = "data/raw_audio") -> str:
    """Download best audio as 16kHz mono WAV. Returns the wav path."""
    import yt_dlp

    Path(output_dir).mkdir(parents=True, exist_ok=True)
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
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        base = Path(ydl.prepare_filename(info)).with_suffix("")
    return str(base.with_suffix(".wav"))


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
