"""Shared test setup: make the repo root importable so tests use the real
package (`from src.transcribe import ...`).

Replaces the per-file `sys.path.insert(0, "src")` boilerplate that forced
every src module to carry a try/except dual-import dance.
"""

import sys
from pathlib import Path

# Repo root so tests can import the real package: `from src.transcribe import ...`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
