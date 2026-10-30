"""v1 orchestration: single video + playlist with SQLite checkpoint."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path

try:
    from .normalize_ar import NORM_VERSION, normalize_ar
    from .qa import qa_checks, qa_scores
    from .schema import VideoRecord
    from .transcribe import TranscribeConfig, TranscribeSession, transcribe_ar
    from .youtube import (
        download_audio,
        extract_metadata,
        get_playlist_video_urls,
        video_id_from_url as _video_id_from_url,
    )
except ImportError:  # script-style execution
    from normalize_ar import NORM_VERSION, normalize_ar  # type: ignore
    from qa import qa_checks, qa_scores  # type: ignore
    from schema import VideoRecord  # type: ignore
    from transcribe import TranscribeConfig, TranscribeSession, transcribe_ar  # type: ignore
    from youtube import (  # type: ignore
        download_audio,
        extract_metadata,
        get_playlist_video_urls,
        video_id_from_url as _video_id_from_url,
    )

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
        (vid, status, error[:500]),
    )
    con.commit()


def _done(con: sqlite3.Connection, vid: str) -> bool:
    row = con.execute("SELECT status FROM videos WHERE video_id=?", (vid,)).fetchone()
    return bool(row and row[0] == "ok")


def _upsert_jsonl(jsonl_path: str, rec: VideoRecord) -> None:
    """Append-or-replace one record: videos.jsonl stays idempotent on video_id."""
    path = Path(jsonl_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    kept: list[str] = []
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    if json.loads(line).get("video_id") == rec.video_id:
                        continue
                except json.JSONDecodeError:
                    pass
                kept.append(line if line.endswith("\n") else line + "\n")
    kept.append(rec.to_jsonl() + "\n")
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(kept)


def _git_sha() -> str:
    try:
        import subprocess

        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def write_manifest(
    path: str | Path, summary: dict, config: TranscribeConfig | None = None
) -> dict:
    """Write a run-manifest (provenance) next to the outputs. Returns it."""
    manifest = {
        **summary,
        "model": (config or TranscribeConfig()).model,
        "device": (config or TranscribeConfig()).device,
        "compute_type": (config or TranscribeConfig()).compute_type,
        "vad_method": (config or TranscribeConfig()).vad_method,
        "backend": (config or TranscribeConfig()).backend,
        "language": (config or TranscribeConfig()).language,
        "diarize": (config or TranscribeConfig()).diarize,
        "git_sha": _git_sha(),
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


def _build_record(
    vid: str,
    meta: dict,
    playlist_url: str,
    res: dict,
    timings: dict,
) -> VideoRecord:
    segments = res.get("segments", [])
    raw = " ".join(s.get("text", "") for s in segments).strip()
    align_status = res.get("align_status", "ok")
    return VideoRecord(
        video_id=vid,
        video_title=meta["video_title"],
        channel=meta["channel"],
        channel_id=meta["channel_id"],
        upload_date=meta["upload_date"],
        license=meta.get("license", ""),
        playlist_url=playlist_url,
        source_url=meta["source_url"],
        duration=meta["duration"],
        align_status=align_status,
        language=res.get("language", "ar"),
        transcript_raw=raw,
        transcript_norm=normalize_ar(raw),
        norm_version=NORM_VERSION,
        qa=qa_checks(
            duration=meta["duration"],
            raw=raw,
            segments=segments,
            word_segments=res.get("word_segments", []),
            align_status=align_status,
            diarize_status=res.get("diarize_status", ""),
            lid_status=res.get("lid_status", ""),
            lid_lang=res.get("lid_lang", ""),
            expected_lang=res.get("language", "ar"),
        ),
        qa_scores=qa_scores(
            duration=meta["duration"],
            raw=raw,
            segments=segments,
            word_segments=res.get("word_segments", []),
        ),
        diarize_status=res.get("diarize_status", ""),
        speakers=res.get("speakers", []),
        lid_status=res.get("lid_status", ""),
        lid_lang=res.get("lid_lang", ""),
        lid_confidence=float(res.get("lid_confidence", 0.0) or 0.0),
        timings=timings,
        segments=[
            {
                "start": s.get("start"),
                "end": s.get("end"),
                "text": s.get("text", ""),
                "words": s.get("words", []),
                **({"speaker": s["speaker"]} if s.get("speaker") else {}),
            }
            for s in segments
        ],
        word_segments=res.get("word_segments", []),
        model=res.get("model", ""),
    )


def process_video(
    url: str,
    playlist_url: str = "",
    keep_audio: bool = False,
    retries: int = 3,
    db_path: str = CHECKPOINT_DB,
    jsonl_path: str = OUTPUT_JSONL,
    ffmpeg_location: str | None = None,
    config: TranscribeConfig | None = None,
    session: TranscribeSession | None = None,
) -> VideoRecord | None:
    con = _db(db_path)
    # Checkpoint first: resume must not cost a network call. The URL-derived
    # id is authoritative; metadata only fills in the rest.
    vid = _video_id_from_url(url)
    if vid and _done(con, vid):
        log.info("skip %s (already ok)", vid)
        return None
    meta = extract_metadata(url)
    vid = meta["video_id"] or vid
    if _done(con, vid):
        log.info("skip %s (already ok)", vid)
        return None
    own_session = session is None
    if own_session:
        session = TranscribeSession(config)
    assert session is not None
    audio = ""
    owned = False  # only delete audio this attempt downloaded (never reused)
    t0 = time.time()
    try:
        for attempt in range(1, retries + 1):
            try:
                t_dl = time.time()
                audio, reused = download_audio(
                    url,
                    ffmpeg_location=ffmpeg_location,
                    expected_duration=meta.get("duration", 0),
                )
                owned = not reused
                dl_secs = time.time() - t_dl
                t_tr = time.time()
                res = session.transcribe(audio)
                tr_secs = time.time() - t_tr
                rec = _build_record(
                    vid,
                    meta,
                    playlist_url,
                    res,
                    timings={
                        "download_seconds": round(dl_secs, 1),
                        "transcribe_seconds": round(tr_secs, 1),
                        "total_seconds": round(time.time() - t0, 1),
                    },
                )
                _upsert_jsonl(jsonl_path, rec)
                _mark(con, vid, "ok")
                log.info(
                    "ok %s (%d segments, align=%s, qa=%s)",
                    vid,
                    len(rec.segments),
                    rec.align_status,
                    rec.qa or "clean",
                )
                return rec
            except Exception as e:  # noqa: BLE001
                log.exception("attempt %d/%d failed for %s", attempt, retries, vid)
                _mark(con, vid, "failed", str(e))
                time.sleep(2**attempt)
            finally:
                if audio and not keep_audio and owned:
                    Path(audio).unlink(missing_ok=True)
                    owned = False
    finally:
        if own_session:
            session.close()
    return None


def _prefetch_audio(url: str, ffmpeg_location: str | None) -> None:
    """Warm the audio cache for the next video (best-effort, errors ignored)."""
    try:
        download_audio(url, ffmpeg_location=ffmpeg_location)
    except Exception as e:  # noqa: BLE001
        log.debug("prefetch failed for %s: %s", url, e)


def process_playlist(
    playlist_url: str,
    keep_audio: bool = False,
    db_path: str = CHECKPOINT_DB,
    jsonl_path: str = OUTPUT_JSONL,
    ffmpeg_location: str | None = None,
    config: TranscribeConfig | None = None,
    manifest_path: str | None = None,
    max_videos: int = 0,
) -> dict:
    from concurrent.futures import ThreadPoolExecutor

    urls = get_playlist_video_urls(playlist_url)
    if max_videos and max_videos > 0:
        urls = urls[:max_videos]
    log.info("playlist: %d videos", len(urls))
    started = time.time()
    # One resident model for the whole playlist (loads ~4GB weights once).
    # Prefetch overlaps the next audio download with current GPU transcribe.
    ok = fail = 0
    con = _db(db_path)
    with (
        TranscribeSession(config) as session,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="prefetch") as pool,
    ):
        pending = None
        for i, url in enumerate(urls, 1):
            log.info("[%d/%d] %s", i, len(urls), url)
            if pending is not None:
                try:
                    pending.result()
                except Exception:  # noqa: BLE001
                    pass  # real attempt below retries with validation
                pending = None
            if i < len(urls):
                pending = pool.submit(_prefetch_audio, urls[i], ffmpeg_location)
            if _done(con, _video_id_from_url(url)):
                log.info("skip %s (already ok)", url)
                ok += 1
                continue
            rec = process_video(
                url,
                playlist_url,
                keep_audio,
                db_path=db_path,
                jsonl_path=jsonl_path,
                ffmpeg_location=ffmpeg_location,
                config=config,
                session=session,
            )
            ok += rec is not None
            fail += rec is None
            time.sleep(1.5)
    summary = {
        "playlist_url": playlist_url,
        "total": len(urls),
        "ok": ok,
        "failed": fail,
        "elapsed_seconds": round(time.time() - started, 1),
    }
    Path(jsonl_path).parent.mkdir(parents=True, exist_ok=True)
    with open(
        Path(jsonl_path).parent / "playlist_summary.json", "w", encoding="utf-8"
    ) as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    write_manifest(
        manifest_path or str(Path(jsonl_path).parent / "manifest.json"),
        summary,
        config,
    )
    return summary
