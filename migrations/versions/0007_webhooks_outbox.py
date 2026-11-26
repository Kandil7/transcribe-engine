"""Webhooks (S20, D-048, D-049): the destination on a job, retry state on outbox rows, and the
tenant's webhook secrets. Up to two active secrets per tenant during rotation (D-048). The secrets
table has the same RLS policy as the other tenant tables (D-024). Outbox rows have no tenant
column; the publisher runs in the system scope, as the worker does.

Revision ID: 0007_webhooks_outbox
Revises: 0006_result_refs
Create Date: 2026-11-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_webhooks_outbox"
down_revision: str | None = "0006_result_refs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = (
    "tenant_id = current_setting('app.tenant_id', true) "
    "OR current_setting('app.system', true) = 'on'"
)


def upgrade() -> None:
    op.add_column("jobs", sa.Column("webhook_url", sa.Text, nullable=True))
    op.add_column(
        "outbox",
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column("outbox", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outbox", sa.Column("abandoned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outbox", sa.Column("lease_owner", sa.Text, nullable=True))
    op.add_column("outbox", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "webhook_secrets",
        sa.Column("tenant_id", sa.Text, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("secret_id", sa.Text, nullable=False),
        sa.Column("secret", sa.LargeBinary, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "secret_id", name="pk_webhook_secrets"),
    )
    op.execute("ALTER TABLE webhook_secrets ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE webhook_secrets FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY webhook_secrets_tenant_or_system ON webhook_secrets "
        f"USING ({_POLICY}) WITH CHECK ({_POLICY})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS webhook_secrets_tenant_or_system ON webhook_secrets")
    op.execute("ALTER TABLE webhook_secrets NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE webhook_secrets DISABLE ROW LEVEL SECURITY")
    op.drop_table("webhook_secrets")
    op.drop_column("outbox", "lease_until")
    op.drop_column("outbox", "lease_owner")
    op.drop_column("outbox", "abandoned_at")
    op.drop_column("outbox", "next_attempt_at")
    op.drop_column("outbox", "attempts")
    op.drop_column("jobs", "webhook_url")
