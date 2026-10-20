import sys
try:
    import sqlite3
    if not hasattr(sqlite3.Connection, "enable_load_extension"):
        import sqlean as sqlite3
        sys.modules["sqlite3"] = sqlite3
except ImportError:
    pass

import sqlite_vec
from sqlalchemy import event
from sqlmodel import SQLModel, create_engine


from config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 60.0},
)


@event.listens_for(engine, "connect")
def _configure_connection(dbapi_connection, _connection_record):
    dbapi_connection.enable_load_extension(True)
    sqlite_vec.load(dbapi_connection)
    dbapi_connection.enable_load_extension(False)
    # Wait up to 60s if another thread or background indexer holds the write lock
    dbapi_connection.execute("PRAGMA busy_timeout=60000")
    # WAL lets the background indexer write while requests keep reading
    dbapi_connection.execute("PRAGMA journal_mode=WAL")
    # NORMAL synchronous mode avoids aggressive fsync stalls on external USB drives
    dbapi_connection.execute("PRAGMA synchronous=NORMAL")
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


def init_db():
    SQLModel.metadata.create_all(engine)
    # Ensure backward-compatible SQLite migration for new columns
    with engine.begin() as conn:
        cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(filemeta)").all()]
        if cols and "is_deleted" not in cols:
            conn.exec_driver_sql("ALTER TABLE filemeta ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0")
        if cols and "deleted_at" not in cols:
            conn.exec_driver_sql("ALTER TABLE filemeta ADD COLUMN deleted_at DATETIME")

