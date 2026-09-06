"""cohereX wrapper (bakrianoo/cohereX Python API, transcript-only v1).

Heavy imports (coherex, torch) are deferred to call time so the package
imports and tests run without a GPU environment.

``TranscribeSession`` keeps the ASR + align models loaded across videos so
playlists pay the ~4GB weight load once instead of per video. ``transcribe_ar``
is a thin single-shot wrapper around it (backwards compatible).
"""

from __future__ import annotations

from dataclasses import dataclass

AR_MODEL = "CohereLabs/cohere-transcribe-arabic-07-2026"


@dataclass
class TranscribeConfig:
    """Knobs for one engine run (CLI builds this; sessions consume it)."""

    model: str = AR_MODEL
    device: str = "cuda"
    # Turing sm_75 (RTX 5000) has no bf16 tensor cores; coherex "default"
    # resolves to bfloat16 on cuda, so default to float16 here.
    compute_type: str = "float16"
    vad_method: str = "silero"
    batch_size: int = 8
    chunk_size: float = 30.0
    align: bool = True
    hf_token: str | None = None


def ensure_ffmpeg_on_path() -> str | None:
    """Make a `ffmpeg` binary discoverable for coherex subprocess calls.

    coherex.audio.load_audio hard-codes ``ffmpeg`` on PATH. On machines
    without a system ffmpeg (e.g. Windows + imageio-ffmpeg only), copy the
    resolved binary to ``data/bin/ffmpeg.exe`` and prepend it to PATH.
    Returns the ffmpeg path, or None if none could be found.
    """
    import os
    import shutil

    try:
        from .youtube import resolve_ffmpeg
    except ImportError:  # script-style execution
        from youtube import resolve_ffmpeg  # type: ignore

    exe = resolve_ffmpeg()
    if not exe or not os.path.exists(exe):
        return shutil.which("ffmpeg")
    # Only usable as-is when literally named ffmpeg(.exe), e.g. not the
    # imageio-ffmpeg `ffmpeg-win-x86_64-v7.1.exe` build.
    if os.path.basename(exe).lower() in ("ffmpeg", "ffmpeg.exe"):
        d = os.path.dirname(os.path.abspath(exe))
        if d not in os.environ.get("PATH", ""):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        return exe
    shim_dir = os.path.join("data", "bin")
    os.makedirs(shim_dir, exist_ok=True)
    shim = os.path.abspath(os.path.join(shim_dir, "ffmpeg.exe"))
    if not os.path.exists(shim):
        shutil.copyfile(exe, shim)
    d = os.path.dirname(shim)
    if d not in os.environ.get("PATH", ""):
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
    return shim


def _resolve_token(hf_token: str | None) -> str | None:
    import os

    tok = (
        hf_token
        or os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    )
    if tok:
        os.environ.setdefault("HF_TOKEN", tok)
        os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", tok)
    return tok


def _empty_cuda_cache(device: str) -> None:
    try:
        import torch

        if device == "cuda":
            torch.cuda.empty_cache()
    except Exception:
        pass


class TranscribeSession:
    """Long-lived ASR + align models for transcribing many videos.

    Use as a context manager (``with TranscribeSession(...) as s:``) or
    call :meth:`close` explicitly. Not thread-safe — one video at a time.
    VRAM need: ~4GB ASR fp16 + ~2GB aligner resident on cuda.
    """

    def __init__(self, config: TranscribeConfig | None = None, **kwargs) -> None:
        import logging

        self.log = logging.getLogger("transcribe-engine")
        self.config = config or TranscribeConfig(**kwargs)
        # coherex shells out to `ffmpeg` (load_audio + align); without it
        # every attempt dies with FileNotFoundError [WinError 2].
        ensure_ffmpeg_on_path()
        self.hf_token = _resolve_token(self.config.hf_token)
        self.asr = None
        self.align_model = None
        self.align_metadata = None
        self.align_lang = ""

    def open(self) -> "TranscribeSession":
        import coherex

        c = self.config
        if self.asr is None:
            self.asr = coherex.load_model(
                model_name=c.model,
                device=c.device,
                compute_type=c.compute_type,
                vad_method=c.vad_method,
                batch_size=c.batch_size,
                use_auth_token=self.hf_token,
            )
        return self

    def _ensure_align(self, language: str) -> bool:
        import coherex

        if self.align_model is not None and self.align_lang == language:
            return True
        self._drop_align()
        try:
            self.align_model, self.align_metadata = coherex.load_align_model(
                language, device=self.config.device
            )
            self.align_lang = language
            return True
        except Exception:
            self.log.exception("align model load failed for %r", language)
            return False

    def _drop_align(self) -> None:
        import gc

        self.align_model = None
        self.align_metadata = None
        self.align_lang = ""
        gc.collect()
        _empty_cuda_cache(self.config.device)

    def transcribe(self, audio_path: str, language: str = "ar") -> dict:
        """Run VAD → ASR → forced alignment for one audio file."""
        import gc
        import logging

        import coherex

        log = logging.getLogger("transcribe-engine")
        c = self.config
        self.open()
        try:
            result = self.asr.transcribe(
                audio_path,
                language=language,
                batch_size=c.batch_size,
                chunk_size=c.chunk_size,
            )
        except RuntimeError as e:
            # OOM fallback per ARCHITECTURE: batch 8 → 4 for this video.
            if "out of memory" not in str(e).lower() or c.batch_size <= 4:
                raise
            _empty_cuda_cache(c.device)
            log.warning(
                "OOM at batch=%d, retrying %s at batch=4", c.batch_size, audio_path
            )
            result = self.asr.transcribe(
                audio_path, language=language, batch_size=4, chunk_size=c.chunk_size
            )
        if c.align:
            if self._ensure_align(language):
                try:
                    result = coherex.align(
                        result["segments"],
                        self.align_model,
                        self.align_metadata,
                        audio_path,
                        c.device,
                    )
                    result["align_status"] = "ok"
                except Exception:
                    log.exception("alignment failed for %s", audio_path)
                    result["align_status"] = "segment_only"
                    result.setdefault("word_segments", [])
            else:
                result["align_status"] = "segment_only"
                result.setdefault("word_segments", [])
        else:
            result["align_status"] = "skipped"
            result.setdefault("word_segments", [])
        result["model"] = c.model
        gc.collect()
        return result

    def close(self) -> None:
        import gc

        if self.asr is not None:
            try:
                self.asr.shutdown()
            except Exception:
                pass
            self.asr = None
        self._drop_align()
        gc.collect()
        _empty_cuda_cache(self.config.device)

    def __enter__(self) -> "TranscribeSession":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()


def transcribe_ar(
    audio_path: str,
    language: str = "ar",
    model: str = AR_MODEL,
    device: str = "cuda",
    compute_type: str = "float16",
    vad_method: str = "silero",
    batch_size: int = 8,
    chunk_size: float = 30.0,
    hf_token: str | None = None,
    align: bool = True,
) -> dict:
    """Single-shot VAD → Cohere-AR ASR → forced alignment.

    Returns the cohereX result dict: {segments, word_segments, language}.
    Falls back to segment-level timestamps when Arabic alignment is
    unavailable (align_status=segment_only downstream).
    """
    cfg = TranscribeConfig(
        model=model,
        device=device,
        compute_type=compute_type,
        vad_method=vad_method,
        batch_size=batch_size,
        chunk_size=chunk_size,
        align=align,
        hf_token=hf_token,
    )
    with TranscribeSession(cfg) as session:
        return session.transcribe(audio_path, language=language)
