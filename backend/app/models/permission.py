"""Sharing and access-control models.

``FileShare`` is the granular ACL: it grants a specific Tailnet user (matched by
id or login) read/write permission on an ``Item``. ``SharedLink`` is an
unguessable public token for Tailscale Funnel downloads.
"""

import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from app.models.item import Item


class FileShare(SQLModel, table=True):
    """Explicit sharing of an item with a specific Tailnet user (an ACL entry)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    file_id: int = Field(foreign_key="filemeta.id", index=True)
    shared_with_user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    shared_with_login: Optional[str] = Field(default=None, index=True)
    permission: str = Field(default="read")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    item: Optional["Item"] = Relationship()


class SharedLink(SQLModel, table=True):
    """Public, token-based share for Funnel ingress downloads."""

    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(default_factory=lambda: secrets.token_urlsafe(32), unique=True, index=True)
    file_id: int = Field(foreign_key="filemeta.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    download_count: int = Field(default=0)
    item: "Item" = Relationship()


__all__ = ["FileShare", "SharedLink"]
