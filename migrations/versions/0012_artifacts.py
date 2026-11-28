"""Derived artifacts of a transcript version (S19, design: artifacts).

One row per (tenant, transcript, version, kind, model, model version). An artifact never
changes the transcript it was derived from: a new model or a new version of the rules is a new row,
and the old one stays readable. RLS as on the other tenant tables (D-024).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_artifacts"
down_revision: str | None = "0011_rag_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = (
    "tenant_id = current_setting('app.tenant_id', true) "
    "OR current_setting('app.system', true) = 'on'"
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE artifacts (
            tenant_id text NOT NULL REFERENCES tenants(id),
            transcript_id text NOT NULL,
            transcript_version integer NOT NULL CHECK (transcript_version >= 1),
            kind text NOT NULL,
            model text NOT NULL,
            model_version text NOT NULL,
            payload jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, transcript_id, transcript_version, kind, model, model_version)
        )
        """
    )
    op.execute("ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE artifacts FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY artifacts_tenant_or_system ON artifacts "
        f"USING ({_POLICY}) WITH CHECK ({_POLICY})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS artifacts_tenant_or_system ON artifacts")
    op.execute("ALTER TABLE artifacts NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE artifacts DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS artifacts")
