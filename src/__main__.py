"""Allow `python -m src ...` (forwards to src.cli)."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
