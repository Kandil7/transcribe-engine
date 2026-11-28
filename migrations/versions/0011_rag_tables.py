"""RAG search tables (S18, design: التخزين والـ API).

- rag_embeddings: one vector per (tenant, embedding_id). The id is a hash of the text with its
  header and the model, so unchanged text is never embedded twice (AC-5).
- rag_chunks: the searchable chunks of one transcript version. The primary key is per tenant and
  chunk.
- rag_active: the one active version of each transcript. Searches read only the active version, so
  a re-index is invisible until it is activated in one transaction (AC-6).

RLS as on the other tenant tables (D-024). Extension: pgvector, in the pgvector image (D-057).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_rag_tables"
down_revision: str | None = "0010_job_prepared"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = (
    "tenant_id = current_setting('app.tenant_id', true) "
    "OR current_setting('app.system', true) = 'on'"
)
_TABLES = ("rag_embeddings", "rag_chunks", "rag_active")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE rag_embeddings (
            tenant_id text NOT NULL REFERENCES tenants(id),
            embedding_id text NOT NULL,
            embedding_model text NOT NULL,
            vector vector(1024) NOT NULL,
            PRIMARY KEY (tenant_id, embedding_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE rag_chunks (
            tenant_id text NOT NULL REFERENCES tenants(id),
            chunk_id text NOT NULL,
            transcript_id text NOT NULL,
            transcript_version integer NOT NULL CHECK (transcript_version >= 1),
            media_id text NOT NULL,
            start_ms integer NOT NULL CHECK (start_ms >= 0),
            end_ms integer NOT NULL CHECK (end_ms >= start_ms),
            body text NOT NULL,
            search_text text NOT NULL,
            embedding_id text NOT NULL,
            embedding_model text NOT NULL,
            PRIMARY KEY (tenant_id, chunk_id),
            FOREIGN KEY (tenant_id, embedding_id)
                REFERENCES rag_embeddings (tenant_id, embedding_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE rag_active (
            tenant_id text NOT NULL REFERENCES tenants(id),
            transcript_id text NOT NULL,
            transcript_version integer NOT NULL CHECK (transcript_version >= 1),
            PRIMARY KEY (tenant_id, transcript_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX rag_chunks_fts ON rag_chunks USING gin (to_tsvector('simple', search_text))"
    )
    op.execute(
        "CREATE INDEX rag_embeddings_hnsw ON rag_embeddings USING hnsw (vector vector_cosine_ops)"
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
    op.execute("DROP TABLE IF EXISTS rag_active")
    op.execute("DROP TABLE IF EXISTS rag_chunks")
    op.execute("DROP TABLE IF EXISTS rag_embeddings")
