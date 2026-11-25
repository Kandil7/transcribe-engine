"""SQLAlchemy Core table definitions. They mirror migrations/versions/0002_core_tables.py (S05)."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

metadata = sa.MetaData()

media = sa.Table(
    "media",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("sha256", sa.Text, nullable=False, unique=True),
    sa.Column("storage_key", sa.Text, nullable=False),
    sa.Column("duration_ms", sa.BigInteger, nullable=False),
    sa.Column("format", sa.Text, nullable=False),
    sa.Column("size_bytes", sa.BigInteger, nullable=False),
)

results = sa.Table(
    "results",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("result_key", sa.Text, nullable=False, unique=True),
    sa.Column("media_id", sa.Text, sa.ForeignKey("media.id"), nullable=False),
    sa.Column("engine", sa.Text, nullable=False),
    sa.Column("model_revision", sa.Text, nullable=False),
    sa.Column("pipeline_version", sa.Text, nullable=False),
    sa.Column("pipeline_config", postgresql.JSONB, nullable=False),
    sa.Column("rtf", sa.Float, nullable=True),
    sa.Column("ref_count", sa.Integer, nullable=False, server_default="0"),
)

jobs = sa.Table(
    "jobs",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("tenant_id", sa.Text, nullable=False),
    sa.Column("media_id", sa.Text, sa.ForeignKey("media.id"), nullable=False),
    sa.Column("state", sa.Text, nullable=False),
    sa.Column("stage", sa.Text, nullable=True),
    sa.Column("queue", sa.Text, nullable=False),
    sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("max_attempts", sa.Integer, nullable=False),
    sa.Column("result_id", sa.Text, sa.ForeignKey("results.id"), nullable=True),
    sa.Column("error_code", sa.Text, nullable=True),
    sa.Column("warnings", postgresql.JSONB, nullable=False),
    sa.Column("pipeline_config", postgresql.JSONB, nullable=False),
)
