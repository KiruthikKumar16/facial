"""Database connection and session management."""
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool
from config import settings

engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    poolclass=NullPool,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency for FastAPI to inject database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@event.listens_for(engine, "connect")
def _ensure_pgvector_extension(dbapi_conn, connection_record):
    """Ensure the pgvector extension is enabled (Supabase already has it; safe no-op otherwise)."""
    try:
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        finally:
            cursor.close()
    except Exception as e:
        print(f"Warning: Could not load pgvector extension: {e}")
