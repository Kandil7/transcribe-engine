"""videos.jsonl reading — one implementation for all consumers.

The reader lived in three places (viewer, score_wer, and make_reference
via score_wer) with two behaviors. Here it lives once:

- ``load_records`` — tolerant: a missing file yields an empty list and
  blank lines are skipped (the viewer's behavior).
- ``load_video`` — strict: a missing file or unmatched video_id raises
  ``SystemExit`` with a message (the scorer's behavior).
"""

from __future__ import annotations

import json
from pathlib import Path


def load_records(jsonl_path: str | Path) -> list[dict]:
    """videos.jsonl -> list of record dicts (tolerant to blank lines)."""
    p = Path(jsonl_path)
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_video(jsonl_path: str | Path, video_id: str) -> dict:
    """videos.jsonl -> the one record with ``video_id``; raises if absent."""
    p = Path(jsonl_path)
    if not p.exists():
        raise SystemExit(f"missing {jsonl_path}")
    with p.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("video_id") == video_id:
                return d
    raise SystemExit(f"video_id {video_id} not found in {jsonl_path}")
