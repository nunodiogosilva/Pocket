from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel


class ShareLinkResponse(SQLModel):
    share_url: str
    expires_at: datetime


class ShareUserRequest(SQLModel):
    login: str
    permission: str = "read"


class ShareUserResponse(SQLModel):
    status: str
    file_id: int
    shared_with_login: str
