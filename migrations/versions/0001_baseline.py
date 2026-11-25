"""Baseline: empty schema. S05 adds the first tables.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-25

"""

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No schema yet: the baseline exists so the migration chain and tooling are proven."""


def downgrade() -> None:
    """Nothing to undo."""
