"""cohereX wrapper (bakrianoo/cohereX Python API, transcript-only v1).

Heavy imports (coherex, torch) are deferred to call time so the package
imports and tests run without a GPU environment.
"""

from __future__ import annotations

AR_MODEL = "CohereLabs/cohere-transcribe-arabic-07-2026"


def transcribe_ar(
    audio_path: str,
    language: str = "ar",
    model: str = AR_MODEL,
    device: str = "cuda",
    compute_type: str = "bfloat16",
    vad_method: str = "silero",
    batch_size: int = 8,
    chunk_size: float = 30.0,
    hf_token: str | None = None,
) -> dict:
    """Run VAD → Cohere-AR ASR → forced alignment.

    Returns the cohereX result dict: {segments, word_segments, language}.
    Falls back to segment-level timestamps when Arabic alignment is
    unavailable (align_status=segment_only downstream).
    """
    import coherex

    if hf_token:
        import os

        os.environ.setdefault("HF_TOKEN", hf_token)
        os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", hf_token)

    asr = coherex.load_model(
        model_name=model,
        device=device,
        compute_type=compute_type,
        vad_method=vad_method,
    )
    result = asr.transcribe(audio_path, language=language, batch_size=batch_size)
    try:
        align_model, metadata = coherex.load_align_model(language, device=device)
        result = coherex.align(
            result["segments"], align_model, metadata, audio_path, device
        )
        result["align_status"] = "ok"
    except Exception:
        result["align_status"] = "segment_only"
        result.setdefault("word_segments", [])
    result["model"] = model
    return result
