"""Contract tests: schema roundtrip, normalizer, JSONL→rows flatten."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jsonl_to_parquet import PARQUET_COLUMNS, jsonl_to_rows  # noqa: E402
from normalize_ar import normalize_ar  # noqa: E402
from schema import VideoRecord  # noqa: E402


def test_schema_roundtrip(tmp_path):
    rec = VideoRecord(
        video_id="abc123",
        video_title="محاضرة عن الذكاء الاصطناعي",
        channel="قناة التعليم",
        channel_id="UCxxx",
        playlist_url="https://youtube.com/playlist?list=PLxxx",
        transcript_raw="في هذه المحاضرة سنتحدث عن",
        align_status="ok",
        segments=[{"start": 0.5, "end": 4.2, "text": "في هذه المحاضرة"}],
        word_segments=[{"word": "في", "start": 0.5, "end": 0.8, "score": 0.9}],
    )
    line = rec.to_jsonl()
    back = VideoRecord.from_jsonl(line)
    assert back.video_id == "abc123"
    assert back.playlist_url.endswith("PLxxx")
    assert back.segments[0]["start"] == 0.5


def test_normalize_ar():
    assert normalize_ar("آلأإٱ ؤ ئ ء") != ""
    assert "ـ" not in normalize_ar("مـرحـبـا")
    assert normalize_ar("سنة ٢٠٢٦") == normalize_ar("سنة 2026").replace("ه", "ه")
    assert "٢٠٢٦" not in normalize_ar("عام ٢٠٢٦")


def test_jsonl_to_rows_flattens_segments(tmp_path):
    p = tmp_path / "videos.jsonl"
    p.write_text(
        json.dumps(
            {
                "video_id": "v1",
                "video_title": "t",
                "channel": "c",
                "channel_id": "UC1",
                "upload_date": "2026-01-15",
                "playlist_url": "PL1",
                "align_status": "segment_only",
                "model": "m",
                "segments": [
                    {"start": 0.0, "end": 2.0, "text": "مرحبا بكم"},
                    {"start": 2.0, "end": 4.0, "text": "في المحاضرة", "words": []},
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    rows = jsonl_to_rows(p)
    assert len(rows) == 2
    assert set(rows[0]) == set(PARQUET_COLUMNS)
    assert rows[0]["playlist_url"] == "PL1"
    assert rows[0]["channel"] == "c"
    assert rows[0]["word_count"] == 2
