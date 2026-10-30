"""Offline pipeline tests with mocked network/GPU boundaries."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pipeline  # noqa: E402
from schema import VideoRecord  # noqa: E402


META = {
    "video_id": "VID12345678",
    "video_title": "t",
    "channel": "c",
    "channel_id": "UC1",
    "upload_date": "2026-01-01",
    "license": "Creative Commons",
    "playlist_url": "",
    "source_url": "https://www.youtube.com/watch?v=VID12345678",
    "duration": 60.0,
}

RES = {
    "segments": [{"start": 0.0, "end": 58.0, "text": "مرحبا", "words": []}],
    "word_segments": [{"word": "مرحبا", "start": 0.0, "end": 1.0, "score": 0.9}],
    "align_status": "ok",
    "model": "m",
}


class FakeSession:
    """Stand-in for TranscribeSession (no GPU)."""

    def __init__(self, fail_first=0):
        self.calls = 0
        self.fail_first = fail_first
        self.closed = False

    def transcribe(self, audio):
        self.calls += 1
        if self.calls <= self.fail_first:
            raise RuntimeError("boom")
        return dict(RES)

    def close(self):
        self.closed = True


def _wire(monkeypatch, tmp_path, fail_first=0):
    def fake_meta(url):
        return dict(META)

    def fake_dl(url, ffmpeg_location=None, expected_duration=0):
        wav = tmp_path / "a.wav"
        wav.write_bytes(b"x" * 2048)
        return str(wav), True

    monkeypatch.setattr(pipeline, "extract_metadata", fake_meta)
    monkeypatch.setattr(pipeline, "download_audio", fake_dl)
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)
    return FakeSession(fail_first=fail_first)


def test_process_video_success_and_checkpoint(monkeypatch, tmp_path):
    session = _wire(monkeypatch, tmp_path)
    db = str(tmp_path / "c.db")
    jl = str(tmp_path / "v.jsonl")
    rec = pipeline.process_video(
        "https://www.youtube.com/watch?v=VID12345678",
        db_path=db,
        jsonl_path=jl,
        session=session,
    )
    assert rec is not None
    assert rec.video_id == "VID12345678"
    assert rec.license == "Creative Commons"
    assert rec.norm_version == "v1"
    assert rec.qa == []
    assert rec.timings["transcribe_seconds"] >= 0
    assert pipeline._done(pipeline._db(db), "VID12345678")
    lines = Path(jl).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_process_video_retry_then_ok(monkeypatch, tmp_path):
    session = _wire(monkeypatch, tmp_path, fail_first=1)
    rec = pipeline.process_video(
        "https://www.youtube.com/watch?v=VID12345678",
        db_path=str(tmp_path / "c.db"),
        jsonl_path=str(tmp_path / "v.jsonl"),
        session=session,
    )
    assert rec is not None
    assert session.calls == 2


def test_process_video_skips_before_network(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path)
    db = str(tmp_path / "c.db")
    con = pipeline._db(db)
    pipeline._mark(con, "VID12345678", "ok")

    def boom(url):
        raise AssertionError("metadata must not be fetched on resume")

    monkeypatch.setattr(pipeline, "extract_metadata", boom)
    rec = pipeline.process_video(
        "https://www.youtube.com/watch?v=VID12345678",
        db_path=db,
        jsonl_path=str(tmp_path / "v.jsonl"),
    )
    assert rec is None


def test_process_video_diarize_flow(monkeypatch, tmp_path):
    class DiarizedSession(FakeSession):
        def transcribe(self, audio):
            res = dict(RES)
            res["segments"] = [
                {
                    "start": 0.0,
                    "end": 5.0,
                    "text": "أ",
                    "words": [],
                    "speaker": "SPEAKER_00",
                },
                {
                    "start": 5.0,
                    "end": 58.0,
                    "text": "ب",
                    "words": [],
                    "speaker": "SPEAKER_01",
                },
            ]
            res["word_segments"] = [
                {
                    "word": "أ",
                    "start": 0.0,
                    "end": 1.0,
                    "score": 0.9,
                    "speaker": "SPEAKER_00",
                }
            ]
            res["speakers"] = ["SPEAKER_00", "SPEAKER_01"]
            res["diarize_status"] = "ok"
            return res

    session = _wire(monkeypatch, tmp_path)
    dsession = DiarizedSession()
    dsession.calls = 0
    rec = pipeline.process_video(
        "https://www.youtube.com/watch?v=VID12345678",
        db_path=str(tmp_path / "c.db"),
        jsonl_path=str(tmp_path / "v.jsonl"),
        session=dsession,
    )
    assert rec.speakers == ["SPEAKER_00", "SPEAKER_01"]
    assert rec.diarize_status == "ok"
    assert rec.segments[0]["speaker"] == "SPEAKER_00"  # speaker survives projection
    assert rec.qa == []  # ok diarization adds no flag


def test_process_video_diarize_failed_flag(monkeypatch, tmp_path):
    class FailedDiarizeSession(FakeSession):
        def transcribe(self, audio):
            res = dict(RES)
            res["speakers"] = []
            res["diarize_status"] = "failed"
            return res

    session = _wire(monkeypatch, tmp_path)
    fs = FailedDiarizeSession()
    fs.calls = 0
    rec = pipeline.process_video(
        "https://www.youtube.com/watch?v=VID12345678",
        db_path=str(tmp_path / "c.db"),
        jsonl_path=str(tmp_path / "v.jsonl"),
        session=fs,
    )
    assert rec.diarize_status == "failed"
    assert "diarize_failed" in rec.qa


def test_process_video_record_language(monkeypatch, tmp_path):
    class LangSession(FakeSession):
        def transcribe(self, audio):
            res = dict(RES)
            res["language"] = "ar"
            return res

    _wire(monkeypatch, tmp_path)
    ls = LangSession()
    ls.calls = 0
    rec = pipeline.process_video(
        "https://www.youtube.com/watch?v=VID12345678",
        db_path=str(tmp_path / "c.db"),
        jsonl_path=str(tmp_path / "v.jsonl"),
        session=ls,
    )
    assert rec.language == "ar"  # engine-reported language lands on the record


def test_upsert_jsonl_is_idempotent(tmp_path):
    jl = str(tmp_path / "v.jsonl")
    rec = VideoRecord(video_id="A", video_title="t")
    pipeline._upsert_jsonl(jl, rec)
    pipeline._upsert_jsonl(jl, rec)
    lines = [
        ln for ln in Path(jl).read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    assert len(lines) == 1
    assert json.loads(lines[0])["video_id"] == "A"
    rec2 = VideoRecord(video_id="B", video_title="t2")
    pipeline._upsert_jsonl(jl, rec2)
    assert len(Path(jl).read_text(encoding="utf-8").splitlines()) == 2


def test_write_manifest(tmp_path):
    m = pipeline.write_manifest(
        str(tmp_path / "manifest.json"), {"ok": 1, "total": 1}, None
    )
    assert m["ok"] == 1
    assert "finished_at" in m and "model" in m
