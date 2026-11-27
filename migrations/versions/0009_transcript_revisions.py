"""Versioned transcripts (S22, design: التمثيل المرجعي).

Each version of a job's transcript is one row: the canonical JSON exactly as the domain serializes
it, its version number and its source (asr or human).

The primary key (transcript_id, version) is the optimistic-concurrency guard: two saves that
both try to write the next version cannot both succeed. RLS as on the other tenant tables (D-024).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_transcript_revisions"
down_revision: str | None = "0008_deletion_retention_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = (
    "tenant_id = current_setting('app.tenant_id', true) "
    "OR current_setting('app.system', true) = 'on'"
)


def upgrade() -> None:
    op.create_table(
        "transcript_revisions",
        sa.Column("transcript_id", sa.Text, nullable=False),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("canonical", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("transcript_id", "version", name="pk_transcript_revisions"),
        sa.CheckConstraint("version >= 1", name="ck_transcript_revisions_version"),
        sa.CheckConstraint("source IN ('asr', 'human')", name="ck_transcript_revisions_source"),
    )
    op.execute("ALTER TABLE transcript_revisions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE transcript_revisions FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY transcript_revisions_tenant_or_system ON transcript_revisions "
        f"USING ({_POLICY}) WITH CHECK ({_POLICY})"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS transcript_revisions_tenant_or_system ON transcript_revisions"
    )
    op.execute("ALTER TABLE transcript_revisions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE transcript_revisions DISABLE ROW LEVEL SECURITY")
    op.drop_table("transcript_revisions")
