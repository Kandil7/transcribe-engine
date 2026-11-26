"""Chunk plan, per-chunk results and merged transcripts, with RLS (S10).

Every table carries tenant_id and the same policy as jobs (D-024): a row is visible when
`app.tenant_id` matches it, or when the system scope is on. Plans are written before ASR runs, so a
restarted job reads them back (AC-7).

Revision ID: 0005_chunks_transcripts
Revises: 0004_tenants_keys_rls
Create Date: 2026-11-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_chunks_transcripts"
down_revision: str | None = "0004_tenants_keys_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = (
    "tenant_id = current_setting('app.tenant_id', true) "
    "OR current_setting('app.system', true) = 'on'"
)
_TABLES = ("chunks", "chunk_results", "transcripts")


_OLD_CHUNKS_GUARD = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM chunks) THEN
        RAISE EXCEPTION 'chunks has rows; the S05 shape cannot be replaced automatically';
    END IF;
END $$;
"""


def upgrade() -> None:
    # 0002 created `chunks` with the S05 shape. Nothing has written to it, so it is replaced here.
    # The guard refuses to run if rows exist (data safety).
    op.execute(_OLD_CHUNKS_GUARD)
    op.drop_table("chunks")
    op.create_table(
        "chunks",
        sa.Column("chunk_id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("job_id", sa.Text, sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("idx", sa.Integer, nullable=False),
        sa.Column("total", sa.Integer, nullable=False),
        sa.Column("start_sample", sa.BigInteger, nullable=False),
        sa.Column("end_sample", sa.BigInteger, nullable=False),
        sa.Column("pad_before", sa.BigInteger, nullable=False),
        sa.Column("pad_after", sa.BigInteger, nullable=False),
        sa.Column("sample_rate", sa.Integer, nullable=False),
        sa.Column("media_sha256", sa.Text, nullable=False),
        sa.Column("config_hash", sa.Text, nullable=False),
        sa.UniqueConstraint("job_id", "idx", name="uq_chunks_job_idx"),
        sa.CheckConstraint("end_sample > start_sample", name="ck_chunks_core_positive"),
    )
    op.create_table(
        "chunk_results",
        sa.Column("chunk_id", sa.Text, sa.ForeignKey("chunks.chunk_id"), primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("job_id", sa.Text, sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("words", postgresql.JSONB, nullable=False),
    )
    op.create_table(
        "transcripts",
        sa.Column("job_id", sa.Text, sa.ForeignKey("jobs.id"), primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("sample_rate", sa.Integer, nullable=False),
        sa.Column("words", postgresql.JSONB, nullable=False),
    )
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_or_system ON {table} "
            f"USING ({_POLICY}) WITH CHECK ({_POLICY})"
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_or_system ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("transcripts")
    op.drop_table("chunk_results")
    op.drop_table("chunks")
    op.create_table(
        "chunks",
        sa.Column("chunk_id", sa.Text, primary_key=True),
        sa.Column("job_id", sa.Text, sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("idx", sa.Integer, nullable=False),
        sa.Column("total", sa.Integer, nullable=False),
        sa.Column("start_sample", sa.BigInteger, nullable=False),
        sa.Column("end_sample", sa.BigInteger, nullable=False),
        sa.Column("pad_before", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pad_after", sa.Integer, nullable=False, server_default="0"),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("result_key_s3", sa.Text, nullable=True),
        sa.UniqueConstraint("job_id", "idx", name="uq_chunks_job_idx"),
    )
