from fastapi import APIRouter, Depends
from sqlmodel import Session
from dependencies import get_current_user, get_db
from models import User
from schemas import StorageUsage, UserRead
from services import storage

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("", response_model=UserRead)
@router.get("/me", response_model=UserRead)
def get_current_user_profile(user: User = Depends(get_current_user)):
    """Returns the currently authenticated Tailscale user profile."""
    return UserRead(
        id=user.id,
        login=user.login,
        name=user.name,
        email=user.email,
        profile_pic=user.profile_pic,
    )


@router.get("/storage", response_model=StorageUsage)
def get_current_user_storage(
    session: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns the current user's active storage consumption and file counts."""
    stats = storage.get_user_storage(session, user)
    return StorageUsage(**stats)

