# S18 — RAG chunks, embeddings, hybrid search

| | |
|---|---|
| Phase | 5 |
| Depends on | S15 |
| Branch | `feat/S18-rag-indexing-search` |
| Design sections | نواتج النظام والـ RAG › الـ RAG؛ التخزين والـ API |
| ADRs | — |

## Goal
Every completed transcript version is split into retrieval chunks with full metadata, embedded with a
contextual header, and searchable by hybrid search that returns timestamped citations.

## Interfaces
```python
@dataclass(frozen=True)
class RagChunk:
    chunk_id: str; transcript_id: str; transcript_version: int; media_id: str; tenant_id: str
    acl: tuple[str, ...]; start_ms: int; end_ms: int; segment_ids: tuple[str, ...]
    parent_id: str | None; chapter_title: str | None; speakers: tuple[str, ...]; lang: str
    has_code_switch: bool; entities: tuple[str, ...]; confidence: float; quality_flags: tuple[str, ...]
    media_title: str; recorded_at: date | None; text: str; level: Literal["small", "parent", "summary"]
def build_rag_chunks(t: CanonicalTranscript, tok: TokenCounter, cfg: RagChunkConfig) -> Sequence[RagChunk]
def contextual_header(c: RagChunk) -> str
class Embedder(Protocol):
    model: str; version: str
    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...
class SearchIndex(Protocol):
    async def upsert(self, chunks: Sequence[RagChunk], vectors: Sequence[Sequence[float]]) -> None: ...
    async def activate(self, transcript_id: str, version: int) -> None: ...
    async def search(self, q: SearchQuery) -> Sequence[SearchHit]: ...   # tenant-scoped
```

## Files
- `src/transcribe_engine/domain/rag.py` (chunking, header, RRF, confidence weighting — pure)
- `src/transcribe_engine/application/use_cases/{index_transcript,search}.py`
- `src/transcribe_engine/infrastructure/search/{pg_index,embedder_http,reranker_http}.py`
- `migrations/versions/00xx_rag_tables.py` (pgvector)
- `src/transcribe_engine/presentation/api/routes_search.py` — `GET /v1/search`, `GET .../rag-chunks`

## Rules `[D: الـ RAG]`
- Start from speaker turns after merge; 200–400 tokens by the embedding model's tokenizer; 1–2 sentence
  overlap; never cross a topic boundary (similarity drop between consecutive sentence embeddings).
- Three levels: small (search), parent 2–5 min (context for the LLM), file summary (S19 fills it).
- Contextual header prepended only for embedding.
- Hybrid: BM25-style on `search_text` + dense vectors → Reciprocal Rank Fusion → reranker on top 20–50;
  low-confidence chunks down-weighted and marked.
- Every hit returns media id, start/end ms and a player deep link `?t=<seconds>`.
- Ids: `rag_chunk_id`, `embedding_id` (S03); re-index skips unchanged; new version or new embedding
  model indexed in background, then atomic switch; never mix two embedding models in one search.
- Event `index.completed` after activation (S20).

## Acceptance criteria
- **AC-1** — `test_rag.py::test_chunks_within_token_bounds` (Hypothesis).
- **AC-2** — `test_rag.py::test_no_chunk_crosses_topic_boundary` (unit, constructed similarities).
- **AC-3** — `test_rag.py::test_metadata_complete` (unit): every field non-empty where the source has it.
- **AC-4** — `test_rag.py::test_rrf_known_ranking` (unit).
- **AC-5** — `test_index_transcript.py::test_reindex_skips_unchanged` (unit, fake embedder counts calls).
- **AC-6** — `test_search_contract.py::test_atomic_version_switch` (integration): searches during
  re-index return only one version.
- **AC-7** — `test_search_contract.py::test_tenant_isolation` (integration).
- **AC-8** — `test_api_search.py::test_hit_has_deeplink` (integration).

## Commit plan
1. `docs(S18): add spec`
2. `test(S18): add RAG tests (xfail)`
3. `feat(S18): add RAG chunking and contextual header`
4. `build(S18): add pgvector tables`
5. `feat(S18): add embedder port and HTTP adapter`
6. `feat(S18): add index use case with atomic activation`
7. `feat(S18): add hybrid search with RRF and reranker`
8. `feat(S18): add search and rag-chunks endpoints`

## Open questions
- [ ] Q1 — BM25 in Postgres: built-in FTS (`ts_rank`, not true BM25) on normalized text, an extension, or
  OpenSearch? Proposed: built-in FTS behind `SearchIndex` for v1; compare recall in S16.
- [ ] Q2 — Embedding and reranker models: compare 2–3 on real Arabic questions (design requirement), record ADR.
- [ ] Q3 — Parent level before S19 chapters exist: proposed fixed 2–5 min windows on speaker-turn boundaries.
