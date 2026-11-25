"""Write the API's OpenAPI schema to docs/openapi.json (S08). Run with `make openapi`.

No database or storage is needed: the schema comes from the presentation layer alone.
"""

import json
from pathlib import Path

from transcribe_engine.presentation.api.app import create_app

OUT = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"


def render() -> str:
    schema = create_app(lambda _tenant: None, None).openapi()
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
