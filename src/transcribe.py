"""cohereX ASR engine wrapper (v1 core).

Heavy imports (coherex, torch) are deferred to call time so the package
imports and tests run without a GPU environment.

``TranscribeSession`` keeps the ASR + align models loaded across videos so
playlists pay the ~4GB weight load once instead of per video. ``transcribe_ar``
is a thin single-shot wrapper around it (backwards compatible).

Model-loading infrastructure lives in ``hub.py`` (cache resolver,
local-first loading, offline context, token); audio decoding lives in
``audio_io.py``; model repo ids live in ``models.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .audio_io import ensure_ffmpeg_on_path
from .hub import load_local_first, resolve_cache_dir, resolve_token
from .models import AR_MODEL, DIALECT_MODEL, DIARIZE_MODEL, LID_MODEL

if TYPE_CHECKING:
    from .schema import EngineResult


@dataclass
class TranscribeConfig:
    """Knobs for one engine run (CLI builds this; sessions consume it)."""

    model: str = AR_MODEL
    device: str = "cuda"
    # Turing sm_75 (RTX 5000) has no bf16 tensor cores; coherex "default"
    # resolves to bfloat16 on cuda, so default to float16 here.
    compute_type: str = "float16"
    vad_method: str = "silero"  # silero only (pyannote VAD removed, ADR 18)
    batch_size: int = 8
    chunk_size: float = 30.0
    align: bool = True
    hf_token: str | None = None
    # Explicit language code ("ar" default). Cohere Transcribe performs no
    # LID (coherex raises on language=None), so auto-detect needs an
    # external model — see ROADMAP item 8.
    language: str = "ar"
    # Engine backend: "local" in-process, or "vllm" to offload transcription
    # to a vLLM server (coherex starts one itself when vllm_url is empty).
    backend: str = "local"
    vllm_url: str = ""
    vllm_api_key: str | None = None
    vllm_args: str = ""  # extra `vllm serve` args, shell-style split
    # Speaker diarization: annotates segments/words with speaker. Nemotron-3
    # (OpenMDW, ungated) is the sole backend since ADR 18 (pyannote removed).
    diarize: bool = False
    diarize_model: str = DIARIZE_MODEL
    # Audio LID: records the detected language + confidence on each record;
    # QA flags a mismatch with the requested language. Loads transiently.
    lid: bool = False
    lid_model: str = LID_MODEL
    # Written-dialect tag (MARBERTv2, labels MAGHREB|LEV|MSA|GLF|EGY):
    # classifies the transcript text, records dialect + confidence.
    dialect: bool = False
    dialect_model: str = DIALECT_MODEL


def _empty_cuda_cache(device: str) -> None:
    try:
        import torch

        if device == "cuda":
            torch.cuda.empty_cache()
    except Exception:
        pass


# Per-stage keys to reset on failure (never-fail contract: the run
# continues with the stage's neutral values, never a crash).
_STAGE_RESET = {
    "diarize": {"speakers": []},
    "lid": {"lid_lang": "", "lid_confidence": 0.0},
    "dialect": {"dialect": "", "dialect_confidence": 0.0},
}


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
        self.hf_token = resolve_token(self.config.hf_token)
        self.asr = None
        self.align_model = None
        self.align_metadata = None
        self.align_lang = ""

    def open(self) -> TranscribeSession:
        import shlex

        import coherex

        c = self.config
        if self.asr is None:
            self.asr = load_local_first(
                coherex.load_model,
                model_name=c.model,
                device=c.device,
                compute_type=c.compute_type,
                vad_method=c.vad_method,
                batch_size=c.batch_size,
                use_auth_token=self.hf_token,
                download_root=resolve_cache_dir(c.model),
                backend=c.backend,
                vllm_url=c.vllm_url or None,
                vllm_api_key=c.vllm_api_key,
                vllm_args=shlex.split(c.vllm_args) if c.vllm_args else None,
            )
        return self

    def _ensure_align(self, language: str) -> bool:
        import coherex

        if self.align_model is not None and self.align_lang == language:
            return True
        self._drop_align()
        try:
            from coherex import alignment as _align

            align_id = getattr(_align, "DEFAULT_ALIGN_MODELS_TORCH", {}).get(
                language
            ) or getattr(_align, "DEFAULT_ALIGN_MODELS_HF", {}).get(language)
            self.align_model, self.align_metadata = load_local_first(
                coherex.load_align_model,
                language,
                device=self.config.device,
                model_dir=resolve_cache_dir(align_id) if align_id else None,
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

    def transcribe(self, audio_path: str, language: str | None = None) -> EngineResult:
        """Run VAD → ASR → forced alignment for one audio file."""
        import gc
        import logging

        import coherex

        log = logging.getLogger("transcribe-engine")
        c = self.config
        language = language or c.language
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
        for name, cleanup in (
            ("diarize", False),
            ("lid", True),
            ("dialect", True),
        ):
            self._stage(name, result, getattr(self, f"_do_{name}"), audio_path, cleanup)
        result["model"] = c.model
        gc.collect()
        return result

    def _stage(
        self, name: str, result: dict, fn, audio_path: str, cleanup: bool = False
    ) -> None:
        """Run one annotation stage; never let it fail the run.

        The triplicated try/except/log/reset of ``_apply_diarize`` /
        ``_apply_lid`` / ``_apply_dialect`` collapsed here: each stage's
        success path lives in ``_do_<name>``, and this wrapper owns the
        never-fail contract — record the status, reset the stage's keys,
        log the traceback, and (optionally) free GPU memory.
        """
        try:
            fn(result, audio_path)
            result[f"{name}_status"] = "ok"
        except Exception:
            self.log.exception("%s failed for %s", name, audio_path)
            result[f"{name}_status"] = "failed"
            result.update(_STAGE_RESET[name])
        finally:
            if cleanup:
                import gc

                gc.collect()
                _empty_cuda_cache(self.config.device)

    def _do_diarize(self, result: dict, audio_path: str) -> None:
        """Annotate segments/words with speakers (Nemotron-3 turns)."""
        from .diarize import assign_speakers, diarize_audio

        turns = diarize_audio(
            audio_path,
            device=self.config.device,
            hf_token=self.hf_token,
            model_id=self.config.diarize_model,
        )
        segs, words, speakers = assign_speakers(
            result.get("segments", []), result.get("word_segments", []), turns
        )
        result["segments"] = segs
        result["word_segments"] = words
        result["speakers"] = speakers

    def _do_lid(self, result: dict, audio_path: str) -> None:
        """Set lid_lang/lid_confidence on the result.

        The LID model is transient (loaded, used, dropped) so it never
        competes with ASR/aligner VRAM across a playlist. Its ~2.5GB
        safetensors is mmap'd at load, charging Windows commit on top of
        the resident ASR+aligner — on commit exhaustion free the models
        whose work is done for this video (aligner: already aligned;
        ASR: `open()` reloads lazily per video) and retry before failing.
        """
        import gc

        def _mem_err(e: BaseException) -> bool:
            msg = str(e).lower()
            return "out of memory" in msg or "paging file" in msg or "error 1455" in msg

        def _run(device: str) -> dict:
            from .lid import lid_audio

            return lid_audio(audio_path, device=device, model_id=self.config.lid_model)

        try:
            lid = _run(self.config.device)
        except (RuntimeError, OSError) as e:
            if not _mem_err(e):
                raise
            self.log.warning(
                "LID memory pressure on %s (%s); freeing finished models and retrying",
                self.config.device,
                e,
            )
            self._drop_align()
            if self.asr is not None:
                try:
                    self.asr.shutdown()
                except Exception:
                    pass
                self.asr = None
            gc.collect()
            _empty_cuda_cache(self.config.device)
            try:
                lid = _run(self.config.device)
            except (RuntimeError, OSError) as e2:
                if not _mem_err(e2):
                    raise
                self.log.warning("LID still OOM; final retry on cpu")
                lid = _run("cpu")
        result["lid_lang"] = lid["lang"]
        result["lid_confidence"] = lid["confidence"]

    def _do_dialect(self, result: dict, audio_path: str) -> None:
        """Set dialect/dialect_confidence from the transcript text."""
        from .dialect import classify_dialect

        text = " ".join(s.get("text", "") for s in result.get("segments", []))
        tag = classify_dialect(
            text, device=self.config.device, model_id=self.config.dialect_model
        )
        result["dialect"] = tag["dialect"]
        result["dialect_confidence"] = tag["confidence"]

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

    def __enter__(self) -> TranscribeSession:
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
    backend: str = "local",
    vllm_url: str = "",
    vllm_api_key: str | None = None,
    vllm_args: str = "",
    diarize: bool = False,
    diarize_model: str = DIARIZE_MODEL,
) -> EngineResult:
    """Single-shot VAD → Cohere-AR ASR → forced alignment (+ optional diarization).

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
        language=language,
        backend=backend,
        vllm_url=vllm_url,
        vllm_api_key=vllm_api_key,
        vllm_args=vllm_args,
        diarize=diarize,
        diarize_model=diarize_model,
    )
    with TranscribeSession(cfg) as session:
        return session.transcribe(audio_path, language=language)
