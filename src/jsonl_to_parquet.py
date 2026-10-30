"""Flatten videos.jsonl segments to segments.parquet (v1).

One row per segment (not per video, not per word). Words stay in JSONL.
Writer preference: polars → pandas → csv fallback (last resort).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

PARQUET_COLUMNS = [
    "video_id",
    "video_title",
    "channel",
    "channel_id",
    "upload_date",
    "playlist_url",
    "start",
    "end",
    "text_raw",
    "text_norm",
    "word_count",
    "align_status",
    "speaker",
    "model",
]


def jsonl_to_rows(jsonl_path: str | Path) -> list[dict]:
    """Pure-stdlib flatten: JSONL lines → segment row dicts.

    A missing/empty JSONL (e.g. every video failed) yields zero rows instead
    of raising, so `--to-parquet` still writes a valid empty table.
    """
    if not Path(jsonl_path).exists():
        return []
    try:
        from .normalize_ar import normalize_ar
    except ImportError:  # loaded as top-level module (tests, scripts)
        from normalize_ar import normalize_ar

    rows: list[dict] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            for seg in d.get("segments", []):
                text_raw = seg.get("text", "")
                words = seg.get("words", [])
                rows.append(
                    {
                        "video_id": d.get("video_id", ""),
                        "video_title": d.get("video_title", ""),
                        "channel": d.get("channel", ""),
                        "channel_id": d.get("channel_id", ""),
                        "upload_date": d.get("upload_date", ""),
                        "playlist_url": d.get("playlist_url", ""),
                        "start": float(seg.get("start", 0.0)),
                        "end": float(seg.get("end", 0.0)),
                        "text_raw": text_raw,
                        "text_norm": normalize_ar(text_raw),
                        "word_count": len(words) if words else len(text_raw.split()),
                        "align_status": d.get("align_status", "ok"),
                        "speaker": seg.get("speaker", ""),
                        "model": d.get("model", ""),
                    }
                )
    return rows


def coerce_rows(rows: list[dict]) -> list[dict]:
    """Project every row onto PARQUET_COLUMNS (drop extras, fill missing).

    Guards the writers against malformed upstream dicts: a missing column
    becomes None instead of a polars/pandas schema error.
    """
    return [{c: r.get(c) for c in PARQUET_COLUMNS} for r in rows]


def write_parquet(rows: list[dict], out_path: str | Path) -> str:
    """Write rows to parquet (polars → pandas) or csv fallback.

    Returns the path actually written.
    """
    rows = coerce_rows(rows)
    out = Path(out_path)
    if not rows:
        # Empty playlist/failure: write an empty table with the right schema,
        # not a dummy row.
        try:
            import polars as pl

            pl.DataFrame({c: [] for c in PARQUET_COLUMNS}).write_parquet(out)
            return str(out)
        except ImportError:
            pass
        try:
            import pandas as pd

            pd.DataFrame([], columns=PARQUET_COLUMNS).to_parquet(out, index=False)
            return str(out)
        except ImportError:
            pass
        csv_path = out.with_suffix(".csv")
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=PARQUET_COLUMNS)
            w.writeheader()
        return str(csv_path)
    try:
        import polars as pl

        pl.DataFrame(rows, schema=PARQUET_COLUMNS).write_parquet(out)
        return str(out)
    except ImportError:
        pass
    try:
        import pandas as pd

        pd.DataFrame(rows, columns=PARQUET_COLUMNS).to_parquet(out, index=False)
        return str(out)
    except ImportError:
        pass
    csv_path = out.with_suffix(".csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PARQUET_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return str(csv_path)


def main(jsonl_path: str, out_path: str) -> str:
    rows = jsonl_to_rows(jsonl_path)
    written = write_parquet(rows, out_path)
    print(f"rows={len(rows)} written={written}")
    return written


if __name__ == "__main__":
    import sys

    main(sys.argv[1], sys.argv[2])
