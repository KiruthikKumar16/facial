"""Pytest configuration and test fixtures for backend test suite."""

import sys
from pathlib import Path
import pytest

# Ensure backend and root workspace are on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(backend_dir.parent) not in sys.path:
    sys.path.insert(0, str(backend_dir.parent))

from database import Base, engine, ensure_detection_event_id_column
import models  # Ensure all ORM models are registered with Base.metadata


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Ensure all SQLAlchemy tables are created for the test session."""
    Base.metadata.create_all(bind=engine)
    try:
        ensure_detection_event_id_column()
    except Exception:
        pass
    yield
