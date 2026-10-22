"""Unified, self-referential tree model for files and folders.

``Item`` collapses the previous separate "file" and "folder" concepts into a
single table keyed by ``parent_id`` (root items have ``parent_id = NULL``) and
distinguished by the ``is_folder`` flag. ``FileChunk`` is the text-search
index row whose embedding is stored in the ``sqlite-vec`` virtual table.

The SQLAlchemy table name is kept as ``filemeta`` so existing SQLite databases
and the ``sqlite-vec`` ``filechunk_vec`` table remain compatible.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from app.models.user import User


class Item(SQLModel, table=True):
    """A single node in a user's file tree — either a file or a folder."""

    __tablename__ = "filemeta"

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    storage_path: str
    file_size: int
    mime_type: str
    parent_id: Optional[int] = Field(default=None, foreign_key="filemeta.id", index=True)
    is_folder: bool = Field(default=False)
    is_deleted: bool = Field(default=False)
    deleted_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    owner_id: int = Field(foreign_key="user.id", index=True)
    owner: Optional["User"] = Relationship(back_populates="items")


class FileChunk(SQLModel, table=True):
    """A piece of searchable file text; its embedding is stored in ``sqlite-vec``."""

    id: Optional[int] = Field(default=None, primary_key=True)
    file_id: int = Field(foreign_key="filemeta.id", index=True)
    chunk_index: int
    text: str


__all__ = ["Item", "FileChunk"]
