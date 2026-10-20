from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .file import FileMeta


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    login: str = Field(unique=True, index=True)  # Tailscale-User-Login
    name: Optional[str] = Field(default=None)   # Tailscale-User-Name
    profile_pic: Optional[str] = Field(default=None)  # Tailscale-User-Profile-Pic
    email: Optional[str] = Field(default=None, index=True)  # Email or alias
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    files: List["FileMeta"] = Relationship(back_populates="owner")

