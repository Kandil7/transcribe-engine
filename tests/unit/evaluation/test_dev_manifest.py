import importlib
from pathlib import Path

import pytest

DEV_MANIFEST = Path(__file__).resolve().parents[3] / "evaluation" / "spike" / "manifest.jsonl"


@pytest.mark.skipif(
    not DEV_MANIFEST.exists(),
    reason="R-003: the human-transcribed dev hour is not in evaluation/spike/manifest.jsonl yet",
)
def test_dev_manifest_meets_the_coverage_gate() -> None:
    manifest = importlib.import_module("evaluation.spike.manifest")

    assert manifest.coverage_problems(manifest.summarize(manifest.load(DEV_MANIFEST))) == []
