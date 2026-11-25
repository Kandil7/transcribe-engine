"""The checked-in OpenAPI schema must match the code (S08 drift check, runs in make check)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _exporter() -> object:
    spec = importlib.util.spec_from_file_location(
        "export_openapi", ROOT / "scripts" / "export_openapi.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_openapi_snapshot_is_current() -> None:
    exporter = _exporter()
    checked_in = (ROOT / "docs" / "openapi.json").read_text(encoding="utf-8")
    current = exporter.render()  # type: ignore[attr-defined]
    assert checked_in == current, "docs/openapi.json is stale: run `make openapi`"
