"""v1 orchestration: single video + playlist with SQLite checkpoint."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path

try:
    from .normalize_ar import normalize_ar
    from .schema import VideoRecord
    from .transcribe import transcribe_ar
    from .youtube import download_audio, extract_metadata, get_playlist_video_urls
except ImportError:  # script-style execution
    from normalize_ar import normalize_ar  # type: ignore
    from schema import VideoRecord  # type: ignore
    from transcribe import transcribe_ar  # type: ignore
    from youtube import download_audio, extract_metadata, get_playlist_video_urls  # type: ignore

log = logging.getLogger("transcribe-engine")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

OUTPUT_JSONL = "data/output/videos.jsonl"
CHECKPOINT_DB = "data/output/checkpoint.db"


def _db(path: str = CHECKPOINT_DB) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE IF NOT EXISTS videos"
        "(video_id TEXT PRIMARY KEY, status TEXT, attempts INT, error TEXT)"
    )
    return con


def _mark(con: sqlite3.Connection, vid: str, status: str, error: str = "") -> None:
    con.execute(
        "INSERT INTO videos(video_id,status,attempts,error) VALUES(?,?,1,?)"
        " ON CONFLICT(video_id) DO UPDATE SET status=excluded.status,"
        " attempts=attempts+1, error=excluded.error",
        (vid, status, error),
    )
    con.commit()


def _done(con: sqlite3.Connection, vid: str) -> bool:
    row = con.execute("SELECT status FROM videos WHERE video_id=?", (vid,)).fetchone()
    return bool(row and row[0] == "ok")


def process_video(
    url: str,
    playlist_url: str = "",
    keep_audio: bool = False,
    retries: int = 3,
    db_path: str = CHECKPOINT_DB,
    jsonl_path: str = OUTPUT_JSONL,
) -> VideoRecord | None:
    con = _db(db_path)
    meta = extract_metadata(url)
    vid = meta["video_id"]
    if _done(con, vid):
        log.info("skip %s (already ok)", vid)
        return None
    audio = ""
    for attempt in range(1, retries + 1):
        try:
            audio = download_audio(url)
            res = transcribe_ar(audio)
            segments = res.get("segments", [])
            raw = " ".join(s.get("text", "") for s in segments).strip()
            rec = VideoRecord(
                video_id=vid,
                video_title=meta["video_title"],
                channel=meta["channel"],
                channel_id=meta["channel_id"],
                upload_date=meta["upload_date"],
                playlist_url=playlist_url,
                source_url=meta["source_url"],
                duration=meta["duration"],
                align_status=res.get("align_status", "ok"),
                transcript_raw=raw,
                transcript_norm=normalize_ar(raw),
                segments=[
                    {
                        "start": s.get("start"),
                        "end": s.get("end"),
                        "text": s.get("text", ""),
                        "words": s.get("words", []),
                    }
                    for s in segments
                ],
                word_segments=res.get("word_segments", []),
                model=res.get("model", ""),
            )
            Path(jsonl_path).parent.mkdir(parents=True, exist_ok=True)
            with open(jsonl_path, "a", encoding="utf-8") as f:
                f.write(rec.to_jsonl() + "\n")
            _mark(con, vid, "ok")
            log.info(
                "ok %s (%d segments, align=%s)", vid, len(segments), rec.align_status
            )
            return rec
        except Exception as e:  # noqa: BLE001
            log.warning("attempt %d/%d failed for %s: %s", attempt, retries, vid, e)
            _mark(con, vid, "failed", str(e))
            time.sleep(2**attempt)
        finally:
            if audio and not keep_audio:
                Path(audio).unlink(missing_ok=True)
    return None


def process_playlist(
    playlist_url: str,
    keep_audio: bool = False,
    db_path: str = CHECKPOINT_DB,
    jsonl_path: str = OUTPUT_JSONL,
) -> dict:
    urls = get_playlist_video_urls(playlist_url)
    log.info("playlist: %d videos", len(urls))
    ok = fail = 0
    for i, url in enumerate(urls, 1):
        log.info("[%d/%d] %s", i, len(urls), url)
        rec = process_video(
            url, playlist_url, keep_audio, db_path=db_path, jsonl_path=jsonl_path
        )
        ok += rec is not None
        fail += rec is None
        time.sleep(1.5)
    summary = {
        "playlist_url": playlist_url,
        "total": len(urls),
        "ok": ok,
        "failed": fail,
    }
    Path(jsonl_path).parent.mkdir(parents=True, exist_ok=True)
    with open(
        Path(jsonl_path).parent / "playlist_summary.json", "w", encoding="utf-8"
    ) as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary
