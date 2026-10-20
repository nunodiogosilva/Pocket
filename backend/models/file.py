from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .user import User


class FileMeta(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    storage_path: str
    file_size: int
    mime_type: str
    parent_id: Optional[int] = Field(default=None, foreign_key="filemeta.id")
    is_folder: bool = Field(default=False)
    is_deleted: bool = Field(default=False)
    deleted_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    owner_id: int = Field(foreign_key="user.id")
    owner: "User" = Relationship(back_populates="files")
