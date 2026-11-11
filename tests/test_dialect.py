"""Offline tests for src/dialect.py — pure helpers, no transformers/torch."""

from src.dialect import sample_chunks


def test_sample_chunks_short_text():
    assert sample_chunks("كلمة واحدة", max_chunks=3, chunk_words=200) == ["كلمة واحدة"]
    assert sample_chunks("   ") == []


def test_sample_chunks_spread():
    words = [f"w{i}" for i in range(600)]
    chunks = sample_chunks(" ".join(words), max_chunks=3, chunk_words=200)
    assert len(chunks) == 3
    assert chunks[0].split()[0] == "w0"  # start
    assert chunks[-1].split()[-1] == "w599"  # end
    assert chunks[1].split()[0] == "w200"  # middle window


def test_sample_chunks_dedupes_identical_windows():
    words = [f"w{i}" for i in range(250)]
    chunks = sample_chunks(" ".join(words), max_chunks=3, chunk_words=200)
    # rounds can collapse windows; never emit the same chunk twice
    assert len(chunks) == len(set(chunks))
