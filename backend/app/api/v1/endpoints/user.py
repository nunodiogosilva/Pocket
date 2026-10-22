"""User profile endpoint (Tailscale identity)."""

from fastapi import APIRouter, Depends

from app.dependencies.tailscale import get_current_user
from app.models.user import User
from app.schemas.user import UserRead

router = APIRouter(prefix="/api/user", tags=["User"])


@router.get("", response_model=UserRead)
def get_current_user_profile(user: User = Depends(get_current_user)):
    """Return the currently authenticated Tailscale user's profile."""
    return UserRead(
        id=user.id,
        login=user.login,
        name=user.name,
        email=user.email,
        profile_pic=user.profile_pic,
    )


__all__ = ["router"]
