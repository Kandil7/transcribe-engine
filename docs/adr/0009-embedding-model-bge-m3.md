# 0009. Embedding model: bge-m3, provisional until measured (R-009)
Status: Accepted, provisional (S18, D-079)
Date: 2026-11-28   Slice: S18

## Context
Search needs a multilingual dense embedder for Arabic. The design asks for a comparison of 2 to 3 candidates on real Arabic
questions. No such questions exist yet, because the human reference data is owner-blocked (R-001, R-009).

## Decision
Use `BAAI/bge-m3` (MIT), 1024 dimensions, CLS pooling, L2-normalised, run in-process on the pinned ONNX export with ONNX
Runtime, offline from the local cache. The model identity is `BAAI/bge-m3@<revision>`: a new pin is a new identity, and one
search never mixes vectors from two identities.

## Alternatives considered
- paraphrase-multilingual-MiniLM: smaller and cached, weaker for Arabic retrieval in general (not measured here).
- A hosted embedding API: excluded. Transcripts would leave the deployment, which needs the owner's privacy decision (R-011).

## Consequences
- The choice is provisional. The comparison in S18 Q2 is still owed, and R-009 stays open.
- Changing the model or its revision needs a full re-index of every transcript, because the vectors are not compatible.
- The weights are tensor data, not pickle, so no unsafe deserialisation (D-063).
