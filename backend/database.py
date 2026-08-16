"""Database connection and session management."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool
from config import settings

# Create engine
engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    poolclass=NullPool,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()


def get_db():
    """Dependency for FastAPI to inject database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Enable pgvector extension
@event.listens_for(engine, "connect")
def load_spatialite(dbapi_conn, connection_record):
    """Load pgvector extension on connection."""
    try:
        dbapi_conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except Exception as e:
        print(f"Warning: Could not load pgvector extension: {e}")
