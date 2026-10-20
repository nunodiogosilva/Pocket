from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, select

from config import DEV_MODE, DEV_USER_LOGIN, DEV_USER_NAME, DEV_USER_PROFILE_PIC
from database import engine
from models import User


def get_db():
    with Session(engine) as session:
        yield session


def get_current_user(
    tailscale_user_login: Optional[str] = Header(None, alias="Tailscale-User-Login"),
    tailscale_user_name: Optional[str] = Header(None, alias="Tailscale-User-Name"),
    tailscale_user_profile_pic: Optional[str] = Header(None, alias="Tailscale-User-Profile-Pic"),
    session: Session = Depends(get_db),
) -> User:
    """Parses and trusts Tailscale Identity headers with Just-In-Time (JIT) user provisioning.
    
    In a Tailscale Serve environment, Tailscale authenticates the user at the network layer
    and injects verified identity headers:
      - Tailscale-User-Login: verified username/email (e.g. user@tailnet or user@gmail.com)
      - Tailscale-User-Name: verified user display name
      - Tailscale-User-Profile-Pic: URL of user profile picture
    
    If the user does not exist in the local SQLite database, they are provisioned JIT.
    """
    login = tailscale_user_login
    name = tailscale_user_name
    profile_pic = tailscale_user_profile_pic

    # In local development mode without a Tailnet proxy, use fallback identity
    if not login and DEV_MODE:
        login = DEV_USER_LOGIN
        name = name or DEV_USER_NAME
        profile_pic = profile_pic or DEV_USER_PROFILE_PIC

    if not login:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tailscale identity authentication required. No Tailscale-User-Login header received.",
        )

    # JIT Provisioning / lookup
    user = session.exec(select(User).where((User.login == login) | (User.email == login))).first()
    if not user:
        display_name = name or login.split("@")[0].replace(".", " ").title()
        user = User(login=login, name=display_name, email=login, profile_pic=profile_pic)
        session.add(user)
        session.commit()
        session.refresh(user)
    else:
        updated = False
        if name and user.name != name:
            user.name = name
            updated = True
        if profile_pic is not None and user.profile_pic != profile_pic:
            user.profile_pic = profile_pic
            updated = True
        if updated:
            session.add(user)
            session.commit()
            session.refresh(user)

    return user

