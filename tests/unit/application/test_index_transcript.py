"""S18 AC-5 (unit): re-indexing a transcript embeds only the text that is new.

The fake embedder counts the texts it is asked to embed. Positive control: the first index embeds
every chunk; an edit to the last sentences embeds some chunks but not all.
"""

import importlib
from dataclasses import replace
from types import ModuleType
from typing import Any

from tests.fakes.embedder import FakeEmbedder
from tests.fakes.search_index import FakeSearchIndex


def _mod(name: str) -> ModuleType:
    return importlib.import_module(name)


def _transcript(edit_tail: bool = False, version: int = 1) -> Any:
    merge = _mod("transcribe_engine.domain.merge")
    transcript = _mod("transcribe_engine.domain.transcript")
    texts = [f"w{i}." if (i + 1) % 10 == 0 else f"w{i}" for i in range(1000)]
    if edit_tail:
        texts = [t if i < 980 else t.replace("w", "x") for i, t in enumerate(texts)]
    words = tuple(merge.Word(t, i * 400, i * 400 + 350, None, i // 50) for i, t in enumerate(texts))
    merged = merge.MergedWords(words=words, sample_rate=16_000)
    provenance = transcript.Provenance(
        engine="whisper-local", revision="rev", pipeline_version="1.0.0", config_hash="c" * 64
    )
    built = transcript.transcript_from_merged(
        merged, transcript_id="job-s18", media_id="media-s18", language="ar", provenance=provenance
    )
    return replace(built, version=version)


async def test_reindex_skips_unchanged() -> None:
    index_mod = _mod("transcribe_engine.application.use_cases.index_transcript")
    embedder = FakeEmbedder()
    index = FakeSearchIndex()
    index.register_job("tenant-a", "job-s18")
    service = index_mod.IndexTranscript(embedder=embedder, index=index)

    first = await service(_transcript(version=1), tenant_id="tenant-a")
    assert first.embedded > 0
    embedded_after_first = embedder.texts_embedded

    unchanged = await service(_transcript(version=2), tenant_id="tenant-a")
    assert unchanged.embedded == 0
    assert embedder.texts_embedded == embedded_after_first

    edited = await service(_transcript(edit_tail=True, version=3), tenant_id="tenant-a")
    assert 0 < edited.embedded < first.embedded
    assert index.active[("tenant-a", "job-s18")] == 3
