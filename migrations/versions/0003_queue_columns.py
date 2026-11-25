"""Queue columns for S06: started_at, a FIFO sequence, and the claim index (D-021).

`seq` is an identity column: insertion order breaks ties between equal priorities, which created_at
cannot do inside one transaction. The index matches the claim predicate and ordering.

Revision ID: 0003_queue_columns
Revises: 0002_core_tables
Create Date: 2026-11-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_queue_columns"
down_revision: str | None = "0002_core_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("seq", sa.BigInteger, sa.Identity(), nullable=False))
    op.create_index("ix_jobs_claim", "jobs", ["queue", "state", "priority", "seq"])


def downgrade() -> None:
    op.drop_index("ix_jobs_claim", table_name="jobs")
    op.drop_column("jobs", "seq")
    op.drop_column("jobs", "started_at")
