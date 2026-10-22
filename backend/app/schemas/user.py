from typing import Optional

from pydantic import BaseModel


class UserRead(BaseModel):
    """Authenticated user profile (never exposes the on-disk storage path)."""

    id: int
    login: str
    name: Optional[str] = None
    email: Optional[str] = None
    profile_pic: Optional[str] = None


__all__ = ["UserRead"]
