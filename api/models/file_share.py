from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .file import FileMeta


class FileShare(SQLModel, table=True):
    """Explicit sharing of a file with a specific Tailnet user."""

    id: Optional[int] = Field(default=None, primary_key=True)
    file_id: int = Field(foreign_key="filemeta.id", index=True)
    shared_with_user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    shared_with_login: Optional[str] = Field(default=None, index=True)
    permission: str = Field(default="read")  # "read" or "write"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    file: Optional["FileMeta"] = Relationship()
