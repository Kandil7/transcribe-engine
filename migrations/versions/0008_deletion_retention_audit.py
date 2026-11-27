"""Deletion, retention and consent (S21, D-059): an audit log without content, a per-tenant audio
retention in days, the time audio was removed on a job, and training-consent flags (S22 exports
need them). The audit log keeps the tenant's RLS policy (D-024) and holds no transcript text.

Revision ID: 0008_deletion_retention_audit
Revises: 0007_webhooks_outbox
Create Date: 2026-11-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_deletion_retention_audit"
down_revision: str | None = "0007_webhooks_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = (
    "tenant_id = current_setting('app.tenant_id', true) "
    "OR current_setting('app.system', true) = 'on'"
)


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("retention_days", sa.Integer, nullable=False, server_default="30"),
    )
    op.create_check_constraint(
        "ck_tenants_retention_days", "tenants", "retention_days BETWEEN 1 AND 3650"
    )
    # A cached result no longer holds its original upload (D-060): the upload can be deleted
    # when no job uses it, and the result's pointer is cleared first.
    op.alter_column("results", "media_id", existing_type=sa.Text, nullable=True)
    op.add_column(
        "tenants",
        sa.Column("training_consent", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "jobs",
        sa.Column("training_consent", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column("jobs", sa.Column("audio_deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False),
        sa.Column("event", sa.Text, nullable=False),
        sa.Column("subject_id", sa.Text, nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail", postgresql.JSONB, nullable=False, server_default="{}"),
    )
    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY audit_log_tenant_or_system ON audit_log "
        f"USING ({_POLICY}) WITH CHECK ({_POLICY})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_log_tenant_or_system ON audit_log")
    op.execute("ALTER TABLE audit_log NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log DISABLE ROW LEVEL SECURITY")
    op.drop_table("audit_log")
    op.drop_column("jobs", "audio_deleted_at")
    op.drop_column("jobs", "training_consent")
    op.drop_column("tenants", "training_consent")
    op.alter_column("results", "media_id", existing_type=sa.Text, nullable=False)
    op.drop_constraint("ck_tenants_retention_days", "tenants", type_="check")
    op.drop_column("tenants", "retention_days")
