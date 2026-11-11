"""Hugging Face model-loading infrastructure (ADR 13/15).

Kept out of the engine module so every consumer (transcribe, diarize,
lid, dialect, prefetch) shares one implementation without reaching into
TranscribeSession's home:

- ``resolve_cache_dir`` — pick the cache root that actually holds a model
  (this machine's HF caches are split across two roots).
- ``local_only`` / ``load_local_first`` — cache-only before any network;
  online only on a genuine cache miss.
- ``resolve_token`` — HF_TOKEN / HUGGING_FACE_HUB_TOKEN resolution.
"""

from __future__ import annotations

from contextlib import contextmanager


def resolve_cache_dir(model_id: str) -> str | None:
    """Pick the HF cache root that actually holds ``model_id`` on this machine.

    Machine history can leave models split across two roots (e.g. HF_HOME
    vs HF_HOME/hub after an env change or a huggingface_hub upgrade that
    resolves the cache differently). The hub then re-downloads multi-GB
    weights that already exist in the other root or fails offline.

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


def resolve_token(hf_token: str | None) -> str | None:
    """Resolve the HF token (explicit arg, then env), exporting what wins."""
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
