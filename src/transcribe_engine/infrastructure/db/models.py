"""SQLAlchemy Core table definitions. They mirror migrations/versions/0002_core_tables.py (S05).

`metadata` is the target for Alembic autogenerate (migrations/env.py).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

metadata = sa.MetaData()

media = sa.Table(
    "media",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("tenant_id", sa.Text, nullable=False),
    sa.Column("sha256", sa.Text, nullable=False),
    sa.Column("storage_key", sa.Text, nullable=False),
    sa.Column("duration_ms", sa.BigInteger, nullable=False),
    sa.Column("format", sa.Text, nullable=False),
    sa.Column("size_bytes", sa.BigInteger, nullable=False),
    sa.UniqueConstraint("tenant_id", "sha256", name="uq_media_tenant_sha256"),
)

results = sa.Table(
    "results",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("result_key", sa.Text, nullable=False, unique=True),
    sa.Column("media_id", sa.Text, sa.ForeignKey("media.id"), nullable=True),
    sa.Column("engine", sa.Text, nullable=False),
    sa.Column("model_revision", sa.Text, nullable=False),
    sa.Column("pipeline_version", sa.Text, nullable=False),
    sa.Column("pipeline_config", postgresql.JSONB, nullable=False),
    sa.Column("config_canonical", sa.Text, nullable=False),
    sa.Column("rtf", sa.Float, nullable=True),
    sa.Column("ref_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.CheckConstraint("ref_count >= 0", name="ck_results_ref_count"),
)

jobs = sa.Table(
    "jobs",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("tenant_id", sa.Text, nullable=False),
    sa.Column("media_id", sa.Text, sa.ForeignKey("media.id"), nullable=False),
    sa.Column("state", sa.Text, nullable=False),
    sa.Column("stage", sa.Text, nullable=True),
    sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
    sa.Column("queue", sa.Text, nullable=False),
    sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
    sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("max_attempts", sa.Integer, nullable=False),
    sa.Column("lease_owner", sa.Text, nullable=True),
    sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
    sa.Column("run_after", sa.DateTime(timezone=True), nullable=True),
    sa.Column("result_id", sa.Text, sa.ForeignKey("results.id"), nullable=True),
    sa.Column("error_code", sa.Text, nullable=True),
    sa.Column("warnings", postgresql.JSONB, nullable=False, server_default="[]"),
    sa.Column("pipeline_config", postgresql.JSONB, nullable=False),
    sa.Column("config_canonical", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("seq", sa.BigInteger, sa.Identity(), nullable=False),
    sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("webhook_url", sa.Text, nullable=True),
    sa.Column("training_consent", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("audio_deleted_at", sa.DateTime(timezone=True), nullable=True),
)

transcript_versions = sa.Table(
    "transcript_versions",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("result_id", sa.Text, sa.ForeignKey("results.id"), nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("raw_text", sa.Text, nullable=False),
    sa.Column("search_text", sa.Text, nullable=False),
    sa.Column("offset_map_key", sa.Text, nullable=False),
    sa.UniqueConstraint("result_id", "version", name="uq_versions_result_version"),
)

segments = sa.Table(
    "segments",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("version_id", sa.Text, sa.ForeignKey("transcript_versions.id"), nullable=False),
    sa.Column("idx", sa.Integer, nullable=False),
    sa.Column("start_ms", sa.BigInteger, nullable=False),
    sa.Column("end_ms", sa.BigInteger, nullable=False),
    sa.Column("speaker", sa.Text, nullable=True),
    sa.Column("text", sa.Text, nullable=False),
    sa.Column("suspect", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("words", postgresql.JSONB, nullable=False, server_default="[]"),
    sa.UniqueConstraint("version_id", "idx", name="uq_segments_version_idx"),
)

outbox = sa.Table(
    "outbox",
    metadata,
    sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
    sa.Column("event", sa.Text, nullable=False),
    sa.Column("payload", postgresql.JSONB, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("abandoned_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("lease_owner", sa.Text, nullable=True),
    sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
)

webhook_secrets = sa.Table(
    "webhook_secrets",
    metadata,
    sa.Column("tenant_id", sa.Text, sa.ForeignKey("tenants.id"), nullable=False),
    sa.Column("secret_id", sa.Text, nullable=False),
    sa.Column("secret", sa.LargeBinary, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint("tenant_id", "secret_id", name="pk_webhook_secrets"),
)

tenants = sa.Table(
    "tenants",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("max_active_jobs", sa.Integer, nullable=False, server_default="5"),
    sa.Column("retention_days", sa.Integer, nullable=False, server_default="30"),
    sa.CheckConstraint("retention_days BETWEEN 1 AND 3650", name="ck_tenants_retention_days"),
    sa.Column("training_consent", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("quota_audio_ms", sa.BigInteger, nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
)

api_keys = sa.Table(
    "api_keys",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("tenant_id", sa.Text, nullable=False),
    sa.Column("key_hash", sa.Text, nullable=False, unique=True),
    sa.Column("scopes", postgresql.ARRAY(sa.Text), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
)

idempotency_keys = sa.Table(
    "idempotency_keys",
    metadata,
    sa.Column("tenant_id", sa.Text, nullable=False),
    sa.Column("key", sa.Text, nullable=False),
    sa.Column("job_id", sa.Text, sa.ForeignKey("jobs.id"), nullable=False),
    sa.Column("status", sa.Integer, nullable=False),
    sa.Column("body", postgresql.JSONB, nullable=False),
    sa.Column("request_hash", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("tenant_id", "key", name="pk_idempotency_keys"),
)


chunk_table = sa.Table(
    "chunks",
    metadata,
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

chunk_result_table = sa.Table(
    "chunk_results",
    metadata,
    sa.Column("chunk_id", sa.Text, sa.ForeignKey("chunks.chunk_id"), primary_key=True),
    sa.Column("tenant_id", sa.Text, nullable=False),
    sa.Column("job_id", sa.Text, sa.ForeignKey("jobs.id"), nullable=False),
    sa.Column("words", postgresql.JSONB, nullable=False),
)

transcript_table = sa.Table(
    "transcripts",
    metadata,
    sa.Column("job_id", sa.Text, sa.ForeignKey("jobs.id"), primary_key=True),
    sa.Column("tenant_id", sa.Text, nullable=False),
    sa.Column("sample_rate", sa.Integer, nullable=False),
    sa.Column("words", postgresql.JSONB, nullable=False),
)


result_ref_table = sa.Table(
    "result_refs",
    metadata,
    sa.Column("job_id", sa.Text, sa.ForeignKey("jobs.id"), primary_key=True),
    sa.Column("tenant_id", sa.Text, nullable=False),
    sa.Column("result_id", sa.Text, sa.ForeignKey("results.id"), nullable=False),
)
