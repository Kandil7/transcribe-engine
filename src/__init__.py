"""Transcribe Engine: Arabic YouTube transcription pipeline (v1 + v2).

Package layout:
- ``transcribe.py`` — ASR/align engine + TranscribeSession
- ``hub.py`` — HF model-loading infra (cache resolver, local-first)
- ``models.py`` — model repo ids (the single source of truth)
- ``audio_io.py`` — ffmpeg shim + waveform decoding
- ``diarize.py`` / ``lid.py`` / ``dialect.py`` — v2 annotation features
- ``qa.py`` — QA gates + numeric scores
- ``pipeline.py`` — orchestration (checkpoint, upsert, manifest, timings)
- ``schema.py`` — VideoRecord JSONL contract (+ EngineResult TypedDict)
- ``store.py`` — videos.jsonl readers (one implementation, all consumers)
- ``cli.py`` — video / playlist / prefetch / score / make-ref subcommands
- ``score_wer.py`` / ``make_reference.py`` / ``viewer.py`` — eval + browse tools
"""
