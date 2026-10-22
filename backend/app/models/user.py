from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from app.models.item import Item


class User(SQLModel, table=True):
    """A Tailnet user, JIT-provisioned from Tailscale identity headers."""

    id: Optional[int] = Field(default=None, primary_key=True)
    login: str = Field(unique=True, index=True)
    name: Optional[str] = Field(default=None)
    profile_pic: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    items: List["Item"] = Relationship(back_populates="owner")


__all__ = ["User"]
