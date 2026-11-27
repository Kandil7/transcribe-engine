"""Chunk-plan fence (S10).

A job is prepared once its chunk plan is committed, even an empty plan for a silent file. The GPU
stage completes a job only after this mark, so a late cpu stage cannot be overtaken by a stage that
completes the job with an empty transcript.

Revision ID: 0010_job_prepared
Revises: 0009_transcript_revisions
Create Date: 2026-11-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_job_prepared"
down_revision: str | None = "0009_transcript_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "prepared_at")
