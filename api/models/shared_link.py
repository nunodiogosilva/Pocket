from datetime import datetime, timezone
import secrets
from typing import TYPE_CHECKING, Optional
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .file import FileMeta


class SharedLink(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(default_factory=lambda: secrets.token_urlsafe(32), unique=True, index=True)
    file_id: int = Field(foreign_key="filemeta.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    download_count: int = Field(default=0)
    file: "FileMeta" = Relationship()
