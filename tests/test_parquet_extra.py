"""Parquet edge cases: missing input, empty rows, row coercion."""

from src.jsonl_to_parquet import (
    PARQUET_COLUMNS,
    coerce_rows,
    jsonl_to_rows,
    write_parquet,
)


def test_missing_jsonl_yields_no_rows(tmp_path):
    assert jsonl_to_rows(tmp_path / "nope.jsonl") == []


def test_empty_rows_write_readable_table(tmp_path):
    out = tmp_path / "empty.parquet"
    written = write_parquet([], str(out))
    assert written == str(out)
    import polars as pl

    df = pl.read_parquet(out)
    assert df.columns == PARQUET_COLUMNS
    assert len(df) == 0


def test_coerce_rows_projects_columns():
    rows = coerce_rows([{"video_id": "v", "bogus": 1}])
    assert set(rows[0]) == set(PARQUET_COLUMNS)
    assert rows[0]["video_id"] == "v"
    assert rows[0]["start"] is None
