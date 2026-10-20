import os
import sys
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

# Ensure backend root is in sys.path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def get_test_engine():
    """Returns an in-memory SQLite engine initialized with all SQLModel tables, using StaticPool."""
    import models  # noqa: F401
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def get_test_session(engine=None):
    """Returns a new Session for testing."""
    if engine is None:
        engine = get_test_engine()
    return Session(engine)
