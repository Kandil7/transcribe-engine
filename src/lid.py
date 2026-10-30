"""Audio language identification (LID) on facebook/mms-lid-1024 (v2).

Heavy imports are deferred so the package imports and tests run without
transformers/torch. The model is Wav2Vec2ForSequenceClassification over
1024 languages; ``config.id2label`` maps the argmax class to ISO 639-3
codes (``ara``, ``eng``, ...). License CC-BY-NC-4.0 (research use).

Sampling: LID is reliable on short clips, so score at most ``max_seconds``
taken from the middle of the recording (intros/outros tend to be music
and titles). Pure helpers are unit-tested; only ``lid_audio`` touches
models/GPU.
"""

from __future__ import annotations

LID_MODEL = "facebook/mms-lid-1024"

# ISO 639-1 -> 639-3 for the codes this pipeline passes around ("ar").
# Unmapped codes fall back to direct string comparison in lid_mismatch.
_LANG_1_TO_3 = {
    "ar": "ara",
    "en": "eng",
    "fr": "fra",
    "de": "deu",
    "es": "spa",
    "tr": "tur",
    "fa": "fas",
    "ur": "urd",
    "hi": "hin",
    "zh": "cmn",
    "ru": "rus",
    "pt": "por",
    "id": "ind",
    "ms": "zlm",
    "sw": "swh",
}


def lid_codes_equal(requested: str, detected: str) -> bool:
    """Compare a requested language code with an MMS detection result."""
    if not requested or not detected:
        return True  # nothing to compare: never flag
    req = requested.lower()
    det = detected.lower()
    return req == det or _LANG_1_TO_3.get(req) == det


def clip_window(duration: float, max_seconds: float = 30.0) -> tuple[float, float]:
    """Middle window of ``max_seconds`` inside ``duration``.

    Returns (start, end) clamped to the recording; a recording shorter
    than ``max_seconds`` is scored whole.
    """
    if duration <= max_seconds:
        return 0.0, max(duration, 0.0)
    start = (duration - max_seconds) / 2.0
    return start, start + max_seconds


def lid_audio(
    audio_path: str,
    device: str = "cuda",
    model_id: str = LID_MODEL,
    max_seconds: float = 30.0,
) -> dict:
    """Identify the spoken language of an audio file.

    Returns {"lang": str, "confidence": float, "top": [(lang, p), ...]}.
    Raises on model/download errors — callers decide whether failure is
    fatal (the pipeline records ``lid_status="failed"`` and moves on).
    """
    import numpy as np
    import torch
    from transformers import AutoFeatureExtractor, Wav2Vec2ForSequenceClassification

    try:
        from .diarize import _load_audio_16k
        from .transcribe import load_local_first, resolve_cache_dir
    except ImportError:  # script-style execution
        from diarize import _load_audio_16k  # type: ignore
        from transcribe import load_local_first, resolve_cache_dir  # type: ignore

    cache_dir = resolve_cache_dir(model_id)

    def _load():
        proc = AutoFeatureExtractor.from_pretrained(model_id, cache_dir=cache_dir)
        mod = Wav2Vec2ForSequenceClassification.from_pretrained(
            model_id, cache_dir=cache_dir
        )
        return proc, mod

    processor, model = load_local_first(_load)
    model.to(torch.device(device))
    model.eval()

    sampling_rate = getattr(processor, "sampling_rate", None)
    if sampling_rate is None:  # Processor-style wrapper
        sampling_rate = processor.feature_extractor.sampling_rate
    audio = _load_audio_16k(audio_path, sampling_rate)
    duration = len(audio) / float(sampling_rate)
    t0, t1 = clip_window(duration, max_seconds)
    lo, hi = int(t0 * sampling_rate), int(t1 * sampling_rate)
    clip = np.asarray(audio[lo:hi], dtype=np.float32)
    if clip.size == 0:
        clip = np.asarray(audio, dtype=np.float32)

    inputs = processor(clip, sampling_rate=sampling_rate, return_tensors="pt").to(
        model.device
    )
    with torch.inference_mode():
        logits = model(**inputs).logits
    probs = logits.softmax(-1)[0]
    top = probs.topk(min(3, probs.shape[0]))
    labels = model.config.id2label
    top_pairs = [
        (labels.get(int(i), str(int(i))), float(p))
        for p, i in zip(top.values.tolist(), top.indices.tolist())
    ]
    return {
        "lang": top_pairs[0][0],
        "confidence": round(top_pairs[0][1], 3),
        "top": top_pairs,
    }
