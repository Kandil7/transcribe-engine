"""Index one transcript version for search (S18, AC-5, AC-6).

Chunks the transcript, embeds only the chunks whose text is not yet embedded (the embedding id
hashes the contextual header, the text and the model, so unchanged text is never embedded twice),
stores the chunk rows, then activates the version. Activation is the last step, so a search never
sees a version whose vectors are missing.
"""

from dataclasses import dataclass

from transcribe_engine.application.ports.search import Embedder, IndexedChunk, SearchIndex
from transcribe_engine.domain.keys import embedding_id
from transcribe_engine.domain.rag import RagChunkConfig, build_rag_chunks, contextual_header
from transcribe_engine.domain.text import normalize
from transcribe_engine.domain.transcript import CanonicalTranscript

__all__ = ["IndexResult", "IndexTranscript"]


@dataclass(frozen=True)
class IndexResult:
    version: int
    chunks: int
    embedded: int
    reused: int


class IndexTranscript:
    def __init__(self, *, embedder: Embedder, index: SearchIndex) -> None:
        self._embedder = embedder
        self._index = index

    async def __call__(self, transcript: CanonicalTranscript, *, tenant_id: str) -> IndexResult:
        model = self._embedder.model
        cfg = RagChunkConfig()
        chunks = build_rag_chunks(
            transcript,
            tenant_id=tenant_id,
            tokenize=self._embedder.count_tokens,
            cfg=cfg,
        )
        rows: list[IndexedChunk] = []
        texts_by_id: dict[str, str] = {}
        for chunk in chunks:
            text_with_header = f"{contextual_header(chunk)}\n{chunk.text}"
            eid = embedding_id(text_with_header, model)
            texts_by_id.setdefault(eid, text_with_header)
            rows.append(
                IndexedChunk(
                    chunk_id=chunk.chunk_id,
                    embedding_id=eid,
                    start_ms=chunk.start_ms,
                    end_ms=chunk.end_ms,
                    body=chunk.text,
                    search_text=normalize(chunk.text).search,
                )
            )
        known = await self._index.known_embedding_ids(tenant_id, model, list(texts_by_id))
        missing = [eid for eid in texts_by_id if eid not in known]
        vectors: dict[str, list[float]] = {}
        if missing:
            embedded = await self._embedder.embed([texts_by_id[eid] for eid in missing])
            vectors = {eid: list(vector) for eid, vector in zip(missing, embedded, strict=True)}
        await self._index.store(
            tenant_id,
            transcript.transcript_id,
            transcript.media.media_id,
            transcript.version,
            model,
            rows,
            vectors,
        )
        await self._index.activate(tenant_id, transcript.transcript_id, transcript.version)
        return IndexResult(
            version=transcript.version,
            chunks=len(rows),
            embedded=len(missing),
            reused=len(texts_by_id) - len(missing),
        )
