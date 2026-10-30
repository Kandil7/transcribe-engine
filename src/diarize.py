"""Speaker diarization (v2 feature): Nemotron-3 (default) or pyannote.

Heavy imports are deferred so the package imports and tests run without
the model stacks installed. Annotation is pure and unit-tested; only the
``diarize_*`` functions touch models/GPU.

Backends:
- ``nemotron``: ``nvidia/Nemotron-3-Diarization`` via transformers
  (OpenMDW license, ungated, 99.2M params, beats the pyannote baseline on
  every published DER benchmark). Output channels are arrival-ordered.
- ``pyannote``: ``pyannote/speaker-diarization-community-1`` pipeline
  (gated on HF).
"""

from __future__ import annotations

from dataclasses import dataclass

NEMOTRON_MODEL = "nvidia/Nemotron-3-Diarization"
PYANNOTE_MODEL = "pyannote/speaker-diarization-community-1"
DIARIZE_MODEL = NEMOTRON_MODEL


@dataclass
class Turn:
    start: float
    end: float
    speaker: str


def _load_audio_16k(path: str, sampling_rate: int = 16000):
    """Decode audio to a float32 mono waveform via the ffmpeg CLI.

    transformers.audio_utils.load_audio needs torchcodec + shared-FFmpeg
    DLLs; the pipeline already standardizes on a plain ffmpeg CLI
    (coherex does the same), so decode through it: ffmpeg -i <path> -f
    f32le -ac 1 -ar <rate> pipe:1
    """
    import subprocess

    import numpy as np

    try:
        from .transcribe import ensure_ffmpeg_on_path
    except ImportError:  # script-style execution
        from transcribe import ensure_ffmpeg_on_path  # type: ignore

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


def diarize_audio(
    audio_path: str,
    device: str = "cuda",
    hf_token: str | None = None,
    model_id: str = DIARIZE_MODEL,
    num_speakers: int | None = None,
) -> list[dict]:
    """Run diarization; return [{start, end, speaker}] turns sorted by start.

    Dispatches on ``model_id`` (``nemotron`` → Nemotron-3 backend, else
    pyannote). Raises on model/download errors — callers decide whether
    failure is fatal (the pipeline records ``diarize_status="failed"``
    and moves on).
    """
    if "nemotron" in model_id.lower():
        return diarize_nemotron(
            audio_path, device=device, hf_token=hf_token, model_id=model_id
        )
    return diarize_pyannote(
        audio_path,
        device=device,
        hf_token=hf_token,
        model_id=model_id,
        num_speakers=num_speakers,
    )


def diarize_nemotron(
    audio_path: str,
    device: str = "cuda",
    hf_token: str | None = None,
    model_id: str = NEMOTRON_MODEL,
) -> list[dict]:
    """Nemotron-3 (transformers) offline diarization.

    Per-frame logits (10ms) are post-processed by the model's own
    ``processor.extract_speaker_dict``; channels are arrival-ordered, so
    labels map straight to SPEAKER_00..SPEAKER_07 by first appearance.
    """
    import torch
    from transformers import AutoModelForAudioFrameClassification, AutoProcessor

    try:
        from .transcribe import load_local_first, resolve_cache_dir
    except ImportError:  # script-style execution
        from transcribe import load_local_first, resolve_cache_dir  # type: ignore

    cache_dir = resolve_cache_dir(model_id)

    def _load():
        proc = AutoProcessor.from_pretrained(
            model_id, cache_dir=cache_dir, token=hf_token
        )
        mod = AutoModelForAudioFrameClassification.from_pretrained(
            model_id, cache_dir=cache_dir, token=hf_token
        )
        return proc, mod

    processor, model = load_local_first(_load)
    model.to(torch.device(device))
    model.eval()

    sampling_rate = processor.feature_extractor.sampling_rate
    audio = _load_audio_16k(audio_path, sampling_rate)
    inputs = processor(audio, sampling_rate=sampling_rate).to(
        model.device, dtype=model.dtype
    )
    with torch.inference_mode():
        logits = model(**inputs).logits  # (1, num_frames, 8), one frame / 10ms
    raw = processor.extract_speaker_dict(logits, inputs.attention_mask)[0]
    turns = [
        {
            "start": float(s["Start"]),
            "end": float(s["End"]),
            "speaker": f"SPEAKER_{int(s['Speaker']):02d}",
        }
        for s in raw
    ]
    turns.sort(key=lambda t: t["start"])
    return turns


def diarize_pyannote(
    audio_path: str,
    device: str = "cuda",
    hf_token: str | None = None,
    model_id: str = PYANNOTE_MODEL,
    num_speakers: int | None = None,
) -> list[dict]:
    """pyannote.audio pipeline diarization (gated model).

    Raises on model/gating errors — callers decide whether failure is
    fatal (the pipeline records ``diarize_status="failed"`` and moves on).
    """
    import torch
    from pyannote.audio import Pipeline

    try:
        from .transcribe import load_local_first
    except ImportError:  # script-style execution
        from transcribe import load_local_first  # type: ignore

    pipeline = load_local_first(Pipeline.from_pretrained, model_id, token=hf_token)
    pipeline.to(torch.device(device))
    kwargs = {}
    if num_speakers:
        kwargs["num_speakers"] = num_speakers
    diarization = pipeline(audio_path, **kwargs)
    turns = [
        {"start": float(seg.start), "end": float(seg.end), "speaker": str(label)}
        for seg, _, label in diarization.itertracks(yield_label=True)
    ]
    turns.sort(key=lambda t: t["start"])
    return turns


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def assign_speakers(
    segments: list[dict],
    word_segments: list[dict],
    turns: list[dict],
) -> tuple[list[dict], list[dict], list[str]]:
    """Annotate segments and words with ``speaker`` by max time overlap.

    Pure: mutates copies. An interval with no overlapping turn keeps an
    empty speaker string. Returns (segments, word_segments, speakers)
    where speakers is the sorted set of labels seen.
    """
    segs = [dict(s) for s in segments]
    words = [dict(w) for w in word_segments]
    if not turns:
        return segs, words, []

    def best_speaker(start: float, end: float) -> str:
        best, best_ov = "", 0.0
        for t in turns:
            ov = _overlap(start, end, t["start"], t["end"])
            if ov > best_ov:
                best, best_ov = t["speaker"], ov
        return best

    speakers = set()
    for s in segs:
        sp = best_speaker(float(s.get("start", 0) or 0), float(s.get("end", 0) or 0))
        s["speaker"] = sp
        if sp:
            speakers.add(sp)
        inner = s.get("words") or []
        if inner:
            annotated = []
            for w in inner:
                w2 = dict(w) if isinstance(w, dict) else w
                if isinstance(w2, dict):
                    wsp = best_speaker(
                        float(w2.get("start", 0) or 0), float(w2.get("end", 0) or 0)
                    )
                    w2["speaker"] = wsp
                    if wsp:
                        speakers.add(wsp)
                annotated.append(w2)
            s["words"] = annotated
    for w in words:
        sp = best_speaker(float(w.get("start", 0) or 0), float(w.get("end", 0) or 0))
        w["speaker"] = sp
        if sp:
            speakers.add(sp)
    return segs, words, sorted(speakers)
