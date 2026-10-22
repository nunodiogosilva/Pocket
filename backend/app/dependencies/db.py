"""Database session dependency.

``get_db`` yields an isolated ``Session`` scoped to a single HTTP request cycle.
The engine itself lives in ``app.core.database``; this module only bridges the
engine to FastAPI's dependency graph so it can be overridden in tests.
"""

from sqlmodel import Session

from app.core.database import engine


def get_db():
    """Yield a database session for the lifetime of one request."""
    with Session(engine) as session:
        yield session


__all__ = ["get_db"]
