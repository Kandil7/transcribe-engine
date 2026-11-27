"""Deterministic ids and cache keys (S03, D-007). Same inputs always give the same key.

Every key is a type prefix plus lowercase hex SHA-256: res_, chk_, rag_, emb_.
"""

import hashlib
import json
import operator

from transcribe_engine.domain.config import PipelineConfig

__all__ = ["chunk_id", "embedding_id", "rag_chunk_id", "result_key"]

_SEP = "‖"  # separator between file hash, canonical config and optional isolation scope
_PIPE = "|"


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def result_key(file_sha256: str, config: PipelineConfig, isolation_scope: str | None = None) -> str:
    """Key for one processed result: file bytes plus the full processing configuration.

    `isolation_scope` (a tenant id) is appended only for tenants that need full isolation, so
    shared results keep their key when no scope is given.
    """
    payload = f"{file_sha256}{_SEP}{config.canonical_json()}"
    if isolation_scope is not None:
        payload += f"{_SEP}{isolation_scope}"
    return "res_" + _sha256(payload)


def chunk_id(
    job_id: str, media_sha256: str, config_hash: str, idx: int, start_sample: int, end_sample: int
) -> str:
    """Stable id for one audio chunk of one job.

    A re-run of the same job gives the same ids, so saved chunks are skipped. The job id is part
    of the id: the same audio processed by another job must not collide with its chunk rows (D-065).
    """
    parts = [
        job_id,
        media_sha256,
        config_hash,
        str(operator.index(idx)),
        str(operator.index(start_sample)),
        str(operator.index(end_sample)),
    ]
    return "chk_" + _sha256(_PIPE.join(parts))


def rag_chunk_id(transcript_id: str, version: int, start_ms: int, end_ms: int) -> str:
    """Stable id for one searchable transcript chunk."""
    if _PIPE in transcript_id:
        raise ValueError("transcript_id must not contain '|'")
    parts = [
        transcript_id,
        str(operator.index(version)),
        str(operator.index(start_ms)),
        str(operator.index(end_ms)),
    ]
    return "rag_" + _sha256(_PIPE.join(parts))


def embedding_id(text_with_header: str, embedding_model: str) -> str:
    """Stable id for one embedding. JSON framing stops free text colliding with the model name."""
    framed = json.dumps(
        [text_with_header, embedding_model],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "emb_" + _sha256(framed)
