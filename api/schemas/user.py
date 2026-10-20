from typing import Optional
from sqlmodel import SQLModel


class UserRead(SQLModel):
    id: int
    login: str
    name: Optional[str] = None
    email: Optional[str] = None
    profile_pic: Optional[str] = None
