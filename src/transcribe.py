"""cohereX wrapper (bakrianoo/cohereX Python API, transcript-only v1).

Heavy imports (coherex, torch) are deferred to call time so the package
imports and tests run without a GPU environment.

``TranscribeSession`` keeps the ASR + align models loaded across videos so
playlists pay the ~4GB weight load once instead of per video. ``transcribe_ar``
is a thin single-shot wrapper around it (backwards compatible).
"""

from __future__ import annotations

from contextlib import contextmanager
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
    vad_method: str = "silero"  # silero | pyannote
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
    # Speaker diarization: annotates segments/words with speaker. Default
    # is the ungated Nemotron-3 (OpenMDW); pass a pyannote repo id to use
    # the gated pyannote pipeline instead.
    diarize: bool = False
    diarize_model: str = "nvidia/Nemotron-3-Diarization"
    # Audio LID (facebook/mms-lid-1024, CC-BY-NC): records the detected
    # language + confidence on each record; QA flags a mismatch with the
    # requested language. Model loads transiently per video.
    lid: bool = False
    lid_model: str = "facebook/mms-lid-1024"
    # Written-dialect tag (MARBERTv2, labels MAGHREB|LEV|MSA|GLF|EGY):
    # classifies the transcript text, records dialect + confidence.
    dialect: bool = False
    dialect_model: str = "IbrahimAmin/marbertv2-arabic-written-dialect-classifier"


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


def resolve_cache_dir(model_id: str) -> str | None:
    """Pick the HF cache root that actually holds ``model_id`` on this machine.

    Machine history can leave models split across two roots (e.g. HF_HOME
    vs HF_HOME/hub after an env change or a huggingface_hub upgrade that
    resolves the cache differently). The hub then re-downloads multi-GB
    weights that already exist in the other root — or fails offline.

    A root "holds" the model only by content, not by folder presence: a
    failed download leaves a stub directory with config files but no
    weights, and counting that as a holder would pick the wrong root.
    The root with strictly more cached bytes wins; ties or no hits
    return None so huggingface_hub uses its own default.
    """
    import os

    candidates: list[str] = []
    hub_cache = os.environ.get("HF_HUB_CACHE") or os.environ.get(
        "HUGGINGFACE_HUB_CACHE"
    )
    hf_home = os.environ.get("HF_HOME")
    if hub_cache:
        candidates.append(hub_cache)
    if hf_home:
        candidates.extend((hf_home, os.path.join(hf_home, "hub")))
    dirname = "models--" + model_id.replace("/", "--")
    scored: list[tuple[int, str]] = []
    for c in dict.fromkeys(candidates):
        d = os.path.join(c, dirname)
        if not os.path.isdir(d):
            continue
        size = sum(
            os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(d) for f in fs
        )
        scored.append((size, c))
    if not scored:
        return None
    scored.sort(reverse=True)
    if len(scored) == 1:
        return scored[0][1]
    return scored[0][1] if scored[0][0] > scored[1][0] else None


@contextmanager
def local_only():
    """Force huggingface_hub to serve from the local cache (no network).

    HF_HUB_OFFLINE=1 is honored by huggingface_hub and transformers and
    also by loaders that call them internally (coherex, pyannote), so
    one env switch makes any ``from_pretrained``-style load cache-only.
    """
    import os

    prev = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = prev


def load_local_first(loader, *args, **kwargs):
    """Call ``loader`` from the local cache first; fall back to online.

    Local-first kills the per-load HF API round-trips and the
    hub-re-downloads-what-exists class of bugs; the online retry only
    runs on a genuine cache miss and its error (if any) propagates.
    """
    try:
        with local_only():
            return loader(*args, **kwargs)
    except Exception:  # noqa: BLE001 — any cache-miss error falls back online
        return loader(*args, **kwargs)


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

    def transcribe(self, audio_path: str, language: str | None = None) -> dict:
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
        if c.diarize:
            self._apply_diarize(result, audio_path)
        if c.lid:
            self._apply_lid(result, audio_path)
        if c.dialect:
            self._apply_dialect(result)
        result["model"] = c.model
        gc.collect()
        return result

    def _apply_diarize(self, result: dict, audio_path: str) -> None:
        """Annotate segments/words with speakers; never fails the run."""
        try:
            try:
                from .diarize import assign_speakers, diarize_audio
            except ImportError:  # script-style execution
                from diarize import assign_speakers, diarize_audio  # type: ignore

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
            result["diarize_status"] = "ok"
        except Exception:
            self.log.exception("diarization failed for %s", audio_path)
            result["speakers"] = []
            result["diarize_status"] = "failed"

    def _apply_lid(self, result: dict, audio_path: str) -> None:
        """Record detected language + confidence; never fails the run.

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

        try:
            try:
                from .lid import lid_audio
            except ImportError:  # script-style execution
                from lid import lid_audio  # type: ignore

            def _run(device: str) -> dict:
                return lid_audio(
                    audio_path, device=device, model_id=self.config.lid_model
                )

            try:
                lid = _run(self.config.device)
            except (RuntimeError, OSError) as e:
                if not _mem_err(e):
                    raise
                self.log.warning(
                    "LID memory pressure on %s (%s); freeing finished models "
                    "and retrying",
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
            result["lid_status"] = "ok"
        except Exception:
            self.log.exception("LID failed for %s", audio_path)
            result["lid_lang"] = ""
            result["lid_confidence"] = 0.0
            result["lid_status"] = "failed"
        finally:
            gc.collect()
            _empty_cuda_cache(self.config.device)

    def _apply_dialect(self, result: dict) -> None:
        """Record written-dialect tag from the transcript; never fails.

        Text classification only (no audio, no model residency juggling):
        the MARBERTv2 classifier runs transiently on the transcript text.
        """
        import gc

        try:
            try:
                from .dialect import classify_dialect
            except ImportError:  # script-style execution
                from dialect import classify_dialect  # type: ignore

            text = " ".join(s.get("text", "") for s in result.get("segments", []))
            tag = classify_dialect(
                text, device=self.config.device, model_id=self.config.dialect_model
            )
            result["dialect"] = tag["dialect"]
            result["dialect_confidence"] = tag["confidence"]
            result["dialect_status"] = "ok"
        except Exception:
            self.log.exception("dialect tagging failed")
            result["dialect"] = ""
            result["dialect_confidence"] = 0.0
            result["dialect_status"] = "failed"
        finally:
            gc.collect()
            _empty_cuda_cache(self.config.device)

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
    backend: str = "local",
    vllm_url: str = "",
    vllm_api_key: str | None = None,
    vllm_args: str = "",
    diarize: bool = False,
    diarize_model: str = "nvidia/Nemotron-3-Diarization",
) -> dict:
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
