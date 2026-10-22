"""SQLAlchemy engine, declarative base, and the ``sqlite-vec`` loader hook.

SQLite's standard build ships without ``enable_load_extension``, so we swap in
the ``sqlean`` implementation (which supports user-defined extensions) when the
runtime lacks the method. The ``sqlite-vec`` C extension is then registered on
every new connection via a ``connect`` event so the ``vec0`` virtual tables can
be created and queried.
"""

import sys

try:
    import sqlite3

    if not hasattr(sqlite3.Connection, "enable_load_extension"):
        import sqlean as sqlite3  # type: ignore

        sys.modules["sqlite3"] = sqlite3
except ImportError:  # pragma: no cover - depends on the installed SQLite build
    pass

import sqlite_vec  # noqa: E402  (import after the possible sqlite3 swap)
from sqlalchemy import event  # noqa: E402
from sqlmodel import SQLModel, create_engine  # noqa: E402

from app.config import settings

engine = create_engine(
    settings.effective_database_url,
    connect_args={"check_same_thread": False, "timeout": 60.0},
)


@event.listens_for(engine, "connect")
def _configure_connection(dbapi_connection, _connection_record) -> None:
    """Enable the ``sqlite-vec`` extension and tuned pragmas per connection."""
    dbapi_connection.enable_load_extension(True)
    sqlite_vec.load(dbapi_connection)
    dbapi_connection.enable_load_extension(False)
    # Wait up to 60s if another thread or the background indexer holds the write lock.
    dbapi_connection.execute("PRAGMA busy_timeout=60000")
    # WAL lets the background indexer write while requests keep reading.
    dbapi_connection.execute("PRAGMA journal_mode=WAL")
    # NORMAL synchronous mode avoids aggressive fsync stalls on external USB drives.
    dbapi_connection.execute("PRAGMA synchronous=NORMAL")
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


def init_db() -> None:
    """Create all tables and apply lightweight backward-compatible migrations."""
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        user_cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(user)").all()]
        if user_cols and "profile_pic" not in user_cols:
            conn.exec_driver_sql("ALTER TABLE user ADD COLUMN profile_pic TEXT")

        cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(filemeta)").all()]
        if cols and "is_deleted" not in cols:
            conn.exec_driver_sql("ALTER TABLE filemeta ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0")
        if cols and "deleted_at" not in cols:
            conn.exec_driver_sql("ALTER TABLE filemeta ADD COLUMN deleted_at DATETIME")


__all__ = ["engine", "init_db", "SQLModel"]
