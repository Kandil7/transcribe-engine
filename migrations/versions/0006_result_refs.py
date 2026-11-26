"""Per-job result references (S10, D-037): one row per (job, result) makes a cache-hit increment
idempotent, so a retried job cannot count the same reference twice. RLS as on jobs (D-024).

Revision ID: 0006_result_refs
Revises: 0005_chunks_transcripts
Create Date: 2026-11-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_result_refs"
down_revision: str | None = "0005_chunks_transcripts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = (
    "tenant_id = current_setting('app.tenant_id', true) "
    "OR current_setting('app.system', true) = 'on'"
)


def upgrade() -> None:
    op.create_table(
        "result_refs",
        sa.Column("job_id", sa.Text, sa.ForeignKey("jobs.id"), primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("result_id", sa.Text, sa.ForeignKey("results.id"), nullable=False),
    )
    op.execute("ALTER TABLE result_refs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE result_refs FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY result_refs_tenant_or_system ON result_refs "
        f"USING ({_POLICY}) WITH CHECK ({_POLICY})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS result_refs_tenant_or_system ON result_refs")
    op.execute("ALTER TABLE result_refs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE result_refs DISABLE ROW LEVEL SECURITY")
    op.drop_table("result_refs")
