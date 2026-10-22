"""Tailscale Identity authentication via proxy headers.

Identity is delegated entirely to Tailscale: ``tailscale serve`` injects the
``Tailscale-User-*`` headers, and we validate/extract them here. In dev mode (or
behind a non-Tailscale proxy) a configurable fallback identity is used so local
development works.

Two layers are exposed:
* ``get_current_tailscale_user`` — returns a typed ``TailscaleUser`` (raw identity).
* ``get_current_user`` — resolves that identity to a persisted DB ``User`` row.
"""

import threading
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.dependencies.db import get_db
from app.models.user import User

# Serializes JIT provisioning within this worker process so concurrent first
# requests for the same identity don't both attempt the INSERT.
_user_provision_lock = threading.Lock()


def _find_user(session: Session, login: str) -> Optional[User]:
    return session.exec(select(User).where((User.login == login) | (User.email == login))).first()


def get_or_create_user(
    session: Session,
    login: str,
    name: Optional[str] = None,
    profile_pic: Optional[str] = None,
) -> User:
    """Find or JIT-provision a user and refresh identity profile fields.

    Safe under concurrent first requests: provisioning is serialized and a
    ``UNIQUE`` violation from a losing race is resolved by re-fetching the row
    that the winning request already committed.
    """
    with _user_provision_lock:
        user = _find_user(session, login)
        if not user:
            display_name = name or login.split("@")[0].replace(".", " ").title()
            user = User(login=login, name=display_name, email=login, profile_pic=profile_pic)
            session.add(user)
            try:
                session.commit()
            except IntegrityError:
                # Another worker/connection committed the same login first.
                session.rollback()
                user = _find_user(session, login)
                if user is None:
                    raise
            else:
                session.refresh(user)
                return user

        updated = False
        if name and user.name != name:
            user.name = name
            updated = True
        if profile_pic is not None and user.profile_pic != profile_pic:
            user.profile_pic = profile_pic
            updated = True
        if updated:
            session.add(user)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return _find_user(session, login) or user
            else:
                session.refresh(user)
    return user


@dataclass(frozen=True)
class TailscaleUser:
    """The authenticated identity carried by the Tailscale proxy headers."""

    login: str
    name: Optional[str] = None
    profile_pic: Optional[str] = None


def get_current_tailscale_user(
    tailscale_user_login: Optional[str] = Header(None, alias="Tailscale-User-Login"),
    tailscale_user_name: Optional[str] = Header(None, alias="Tailscale-User-Name"),
    tailscale_user_profile_pic: Optional[str] = Header(None, alias="Tailscale-User-Profile-Pic"),
) -> TailscaleUser:
    """Extract and validate the Tailscale identity headers (with dev fallback)."""
    login = tailscale_user_login
    name = tailscale_user_name
    profile_pic = tailscale_user_profile_pic

    if not login and settings.dev_mode:
        login = settings.dev_user_login
        name = name or settings.dev_user_name
        profile_pic = profile_pic or settings.dev_user_profile_pic

    if not login:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tailscale identity authentication required. No Tailscale-User-Login header received.",
        )

    return TailscaleUser(login=login, name=name, profile_pic=profile_pic)


def get_current_user(
    identity: TailscaleUser = Depends(get_current_tailscale_user),
    session: Session = Depends(get_db),
) -> User:
    """Resolve the trusted Tailscale identity to a persisted (or new) ``User``."""
    return get_or_create_user(session, identity.login, identity.name, identity.profile_pic)


__all__ = ["TailscaleUser", "get_current_tailscale_user", "get_current_user"]
