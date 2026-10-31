"""Written-dialect classification on MARBERTv2 (v2 feature).

Model: ``IbrahimAmin/marbertv2-arabic-written-dialect-classifier``
(0.2B params, labels ``MAGHREB | LEV | MSA | GLF | EGY``). Trained on
written dialect text, so it tags transcripts — no audio needed. Opt-in
and never-gating: results land on the record (``dialect``,
``dialect_confidence``) as corpus metadata.

Long transcripts exceed the model's 512-token window, so classification
averages softmax probabilities over up to ``max_chunks`` spread windows
(start / middle / end). Pure helpers are unit-tested; only
``classify_dialect`` touches transformers/torch.
"""

from __future__ import annotations

DIALECT_MODEL = "IbrahimAmin/marbertv2-arabic-written-dialect-classifier"


def sample_chunks(text: str, max_chunks: int = 3, chunk_words: int = 200) -> list[str]:
    """Spread ``max_chunks`` word-windows across ``text`` (start/middle/end).

    Short texts yield a single chunk (the whole text). Windows are
    contiguous word slices; overlapping windows are deduplicated.
    """
    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_words:
        return [" ".join(words)]
    starts = []
    last = len(words) - chunk_words
    for i in range(max_chunks):
        starts.append(round(i * last / max(max_chunks - 1, 1)))
    chunks = []
    for s in dict.fromkeys(starts):
        chunks.append(" ".join(words[s : s + chunk_words]))
    return chunks


def classify_dialect(
    text: str,
    device: str = "cpu",
    model_id: str = DIALECT_MODEL,
    max_chunks: int = 3,
) -> dict:
    """Classify the written dialect of ``text``.

    Returns ``{"dialect": str, "confidence": float, "top": [(label, p), ...]}``
    with probabilities averaged over the sampled chunks. Raises on
    model/download errors — callers decide whether failure is fatal
    (the pipeline records ``dialect_status="failed"`` and moves on).
    """
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    try:
        from .transcribe import load_local_first, resolve_cache_dir
    except ImportError:  # script-style execution
        from transcribe import load_local_first, resolve_cache_dir  # type: ignore

    cache_dir = resolve_cache_dir(model_id)

    def _load():
        tok = AutoTokenizer.from_pretrained(model_id, cache_dir=cache_dir)
        mod = AutoModelForSequenceClassification.from_pretrained(
            model_id, cache_dir=cache_dir
        )
        return tok, mod

    tokenizer, model = load_local_first(_load)
    model.to(torch.device(device))
    model.eval()

    chunks = sample_chunks(text, max_chunks=max_chunks)
    if not chunks:
        raise ValueError("empty text: nothing to classify")
    probs = None
    with torch.inference_mode():
        for chunk in chunks:
            inputs = tokenizer(
                chunk, return_tensors="pt", truncation=True, max_length=512
            ).to(model.device)
            logits = model(**inputs).logits
            p = logits.softmax(-1)[0]
            probs = p if probs is None else probs + p
    probs = probs / len(chunks)
    top = probs.topk(min(3, probs.shape[0]))
    labels = model.config.id2label
    top_pairs = [
        (labels.get(int(i), str(int(i))), round(float(v), 3))
        for v, i in zip(top.values.tolist(), top.indices.tolist())
    ]
    return {"dialect": top_pairs[0][0], "confidence": top_pairs[0][1], "top": top_pairs}
