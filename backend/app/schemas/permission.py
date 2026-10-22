"""DTOs for sharing (ACL) and public shared links."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.item import ItemRead


class SharedItemRead(ItemRead):
    """An item shared with the user, including sharer identity and permission."""

    shared_by: str
    shared_by_name: Optional[str] = None
    permission: str = "read"


class SharedDirectoryContent(BaseModel):
    """Separated folders and files shared with the user."""

    folders: list[SharedItemRead] = Field(default_factory=list)
    files: list[SharedItemRead] = Field(default_factory=list)


class ShareLinkResponse(BaseModel):
    share_url: str
    expires_at: datetime


class ShareUserRequest(BaseModel):
    login: str
    permission: str = "read"


class ShareUserResponse(BaseModel):
    status: str
    file_id: int
    shared_with_login: str


__all__ = [
    "SharedDirectoryContent",
    "SharedItemRead",
    "ShareLinkResponse",
    "ShareUserRequest",
    "ShareUserResponse",
]
