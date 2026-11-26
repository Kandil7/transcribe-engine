"""Tenants, API keys, idempotency keys, deletion marker, and RLS on jobs (S08, D-024, D-025).

The RLS policy admits a jobs row when `app.tenant_id` matches it, or when `app.system` is 'on'
(workers and the reconciler run as the system scope). FORCE applies the policy to the owner too.

Revision ID: 0004_tenants_keys_rls
Revises: 0003_queue_columns
Create Date: 2026-11-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_tenants_keys_rls"
down_revision: str | None = "0003_queue_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = (
    "tenant_id = current_setting('app.tenant_id', true) "
    "OR current_setting('app.system', true) = 'on'"
)


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("max_active_jobs", sa.Integer, nullable=False, server_default="5"),
        sa.Column("quota_audio_ms", sa.BigInteger, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("key_hash", sa.Text, nullable=False, unique=True),
        sa.Column("scopes", postgresql.ARRAY(sa.Text), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("tenant_id", sa.Text, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("job_id", sa.Text, sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("status", sa.Integer, nullable=False),
        sa.Column("body", postgresql.JSONB, nullable=False),
        sa.Column("request_hash", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "key", name="pk_idempotency_keys"),
    )
    op.add_column(
        "jobs", sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("ALTER TABLE jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE jobs FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY jobs_tenant_or_system ON jobs USING ({_POLICY}) WITH CHECK ({_POLICY})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS jobs_tenant_or_system ON jobs")
    op.execute("ALTER TABLE jobs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE jobs DISABLE ROW LEVEL SECURITY")
    op.drop_column("jobs", "deletion_requested_at")
    op.drop_table("idempotency_keys")
    op.drop_table("api_keys")
    op.drop_table("tenants")
