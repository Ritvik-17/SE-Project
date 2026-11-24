from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# Idempotent column additions for databases created by earlier versions.
# Stop-gap until Alembic migrations are introduced.
_PRE_CREATE = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    # The first knowledge-base prototype (knowledge_documents/chunks) is replaced by kb_*; drop it only if empty.
    # Dynamic SQL: a static reference to a missing table fails when the block is planned.
    """DO $$ DECLARE t text; is_empty boolean; BEGIN
         FOREACH t IN ARRAY ARRAY['knowledge_chunks', 'knowledge_documents'] LOOP
           IF to_regclass(t) IS NOT NULL THEN
             EXECUTE format('SELECT NOT EXISTS (SELECT 1 FROM %I)', t) INTO is_empty;
             IF is_empty THEN EXECUTE format('DROP TABLE %I CASCADE', t); END IF;
           END IF;
         END LOOP;
       END $$""",
]

_UPGRADES = [
    "ALTER TABLE requirements ADD COLUMN IF NOT EXISTS origin VARCHAR(50) NOT NULL DEFAULT 'extracted'",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS jurisdiction VARCHAR(20) NOT NULL DEFAULT 'IN'",
    "ALTER TABLE requirements ADD COLUMN IF NOT EXISTS grounding_support VARCHAR(30)",
    "ALTER TABLE requirements ADD COLUMN IF NOT EXISTS citations JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE requirements ADD COLUMN IF NOT EXISTS business_justification TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE requirements ADD COLUMN IF NOT EXISTS assumptions JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE requirements ADD COLUMN IF NOT EXISTS dependencies JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE requirements ADD COLUMN IF NOT EXISTS applicable_regulations JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE requirements ADD COLUMN IF NOT EXISTS risk_level VARCHAR(10) NOT NULL DEFAULT 'low'",
    "ALTER TABLE requirements ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE requirements ADD COLUMN IF NOT EXISTS history JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE approval_requests ALTER COLUMN status TYPE VARCHAR(30)",
    # Step 17: security
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id) ON DELETE SET NULL",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS legal_hold BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ",
    "ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS principal VARCHAR(100)",
    "ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS project_ref INTEGER",
    "UPDATE audit_log SET project_ref = project_id WHERE project_ref IS NULL AND project_id IS NOT NULL",
    "ALTER TABLE kb_embedding_cache ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    # Step 20: artefact versions, deployment stage
    "ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'approved'",
    "ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ",
    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS deployment_stage VARCHAR(20) NOT NULL DEFAULT 'assisted'",
    "ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS domain VARCHAR(100)",
    "ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS prev_hash VARCHAR(64)",
    "ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS hash VARCHAR(64)",
    "ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS audit_log_project_id_fkey",
    "ALTER TABLE audit_log ADD CONSTRAINT audit_log_project_id_fkey FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL",
    # Knowledge-base indexes: ANN vector search, full-text search, fuzzy term lookup, metadata filters.
    "CREATE INDEX IF NOT EXISTS ix_kb_chunks_embedding_hnsw ON kb_chunks "
    "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)",
    "CREATE INDEX IF NOT EXISTS ix_kb_chunks_tsv ON kb_chunks USING gin (tsv)",
    "CREATE INDEX IF NOT EXISTS ix_kb_terms_term_trgm ON kb_terms USING gin (lower(term) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_kb_documents_filters ON kb_documents (collection, status, effective_from, effective_to)",
    "CREATE INDEX IF NOT EXISTS ix_kb_documents_jurisdictions ON kb_documents USING gin (jurisdictions)",
    "CREATE INDEX IF NOT EXISTS ix_kb_documents_applicability ON kb_documents USING gin (applicability)",
]


def init_db() -> None:
    """Enable pgvector, create tables and apply column upgrades."""
    from app import models  # noqa: F401  (registers models on Base.metadata)

    with engine.begin() as conn:
        for stmt in _PRE_CREATE:
            conn.execute(text(stmt))
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        _match_embedding_dimension(conn)
        for stmt in _UPGRADES:
            conn.execute(text(stmt))


def _match_embedding_dimension(conn) -> None:
    """When the embedding model changes size (e.g. OpenAI 1536 → local bge-small 384), clear the old vectors and
    resize the columns. Passages stay keyword-searchable; `python -m app.kb.seed --embed` re-embeds them."""
    from app.config import get_settings

    dim = get_settings().embedding_dim
    for table in ("kb_chunks", "kb_embedding_cache"):
        current = conn.execute(text("SELECT atttypmod FROM pg_attribute WHERE attrelid = to_regclass(:t) "
                                    "AND attname = 'embedding'"), {"t": table}).scalar()
        if current is None or current == dim:
            continue
        if table == "kb_chunks":
            conn.execute(text("DROP INDEX IF EXISTS ix_kb_chunks_embedding_hnsw"))
            conn.execute(text("UPDATE kb_chunks SET embedding = NULL"))
            conn.execute(text("UPDATE kb_documents SET embedding_model = NULL"))
        else:
            conn.execute(text("DELETE FROM kb_embedding_cache"))
        conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN embedding TYPE vector({dim})"))


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
