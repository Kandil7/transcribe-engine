"""Prefetch and verify the pipeline's models on local disk (v1).

Every model the pipeline can load is loaded LOCAL-FIRST here: cache-only
attempt, online download only on a genuine miss. Models are freed
between loads so this runs anywhere (cpu default) without VRAM juggling.

Usage: ``python -m src.cli prefetch [--device cpu]``
"""

from __future__ import annotations

import gc

PREFETCH_MODELS = ("asr", "aligner", "nemotron", "lid")


def _try_local_then_online(loader) -> str:
    """Load via ``loader()`` local-first; report 'local' or 'downloaded'."""
    try:
        from .transcribe import local_only
    except ImportError:  # script-style execution
        from transcribe import local_only  # type: ignore

    try:
        try:
            with local_only():
                loader()
            return "local"
        except Exception:  # noqa: BLE001 — any cache-miss error falls back online
            loader()
            return "downloaded"
    finally:
        gc.collect()


def _prefetch_one(name: str, device: str) -> str:
    return _try_local_then_online(lambda: _LOADERS[name](device))


def _run_worker(name: str, device: str) -> str:
    """Run one model's prefetch in a fresh process.

    Process isolation matters: freeing multi-GB weights in-process is
    lazy under Windows commit accounting (freed pages don't always
    return before the next model's mmap), so sequential in-process
    loads can fail with 'paging file too small' even though each model
    fits alone. A process exit reclaims commit deterministically.
    """
    import os
    import subprocess
    import sys

    env = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run(
        [sys.executable, "-m", "src.prefetch", "--one", name, "--device", device],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            _, res_name, status = line.split(None, 2)
            if res_name != name:
                raise RuntimeError(f"worker mismatch: {line!r}")
            return status
    raise RuntimeError(
        f"prefetch worker for {name} failed (rc={proc.returncode}):\n{proc.stderr[-2000:]}"
    )


def _load_asr(device: str):
    import coherex

    try:
        from .transcribe import AR_MODEL, resolve_cache_dir
    except ImportError:  # script-style execution
        from transcribe import AR_MODEL, resolve_cache_dir  # type: ignore

    m = coherex.load_model(
        model_name=AR_MODEL,
        device=device,
        compute_type="float32",
        vad_method="silero",
        batch_size=1,
        use_auth_token=None,
        download_root=resolve_cache_dir(AR_MODEL),
    )
    try:
        m.shutdown()
    except Exception:  # noqa: BLE001, S110 — best-effort cleanup on a verify path
        pass
    return m


def _load_aligner(device: str):
    import coherex

    try:
        from .transcribe import resolve_cache_dir
    except ImportError:  # script-style execution
        from transcribe import resolve_cache_dir  # type: ignore

    from coherex import alignment as _align

    align_id = getattr(_align, "DEFAULT_ALIGN_MODELS_HF", {}).get("ar") or getattr(
        _align, "DEFAULT_ALIGN_MODELS_TORCH", {}
    ).get("ar")
    return coherex.load_align_model(
        "ar", device=device, model_dir=resolve_cache_dir(align_id) if align_id else None
    )


def _load_nemotron(device: str):
    from transformers import AutoModelForAudioFrameClassification, AutoProcessor

    try:
        from .transcribe import resolve_cache_dir
    except ImportError:  # script-style execution
        from transcribe import resolve_cache_dir  # type: ignore

    model_id = "nvidia/Nemotron-3-Diarization"
    cache_dir = resolve_cache_dir(model_id)
    proc = AutoProcessor.from_pretrained(model_id, cache_dir=cache_dir)
    mod = AutoModelForAudioFrameClassification.from_pretrained(
        model_id, cache_dir=cache_dir
    )
    mod.to(device)
    return proc, mod


def _load_lid(device: str):
    from transformers import AutoFeatureExtractor, Wav2Vec2ForSequenceClassification

    try:
        from .transcribe import resolve_cache_dir
    except ImportError:  # script-style execution
        from transcribe import resolve_cache_dir  # type: ignore

    model_id = "facebook/mms-lid-1024"
    cache_dir = resolve_cache_dir(model_id)
    proc = AutoFeatureExtractor.from_pretrained(model_id, cache_dir=cache_dir)
    mod = Wav2Vec2ForSequenceClassification.from_pretrained(
        model_id, cache_dir=cache_dir
    )
    mod.to(device)
    return proc, mod


_LOADERS = {
    "asr": _load_asr,
    "aligner": _load_aligner,
    "nemotron": _load_nemotron,
    "lid": _load_lid,
}


def prefetch_models(device: str = "cpu") -> dict[str, str]:
    """Prefetch every pipeline model local-first; report per-model status.

    Each model runs in its own process (see ``_run_worker``) so its
    memory is fully reclaimed before the next loads. Returns
    ``{name: "local" | "downloaded"}``; raises on the first hard failure
    (that model needs attention before runs can trust it).
    """
    results: dict[str, str] = {}
    for name in PREFETCH_MODELS:
        results[name] = _run_worker(name, device)
    return results


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="prefetch worker (one model)")
    ap.add_argument("--one", required=True, choices=PREFETCH_MODELS)
    ap.add_argument("--device", default="cpu")
    ns = ap.parse_args()
    print(f"RESULT {ns.one} {_prefetch_one(ns.one, ns.device)}")
