"""Database connection and session management."""
import logging
import os
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool
from config import settings

logger = logging.getLogger(__name__)

db_url = os.environ.get("DATABASE_URL") or settings.database_url
try:
    engine = create_engine(
        db_url,
        echo=settings.debug,
        poolclass=NullPool,
    )
    # Validate connection driver availability
    engine.dialect.dbapi
except Exception as e:
    logger.warning(f"Database dialect/driver initialization failed for {db_url}: {e}. Using local SQLite fallback.")
    db_url = "sqlite:///./facial_recognition.db"
    engine = create_engine(
        db_url,
        echo=settings.debug,
        connect_args={"check_same_thread": False},
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_detection_event_id_column():
    """Upgrade legacy tables with columns added after initial release."""
    with engine.begin() as connection:
        inspector = inspect(connection)
        table_columns = {
            "detections": {
                "event_id": "VARCHAR",
                "embedding_vector": "vector(512)" if engine.dialect.name == "postgresql" else "TEXT",
                "unregistered_subject_id": "VARCHAR",
                "device_id": "VARCHAR",
                "sequence_number": "INTEGER",
                "priority": "VARCHAR",
                "config_version": "INTEGER",
                "detection_model_version": "VARCHAR",
                "embedding_model_version": "VARCHAR",
                "gallery_version": "INTEGER",
                "threshold_version": "INTEGER",
                "camera_config_version": "INTEGER",
                "algorithm_version": "VARCHAR",
                "version_bundle_hash": "VARCHAR",
            },
            "embeddings": {
                "model_version": "VARCHAR",
            },
        }
        for table_name, missing_columns in table_columns.items():
            if not inspector.has_table(table_name):
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in missing_columns.items():
                if column_name not in columns:
                    connection.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                    )

            if table_name == "detections" and "event_id" not in columns:
                connection.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ix_detections_event_id "
                        "ON detections (event_id)"
                    )
                )
            if table_name == "embeddings" and "model_version" not in columns:
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_embeddings_model_version "
                        "ON embeddings (model_version)"
                    )
                )


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
